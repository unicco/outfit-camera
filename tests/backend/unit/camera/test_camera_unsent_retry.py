#!/usr/bin/env python3
"""未送信写真の再送のテスト.

2026-08-08 に、撮影は成功したのに Wi-Fi 断でアップロードが通らず、その日の記録が
丸ごと欠測した。写真は Pi に残っていたので復旧できたが、気づいたのは翌日だった。

守る性質は 6 つ:
- **API に既にある写真を再送しない。**API は photo_id で冪等なので重複
  レコードにはならないが、Pi の上りが細いので届いている写真を上げ直さない
- 届いていない写真は**撮影日を明示して**送る。渡さないと API は受信時刻で記録するため、
  後日の再送が「送った日」の記録になる
- 送れなかったら**印を残す**（次の疎通で拾えるように）。疎通しないだけの場合も同じ
- 写真の実体が消えていたら印を消す（永久に再試行し続けない）
- 送るのは**アップロードだけ**（AI 検出は API がバックグラウンドで回すので Pi から
  重ねて叩かない）
- **撮り直しで捨てた写真は送らない**（UI が破棄を通知する）。写真の実体は
  残すので、誤タップは手動再送で救える

camera/camera_service.py はモジュール読み込み時に CameraService() を生成するため、
test_camera_auth.py と同じく importlib で読み込む（simulation モードでハードウェア回避）。
"""

import importlib.util
import os
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit

CAMERA_SERVICE_PATH = (
    Path(__file__).resolve().parents[4] / "camera" / "camera_service.py"
)


@pytest.fixture(scope="module")
def camera_module(tmp_path_factory):
    """未送信マークの置き場を一時ディレクトリに向けて camera_service を読み込む."""
    base = tmp_path_factory.mktemp("camera")
    os.environ["CAMERA_MODE"] = "simulation"
    os.environ["DISABLE_AI_FEATURES"] = "true"
    os.environ["PIR_ENABLED"] = "false"
    os.environ["PHOTOS_DIR"] = str(base / "photos")
    os.environ["UNSENT_MARKER_DIR"] = str(base / "unsent")
    # 再送ループが読み込み直後に 1 回走る。テスト中に再突入させたくないので長くする
    os.environ["UNSENT_RETRY_INTERVAL_SECONDS"] = "3600"

    spec = importlib.util.spec_from_file_location("camsvc_unsent", CAMERA_SERVICE_PATH)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # pragma: no cover - 環境にカメラ依存が無い場合
        pytest.skip(f"camera_service をロードできない: {exc}")
    return module


@pytest.fixture
def service(camera_module):
    """マークと写真を空にしたカメラサービス.

    写真も消す。残すと「実体が無い」ケースが前のテストのファイルで成立しなくなる。
    """
    svc = camera_module.camera_service
    for directory in (svc.unsent_dir, svc.photos_dir):
        for name in os.listdir(directory):
            os.remove(os.path.join(directory, name))
    return svc


def make_photo(service, filename):
    path = os.path.join(service.photos_dir, filename)
    Path(path).write_bytes(b"jpeg")
    return path


def metadata_response(status_code):
    response = MagicMock()
    response.status_code = status_code
    return response


PHOTO = "photo_20260808_112459.jpg"


def test_already_on_backend_is_not_resent(camera_module, service):
    """API に既にある写真は送らない（重複はしないが Pi の細い上りを無駄に使う）."""
    service._mark_unsent(PHOTO)
    make_photo(service, PHOTO)

    with patch.object(camera_module, "requests") as requests_mock:
        requests_mock.get.return_value = metadata_response(200)
        requests_mock.exceptions = camera_module.requests.exceptions
        with patch.object(service, "send_to_backend") as send:
            remaining = service.reconcile_unsent()

    send.assert_not_called()
    assert remaining == 0
    assert service.list_unsent() == []


def test_missing_photo_is_resent_with_captured_date(camera_module, service):
    """届いていない写真は撮影日を明示して送る."""
    service._mark_unsent(PHOTO)
    path = make_photo(service, PHOTO)

    with patch.object(camera_module, "requests") as requests_mock:
        requests_mock.get.return_value = metadata_response(404)
        requests_mock.exceptions = camera_module.requests.exceptions
        with patch.object(service, "send_to_backend", return_value=True) as send:
            remaining = service.reconcile_unsent()

    send.assert_called_once_with(path, captured_date="2026-08-08")
    assert remaining == 0
    assert service.list_unsent() == []


