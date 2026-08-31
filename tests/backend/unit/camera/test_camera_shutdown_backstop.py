#!/usr/bin/env python3
"""スケジュール halt のバックストップのテスト.

2026-08-10 に、玄関 Pi が起動から約 10 時間 ON のままだった。NTP が一度も同期せず、
毎日 cutoff（20:00 JST）は同期待ちで保留、16 時間の最終バックストップには届かない、
という窓が空いていた。

守る性質は 5 つ:
- **NTP が一度も同期しないまま所定時間が経ったら halt する**（同期待ちで無限に粘らない）
- 未同期でも所定時間に達していなければ halt しない（起動直後に落とさない）
- **一度同期したら以後は壁時計を信用する**（NTPSynchronized が no に転んでも cutoff が効く）
- 経過は **システム起動から** 測る（サービス再起動でタイマーが巻き戻らない）
- **latch は boot 単位**。上 2 つの組み合わせで、サービス再起動の直後は「プロセス内の latch は
  初期化済・経過は閾値超過」になる。ここで「同期後に見失った」を「一度も同期していない」と
  読むと、同期済で稼働中の Pi を落とす
- **同期状態が読めない周回では halt しない**（timedatectl の一過性の失敗を未同期と読まない）

camera/camera_service.py はモジュール読み込み時に CameraService() を生成するため、
test_camera_unsent_retry.py と同じく importlib で読み込む（simulation モードでハードウェア回避）。
"""

import importlib.util
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

pytestmark = pytest.mark.unit

CAMERA_SERVICE_PATH = (
    Path(__file__).resolve().parents[4] / "camera" / "camera_service.py"
)

JST = ZoneInfo("Asia/Tokyo")