def test_upload_failure_keeps_mark(camera_module, service):
    """送信に失敗したら印を残す（次の疎通で拾う）."""
    service._mark_unsent(PHOTO)
    make_photo(service, PHOTO)

    with patch.object(camera_module, "requests") as requests_mock:
        requests_mock.get.return_value = metadata_response(404)
        requests_mock.exceptions = camera_module.requests.exceptions
        with patch.object(service, "send_to_backend", return_value=False):
            remaining = service.reconcile_unsent()

    assert remaining == 1
    assert service.list_unsent() == [PHOTO]


def test_unreachable_backend_does_not_upload(camera_module, service):
    """疎通しないときは送らず印も消さない（存在確認できていないため）."""
    service._mark_unsent(PHOTO)
    make_photo(service, PHOTO)

    with patch.object(camera_module, "requests") as requests_mock:
        requests_mock.exceptions = camera_module.requests.exceptions
        requests_mock.get.side_effect = (
            camera_module.requests.exceptions.ConnectionError("no route to host")
        )
        with patch.object(service, "send_to_backend") as send:
            remaining = service.reconcile_unsent()

    send.assert_not_called()
    assert remaining == 1
    assert service.list_unsent() == [PHOTO]


def test_missing_file_clears_mark(camera_module, service):
    """写真の実体が消えていたら印を消す（永久に再試行しない）."""
    service._mark_unsent(PHOTO)  # 写真は作らない

    with patch.object(camera_module, "requests") as requests_mock:
        requests_mock.get.return_value = metadata_response(404)
        requests_mock.exceptions = camera_module.requests.exceptions
        with patch.object(service, "send_to_backend") as send:
            remaining = service.reconcile_unsent()

    send.assert_not_called()
    assert remaining == 0
    assert service.list_unsent() == []


def test_concurrent_reconcile_sends_once(camera_module, service):
    """定期ループと halt 直前の再送が重なっても二重送信しない.

    ロックが無いと、両方が存在確認を通り抜けてから送信するため `_1` 付きの
    重複レコードができる。1 件目の存在確認で止めて、その間に 2 本目を走らせる。
    """
    service._mark_unsent(PHOTO)
    make_photo(service, PHOTO)

    first_call_started = threading.Event()
    release_first_call = threading.Event()
    calls = []

    def blocking_exists(photo_id):
        calls.append(photo_id)
        if len(calls) == 1:
            first_call_started.set()
            release_first_call.wait(timeout=5)
        return False

    with patch.object(service, "_photo_exists_on_backend", side_effect=blocking_exists):
        with patch.object(service, "send_to_backend", return_value=True) as send:
            first = threading.Thread(target=service.reconcile_unsent)
            first.start()
            assert first_call_started.wait(timeout=5)

            second = threading.Thread(target=service.reconcile_unsent)
            second.start()
            release_first_call.set()

            first.join(timeout=10)
            second.join(timeout=10)

    assert send.call_count == 1
    assert service.list_unsent() == []


def test_manual_upload_skips_when_already_on_backend(camera_module, service):
    """手動再送も存在確認を経由する（この経路だけ重複を作れてはいけない）."""
    from fastapi.testclient import TestClient

    service._mark_unsent(PHOTO)
    make_photo(service, PHOTO)
    client = TestClient(camera_module.app, client=("100.64.1.2", 50000))

    with patch.object(service, "_photo_exists_on_backend", return_value=True):
        with patch.object(service, "send_to_backend") as send:
            response = client.post(f"/upload/{PHOTO}")

    assert response.status_code == 200
    send.assert_not_called()
    assert service.list_unsent() == []


def test_manual_upload_does_not_send_when_backend_unreachable(camera_module, service):
    """存在を確認できないときは送らない（届いていれば重複になるため）."""
    from fastapi.testclient import TestClient

    service._mark_unsent(PHOTO)
    make_photo(service, PHOTO)
    client = TestClient(camera_module.app, client=("100.64.1.2", 50000))

    with patch.object(service, "_photo_exists_on_backend", return_value=None):
        with patch.object(service, "send_to_backend") as send:
            response = client.post(f"/upload/{PHOTO}")

    assert response.status_code == 503
    send.assert_not_called()
    assert service.list_unsent() == [PHOTO]


def test_manual_upload_does_not_race_with_reconcile(camera_module, service):
    """手動再送と再送ループが重なっても二重送信しない."""
    from fastapi.testclient import TestClient

    service._mark_unsent(PHOTO)
    make_photo(service, PHOTO)
    client = TestClient(camera_module.app, client=("100.64.1.2", 50000))

    uploaded = threading.Event()
    # 両方が「まだ届いていない」を観測した状態で揃うと重複送信になる。直列化されていれば
    # 片方はここに到達できず、待ち合わせは時間切れになる（それが正しい姿）
    both_observed = threading.Barrier(2)

    def blocking_exists(photo_id):
        observed = uploaded.is_set()
        try:
            both_observed.wait(timeout=1)
        except threading.BrokenBarrierError:
            pass
        return observed

    def fake_send(*args, **kwargs):
        uploaded.set()
        return True

    with patch.object(service, "_photo_exists_on_backend", side_effect=blocking_exists):
        with patch.object(service, "send_to_backend", side_effect=fake_send) as send:
            reconcile = threading.Thread(target=service.reconcile_unsent)
            manual = threading.Thread(target=lambda: client.post(f"/upload/{PHOTO}"))
            reconcile.start()
            manual.start()
            reconcile.join(timeout=10)
            manual.join(timeout=10)

    assert send.call_count == 1
    assert service.list_unsent() == []


def test_periodic_retry_sends_freshly_marked(camera_module, service):
    """撮ったばかりの写真も定期再送の対象にする.

    かつては UI と重複レコードを作らないよう 10 分の猶予を置いていた。API が冪等に
    なったので猶予は要らず、断からの復帰がその分だけ早くなる。
    """
    service._mark_unsent(PHOTO)
    make_photo(service, PHOTO)

    with patch.object(service, "_photo_exists_on_backend", return_value=False):
        with patch.object(service, "send_to_backend", return_value=True) as send:
            remaining = service.reconcile_unsent()

    send.assert_called_once()
    assert remaining == 0


@pytest.mark.parametrize("reason", ["api request", "daily cutoff"])
def test_shutdown_reconciles_regardless_of_reason(
    camera_module, service, monkeypatch, reason
):
    """halt の理由で猶予を出し分けない.

    20:00 の cutoff は UI が送っている最中でも落とすが、割り込んで送っても
    重複レコードにはならないので、UI 起因の halt と同じ扱いでよい。
    """
    service._mark_unsent(PHOTO)
    make_photo(service, PHOTO)
    monkeypatch.setattr(service, "auto_shutdown_enabled", True)
    monkeypatch.setattr(service, "_shutdown_in_progress", False)
    calls = []
    monkeypatch.setattr(
        service, "reconcile_unsent", lambda **kwargs: calls.append(kwargs)
    )
    monkeypatch.setattr(camera_module.subprocess, "run", lambda *a, **k: None)
    monkeypatch.setattr(camera_module.time, "sleep", lambda _s: None)

    service._perform_shutdown(reason=reason)
    for _ in range(50):
        if calls:
            break
        time.sleep(0.05)

    assert calls == [{"deadline_seconds": 10}]


def test_send_to_backend_does_not_trigger_ai_detection(camera_module, service):
    """送るのはアップロードだけ.

    AI 衣類検出は API が upload の中でバックグラウンド実行するので、Pi から重ねて
    叩くと二重呼び出しになる。
    """
    path = make_photo(service, PHOTO)
    response = MagicMock()
    response.status_code = 200

    with patch.object(camera_module, "requests") as requests_mock:
        requests_mock.post.return_value = response
        requests_mock.exceptions = camera_module.requests.exceptions
        assert service.send_to_backend(path, captured_date="2026-08-08") is True

    assert requests_mock.post.call_count == 1
    assert requests_mock.post.call_args[0][0].endswith("/v2/upload")