@pytest.fixture(scope="module")
def camera_module(tmp_path_factory):
    base = tmp_path_factory.mktemp("camera_shutdown")
    os.environ["CAMERA_MODE"] = "simulation"
    os.environ["DISABLE_AI_FEATURES"] = "true"
    os.environ["PIR_ENABLED"] = "false"
    os.environ["PHOTOS_DIR"] = str(base / "photos")
    os.environ["UNSENT_MARKER_DIR"] = str(base / "unsent")
    os.environ["UNSENT_RETRY_INTERVAL_SECONDS"] = "3600"

    spec = importlib.util.spec_from_file_location(
        "camsvc_shutdown", CAMERA_SERVICE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # pragma: no cover - 環境にカメラ依存が無い場合
        pytest.skip(f"camera_service をロードできない: {exc}")
    return module


@pytest.fixture
def service(camera_module, tmp_path):
    """halt を有効にしたカメラサービス（テストごとに状態を戻す）.

    boot フラグは既定で「存在しない」= この boot で一度も同期していない状態にする。
    同期済を作るテストは flag_path を touch する。
    """
    svc = camera_module.camera_service
    saved = (
        svc.auto_shutdown_enabled,
        svc.stop_shutdown_monitor,
        svc._clock_ever_synced,
        svc.max_uptime_seconds,
        svc.max_unsynced_uptime_seconds,
        svc.daily_shutdown_hour,
        svc.daily_shutdown_minute,
        svc.service_start_monotonic,
        svc.clock_synced_flag_path,
    )
    svc.auto_shutdown_enabled = True
    svc.stop_shutdown_monitor = False
    svc._clock_ever_synced = False
    svc.max_uptime_seconds = 57600
    svc.max_unsynced_uptime_seconds = 21600
    svc.daily_shutdown_hour, svc.daily_shutdown_minute = 20, 0
    svc.clock_synced_flag_path = str(tmp_path / "synchronized")
    yield svc
    (
        svc.auto_shutdown_enabled,
        svc.stop_shutdown_monitor,
        svc._clock_ever_synced,
        svc.max_uptime_seconds,
        svc.max_unsynced_uptime_seconds,
        svc.daily_shutdown_hour,
        svc.daily_shutdown_minute,
        svc.service_start_monotonic,
        svc.clock_synced_flag_path,
    ) = saved


HOUR = 3600


def run_loop(camera_module, service, steps):
    """シャットダウン監視ループを回して halt の理由を返す（halt しなければ None）.

    steps は 1 周回分の (uptime 秒, NTP 同期済か, 壁時計) のリスト。
    halt しないまま尽きたら sleep のところでループを止める。
    """
    remaining = list(steps)
    clock = MagicMock(wraps=datetime)
    shutdown = MagicMock()

    def advance():
        uptime, synced, now = remaining.pop(0)
        clock.now.return_value = now
        advance.synced = synced
        return uptime

    def stop_sleeping(_seconds):
        if not remaining:
            service.stop_shutdown_monitor = True

    with (
        patch.object(service, "_perform_shutdown", shutdown),
        patch.object(service, "_uptime_seconds", side_effect=advance),
        patch.object(service, "_is_clock_synced", side_effect=lambda: advance.synced),
        patch.object(camera_module.time, "sleep", side_effect=stop_sleeping),
        patch.object(camera_module, "datetime", clock),
    ):
        service._scheduled_shutdown_loop()

    if not shutdown.called:
        return None
    return shutdown.call_args.kwargs["reason"]


def test_never_synced_halts_at_threshold(camera_module, service):
    """NTP が一度も同期しないまま閾値を超えたら halt する（の窓）.

    壁時計は fake-hwclock が復元した前夜の値のまま進んでいる（cutoff は判定できない）。
    """
    reason = run_loop(
        camera_module,
        service,
        [
            (5 * HOUR, False, datetime(2026, 8, 9, 23, 30, tzinfo=JST)),
            (6 * HOUR, False, datetime(2026, 8, 10, 0, 30, tzinfo=JST)),
        ],
    )

    assert reason == "unsynced-clock backstop"


def test_never_synced_below_threshold_stays_up(camera_module, service):
    """未同期でも閾値に達していなければ落とさない（起動直後に落とさない）."""
    reason = run_loop(
        camera_module,
        service,
        [
            (60, False, datetime(2026, 8, 9, 20, 1, tzinfo=JST)),
            (2 * HOUR, False, datetime(2026, 8, 9, 22, 0, tzinfo=JST)),
        ],
    )

    assert reason is None


def test_unsynced_backstop_does_not_fire_after_sync(camera_module, service):
    """一度同期したら、同期が no に転んでも未同期バックストップは発火しない.

    latch しないと、同期が落ちた瞬間に「未同期のまま 6 時間経った」と誤判定して
    稼働中の Pi を昼間に落とす。
    """
    reason = run_loop(
        camera_module,
        service,
        [
            (HOUR, True, datetime(2026, 8, 10, 8, 0, tzinfo=JST)),
            (7 * HOUR, False, datetime(2026, 8, 10, 14, 0, tzinfo=JST)),
        ],
    )

    assert reason is None
    assert service._clock_ever_synced is True


def test_daily_cutoff_still_fires_after_sync_is_lost(camera_module, service):
    """同期が no に転んでも cutoff は効く（壁時計は既に合っている）."""
    reason = run_loop(
        camera_module,
        service,
        [
            (HOUR, True, datetime(2026, 8, 10, 8, 0, tzinfo=JST)),
            (13 * HOUR, False, datetime(2026, 8, 10, 20, 1, tzinfo=JST)),
        ],
    )

    assert reason == "daily cutoff"


def test_max_uptime_backstop_still_wins(camera_module, service):
    """16 時間の最終バックストップは未同期バックストップと独立に効く."""
    reason = run_loop(
        camera_module,
        service,
        [(17 * HOUR, True, datetime(2026, 8, 10, 6, 0, tzinfo=JST))],
    )

    assert reason == "max-uptime backstop"


def test_sync_lost_after_service_restart_does_not_halt(camera_module, service):
    """サービス再起動で latch が巻き戻っても、この boot で同期済なら halt しない.

    ヘルスモニタの restart 直後は `_clock_ever_synced` が False に戻る一方、経過は
    システム起動基準で閾値を超えている。ここで timedatectl が no（同期後に NTP を
    見失った）を返しても、「一度も同期していない」と読んではいけない。
    """
    Path(service.clock_synced_flag_path).touch()

    reason = run_loop(
        camera_module,
        service,
        [
            (7 * HOUR, False, datetime(2026, 8, 10, 14, 0, tzinfo=JST)),
            (7 * HOUR + 60, False, datetime(2026, 8, 10, 14, 1, tzinfo=JST)),
        ],
    )

    assert reason is None
    assert service._clock_ever_synced is True


def test_sync_lost_after_service_restart_still_honors_cutoff(camera_module, service):
    """同じ状況でも cutoff は効く（この boot で同期済＝壁時計は合っている）."""
    Path(service.clock_synced_flag_path).touch()

    reason = run_loop(
        camera_module,
        service,
        [(7 * HOUR, False, datetime(2026, 8, 10, 20, 1, tzinfo=JST))],
    )

    assert reason == "daily cutoff"


def test_unknown_sync_state_does_not_halt_after_service_restart(camera_module, service):
    """同期状態が読めない周回では halt しない（サービス再起動直後の誤 halt を防ぐ）.

    ヘルスモニタの restart 直後は latch が初期化され、経過はシステム起動基準で閾値を
    超えている。この周回で timedatectl が答えられなくても未同期と決めつけない。
    """
    reason = run_loop(
        camera_module,
        service,
        [
            (7 * HOUR, None, datetime(2026, 8, 10, 14, 0, tzinfo=JST)),
            (7 * HOUR + 60, True, datetime(2026, 8, 10, 14, 1, tzinfo=JST)),
        ],
    )

    assert reason is None
    assert service._clock_ever_synced is True


def test_is_clock_synced_returns_none_when_timedatectl_fails(camera_module, service):
    """timedatectl が答えないときは None を返す（False に丸めない）."""
    failed = MagicMock(returncode=1, stdout="")
    with patch.object(camera_module.subprocess, "run", return_value=failed):
        assert service._is_clock_synced() is None

    with patch.object(camera_module.subprocess, "run", side_effect=OSError("boom")):
        assert service._is_clock_synced() is None

    for value, expected in (("yes", True), ("no", False)):
        answered = MagicMock(returncode=0, stdout=f"{value}\n")
        with patch.object(camera_module.subprocess, "run", return_value=answered):
            assert service._is_clock_synced() is expected


def test_uptime_is_measured_from_system_boot(camera_module, service):
    """経過は /proc/uptime（システム起動から）で測る.

    サービス起動からの monotonic だと、ヘルスモニタの restart でタイマーが巻き戻り、
    バックストップが規定時間で発火しない。
    """
    with patch("builtins.open", MagicMock()) as open_mock:
        open_mock.return_value.__enter__.return_value.read.return_value = (
            "37260.12 145000.00"
        )
        assert service._uptime_seconds() == pytest.approx(37260.12)


def test_uptime_falls_back_when_proc_is_absent(camera_module, service):
    """/proc が無い環境（macOS 等）ではサービス起動基準にフォールバックする."""
    with (
        patch("builtins.open", side_effect=OSError("no /proc")),
        patch.object(camera_module.time, "monotonic", return_value=1000.0),
    ):
        service.service_start_monotonic = 400.0
        assert service._uptime_seconds() == pytest.approx(600.0)