def test_send_to_backend_names_the_retry_path(camera_module, service):
    """再送は source=camera_retry を名乗る.

    UI の通常アップロードと DB 上で区別できないと、再送ループがどれだけ働いて
    いるかを後から数えられない。
    """
    path = make_photo(service, PHOTO)
    response = MagicMock()
    response.status_code = 200

    with patch.object(camera_module, "requests") as requests_mock:
        requests_mock.post.return_value = response
        requests_mock.exceptions = camera_module.requests.exceptions
        assert service.send_to_backend(path, captured_date="2026-08-08") is True

    data = requests_mock.post.call_args.kwargs["data"]
    assert data["source"] == "camera_retry"
    # captured_date を落として source だけ送る、の取り違えを防ぐ
    assert data["captured_date"] == "2026-08-08"


def test_send_to_backend_names_the_retry_path_without_captured_date(
    camera_module, service
):
    """captured_date が取れなくても source は送る."""
    path = make_photo(service, PHOTO)
    response = MagicMock()
    response.status_code = 200

    with patch.object(camera_module, "requests") as requests_mock:
        requests_mock.post.return_value = response
        requests_mock.exceptions = camera_module.requests.exceptions
        assert service.send_to_backend(path) is True

    assert requests_mock.post.call_args.kwargs["data"] == {"source": "camera_retry"}


def test_captured_date_from_filename(service):
    assert service._captured_date_from_filename(PHOTO) == "2026-08-08"
    assert service._captured_date_from_filename("touchscreen_photo.jpg") is None


def test_status_reports_unsent_count(camera_module, service):
    """未送信の件数が /status から見える."""
    from fastapi.testclient import TestClient

    service._mark_unsent(PHOTO)
    client = TestClient(camera_module.app, client=("100.64.1.2", 50000))

    assert client.get("/status").json()["unsent_photos"] == 1


def test_discard_clears_mark_and_keeps_photo(camera_module, service):
    """撮り直しで捨てた写真は再送の対象から外す。写真そのものは消さない."""
    from fastapi.testclient import TestClient

    service._mark_unsent(PHOTO)
    path = make_photo(service, PHOTO)
    client = TestClient(camera_module.app, client=("100.64.1.2", 50000))

    response = client.post(f"/photo/{PHOTO}/discard")

    assert response.status_code == 200
    assert response.json()["was_marked"] is True
    assert service.list_unsent() == []
    # 誤タップを手動再送で救えるように実体は残す
    assert os.path.exists(path)


def test_discard_is_idempotent(camera_module, service):
    """2 回叩いても失敗しない（UI は撮り直しのたびに投げる）."""
    from fastapi.testclient import TestClient

    service._mark_unsent(PHOTO)
    make_photo(service, PHOTO)
    client = TestClient(camera_module.app, client=("100.64.1.2", 50000))

    first = client.post(f"/photo/{PHOTO}/discard")
    second = client.post(f"/photo/{PHOTO}/discard")

    assert (first.status_code, second.status_code) == (200, 200)
    assert first.json()["was_marked"] is True
    assert second.json()["was_marked"] is False


def test_discard_rejects_invalid_photo_id(camera_module, service):
    """ディレクトリを遡る ID は弾く."""
    from fastapi.testclient import TestClient

    client = TestClient(camera_module.app, client=("100.64.1.2", 50000))

    assert client.post("/photo/not-a-photo/discard").status_code == 400


def test_discard_during_backend_check_stops_send(camera_module, service):
    """存在確認の I/O 中に破棄されたら送らない（の窓）."""
    service._mark_unsent(PHOTO)
    make_photo(service, PHOTO)

    def discard_while_checking(photo_id):
        service.discard_unsent(PHOTO)
        return False  # API には無い＝この後の送信に進もうとする

    with patch.object(
        service, "_photo_exists_on_backend", side_effect=discard_while_checking
    ):
        with patch.object(service, "send_to_backend") as send:
            remaining = service.reconcile_unsent()

    send.assert_not_called()
    assert remaining == 0


def test_manual_upload_works_after_discard(camera_module, service):
    """破棄した写真も手動再送で救える（印の有無を送るかの条件にしない）."""
    from fastapi.testclient import TestClient

    service._mark_unsent(PHOTO)
    path = make_photo(service, PHOTO)
    service.discard_unsent(PHOTO)
    client = TestClient(camera_module.app, client=("100.64.1.2", 50000))

    with patch.object(service, "_photo_exists_on_backend", return_value=False):
        with patch.object(service, "send_to_backend", return_value=True) as send:
            response = client.post(f"/upload/{PHOTO}")

    assert response.status_code == 200
    send.assert_called_once_with(path, captured_date="2026-08-08")
