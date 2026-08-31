#!/usr/bin/env python3
"""フレームの向きを直す経路のテスト。

`/stream`・`/capture/preview`・`/capture` は同じ絵を返さないといけない。ここが
ずれると「ライブ映像と撮った写真で構図が違う」になるので、3 経路が共有する
`orient_frame` の挙動を固定する。

camera/camera_service.py はモジュール読み込み時に CameraService() を生成するため、
test_camera_auth.py と同じく importlib で読み込む（simulation モードでハードウェア回避）。
"""

import importlib.util
import math
import os
from pathlib import Path

import cv2
import numpy as np
import pytest

pytestmark = pytest.mark.unit

CAMERA_SERVICE_PATH = (
    Path(__file__).resolve().parents[4] / "camera" / "camera_service.py"
)


@pytest.fixture(scope="module")
def service():
    # ⚠️ 読み込みのあいだだけ simulation にして戻す。置きっぱなしにすると
    # 同じセッションの他のテストが実機の有無を誤認する
    previous = os.environ.get("CAMERA_MODE")
    os.environ["CAMERA_MODE"] = "simulation"
    spec = importlib.util.spec_from_file_location(
        "camsvc_orientation", CAMERA_SERVICE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    # ⚠️ **skip にするのは依存が無いときだけ。**何でも skip にすると、読み込み時に
    # 壊れた変更が「実行されなかった」ことに紛れて緑のまま通る
    except ModuleNotFoundError as exc:  # pragma: no cover - 依存が無い環境
        pytest.skip(f"camera_service の依存が無いためスキップ: {exc}")
    finally:
        if previous is None:
            os.environ.pop("CAMERA_MODE", None)
        else:
            os.environ["CAMERA_MODE"] = previous
    return module


def make_frame(width: int, height: int) -> np.ndarray:
    """行ごとに値が変わるフレーム。上下の入れ替わりが見える。"""
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    for row in range(height):
        frame[row, :, :] = row % 256
    return frame


def test_no_rotation_passes_frame_through(service, monkeypatch) -> None:
    monkeypatch.delenv("CAMERA_STREAM_ROTATION", raising=False)
    monkeypatch.delenv("CAMERA_ROTATION_FINE_DEG", raising=False)

    frame = make_frame(64, 48)
    assert np.array_equal(service.orient_frame(frame), frame)


@pytest.mark.parametrize("quarter_turn", ["90", "270"])
def test_quarter_turn_swaps_axes(service, monkeypatch, quarter_turn: str) -> None:
    """既存の挙動を固定する。90/270 で縦横が入れ替わらないと横位置で刷られる。"""
    monkeypatch.setenv("CAMERA_STREAM_ROTATION", quarter_turn)
    monkeypatch.delenv("CAMERA_ROTATION_FINE_DEG", raising=False)

    oriented = service.orient_frame(make_frame(64, 48))
    assert oriented.shape[:2] == (64, 48)


def test_180_keeps_shape_and_flips(service, monkeypatch) -> None:
    monkeypatch.setenv("CAMERA_STREAM_ROTATION", "180")
    monkeypatch.delenv("CAMERA_ROTATION_FINE_DEG", raising=False)

    frame = make_frame(64, 48)
    oriented = service.orient_frame(frame)
    assert oriented.shape == frame.shape
    assert np.array_equal(oriented, frame[::-1, ::-1])


def rotate_without_border_fill(
    frame: np.ndarray, degrees: float, scale: float
) -> np.ndarray:
    """縁を埋めずに回す。はみ出したところは黒のまま残る。"""
    height, width = frame.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), degrees, scale)
    return cv2.warpAffine(
        frame,
        matrix,
        (width, height),
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0),
    )


@pytest.mark.parametrize("degrees", [0.5, 3.0, 15.0])
def test_cover_scale_kills_black_corners(service, degrees: float) -> None:
    """拡大率が足りているかを、縁を埋めずに回して確かめる。

    ⚠️ `orient_frame` は保険で `BORDER_REPLICATE` を使うので、**そちらの出力を見ても
    黒は出ない**（拡大率が壊れていても気づけない）。ここは同じ行列を
    `BORDER_CONSTANT` で当てて拡大率だけを見る。細長い画ほど角がはみ出しやすい。
    """
    size = (180, 320)  # (幅, 高さ)
    white = np.full((size[1], size[0], 3), 255, dtype=np.uint8)

    # 拡大しなければ黒い角が出る＝この検査が空振りでないことの確認
    assert rotate_without_border_fill(white, degrees, 1.0).min() == 0

    rotated = rotate_without_border_fill(
        white, degrees, service.cover_scale(size, degrees)
    )
    # ⚠️ **いちばん外の 1px は見ない。**拡大率は画像の外枠に接する値なので、補間が
    # 半画素ぶん外を拾って端だけ薄くなる。`orient_frame` が縁の色で埋めているのはこのため
    assert rotated[1:-1, 1:-1].min() == 255


def test_positive_angle_turns_counterclockwise(service, monkeypatch) -> None:
    """正の値で反時計回り＝右に倒れた絵が起きる向き。逆だと傾きが倍になる。"""
    monkeypatch.delenv("CAMERA_STREAM_ROTATION", raising=False)
    monkeypatch.setenv("CAMERA_ROTATION_FINE_DEG", "10")

    frame = np.zeros((200, 200, 3), dtype=np.uint8)
    frame[10:30, 90:110] = 255  # 上辺の中央に印を置く

    oriented = service.orient_frame(frame)
    brightest_column = int(oriented[:40].sum(axis=(0, 2)).argmax())
    assert brightest_column < 100


@pytest.mark.parametrize("raw", ["ひだり", "16", "-16", "nan", "inf", "-inf"])
def test_unusable_angle_falls_back_to_no_correction(service, monkeypatch, raw) -> None:
    """毎朝の記録を落とさない。読めない値も範囲外も補正なしで続ける。

    🚨 `nan` と `inf` は `float()` を通ってしまい、しかも `abs(nan) > 上限` が False
    なので範囲の検査もすり抜ける。素通しすると行列が NaN になってフレームが壊れる。
    """
    monkeypatch.setenv("CAMERA_ROTATION_FINE_DEG", raw)
    assert service.fine_rotation_deg() == 0.0

    # 補正なしに倒れるので、フレームはそのまま返る
    monkeypatch.delenv("CAMERA_STREAM_ROTATION", raising=False)
    frame = make_frame(64, 48)
    assert np.array_equal(service.orient_frame(frame), frame)


# 実機（IMX708 wide）のモード。1536×864 だけが中央 3072×1728 を読む物理クロップで、
# 他の 2 つは 4608×2592 の全域（2026-08-26 に ScalerCrop を実測）
IMX708_MODES = [
    {"size": (1536, 864)},
    {"size": (2304, 1296)},
    {"size": (4608, 2592)},
]


def test_shared_sensor_mode_covers_both_resolutions(service) -> None:
    """🚨 実機で起きていた食い違いそのもの。

    待機 1920×1080 は `2304×1296`（全画角）、撮影 1280×720 は `1536×864`（中央 2/3）に
    落ちていた。両方を賄うモードを選べば、保存写真だけ狭いことは起きない。
    """
    assert service.shared_sensor_mode(IMX708_MODES, [(1920, 1080), (1280, 720)]) == (
        2304,
        1296,
    )


def test_shared_sensor_mode_picks_the_smallest_that_fits(service) -> None:
    """発熱対策で待機を低くしてあるので、要らない大きさは選ばない。"""
    assert service.shared_sensor_mode(IMX708_MODES, [(1280, 720)]) == (1536, 864)
    assert service.shared_sensor_mode(IMX708_MODES, [(4608, 2592)]) == (4608, 2592)


def test_sensor_kwargs_passes_the_mode_through(service) -> None:
    """3 つの configuration がこれを共有する。片方の形が崩れると画角が食い違う。"""
    camera = service.camera_service
    previous = camera.sensor_mode
    try:
        camera.sensor_mode = (2304, 1296)
        assert camera._sensor_kwargs() == {"raw": {"size": (2304, 1296)}}

        # 固定できなかったときは指定なし＝picamera2 の自動選択に戻す
        camera.sensor_mode = None
        assert camera._sensor_kwargs() == {}
    finally:
        camera.sensor_mode = previous


def test_shared_sensor_mode_falls_back_when_nothing_fits(service) -> None:
    """賄えなければ None＝従来どおり picamera2 に選ばせる（撮影を止めない）。"""
    assert service.shared_sensor_mode(IMX708_MODES, [(8000, 6000)]) is None
    assert service.shared_sensor_mode([], [(1920, 1080)]) is None
    assert service.shared_sensor_mode(IMX708_MODES, []) is None


def test_cover_scale_matches_geometry(service) -> None:
    assert service.cover_scale((100, 200), 0) == pytest.approx(1.0)
    # 正方形を 45 度回すと対角がそのまま辺になる
    assert service.cover_scale((100, 100), 45) == pytest.approx(math.sqrt(2))
    # 細長いほど高くつく（実機の 1080×1920 を 2 度で 6% 強）
    assert service.cover_scale((1080, 1920), 2) == pytest.approx(1.061, abs=0.001)


# 実機の値。1080×1920 を 4.1 度回すと単体では 12.5% 食う
REAL = (1080, 1920)
REAL_TILT = 4.1


def test_effective_zoom_makes_rotation_free_when_cropping(service) -> None:
    """⭐ この PR の眼目。切り出しが回転に必要な拡大以上なら、傾き補正はタダになる。"""
    rotation_only = service.effective_zoom(REAL, REAL_TILT, 1.0)
    assert rotation_only == pytest.approx(1.125, abs=0.001)  # 12.5% 失う

    # 切り出し 1.5 倍と併用すると、拡大は 1.5 のまま＝回転のぶんは上乗せされない
    assert service.effective_zoom(REAL, REAL_TILT, 1.5) == pytest.approx(1.5)


def test_effective_zoom_never_lets_black_corners_in(service) -> None:
    """切り出しが足りないときは回転に必要なぶんまで引き上げる。"""
    assert service.effective_zoom(REAL, REAL_TILT, 1.05) == pytest.approx(
        service.cover_scale(REAL, REAL_TILT)
    )
    # 回転が無ければ要求どおり
    assert service.effective_zoom(REAL, 0.0, 1.4) == pytest.approx(1.4)
    assert service.effective_zoom(REAL, 0.0, 1.0) == pytest.approx(1.0)


@pytest.mark.parametrize("raw", ["まんなか", "0.9", "0", "-1", "3.1", "nan", "inf"])
def test_unusable_center_zoom_falls_back_to_no_crop(service, monkeypatch, raw) -> None:
    """⚠️ 1.0 未満は縮小＝外側を埋められないので弾く。撮影は止めない。"""
    monkeypatch.setenv("CAMERA_CENTER_ZOOM", raw)
    assert service.center_zoom() == 1.0


def test_usable_settings_pass_through(service, monkeypatch) -> None:
    """境界と実機の値がそのまま通ること（退避側だけ効いて常に既定、を防ぐ）。"""
    monkeypatch.setenv("CAMERA_CENTER_ZOOM", "1.5")
    assert service.center_zoom() == pytest.approx(1.5)
    monkeypatch.setenv("CAMERA_CENTER_ZOOM", str(service.CENTER_ZOOM_LIMIT))
    assert service.center_zoom() == pytest.approx(service.CENTER_ZOOM_LIMIT)
    monkeypatch.delenv("CAMERA_CENTER_ZOOM")
    assert service.center_zoom() == 1.0

    monkeypatch.setenv("CAMERA_ROTATION_FINE_DEG", str(REAL_TILT))
    assert service.fine_rotation_deg() == pytest.approx(REAL_TILT)
    monkeypatch.delenv("CAMERA_ROTATION_FINE_DEG")
    assert service.fine_rotation_deg() == 0.0


def test_center_zoom_crops_the_middle(service, monkeypatch) -> None:
    """中央の半分が画面いっぱいに広がる。⚠️ 値でなく**どの行が来たか**で見る
    （補間で偶然その値になった画素と区別できないため）。"""
    monkeypatch.delenv("CAMERA_STREAM_ROTATION", raising=False)
    monkeypatch.delenv("CAMERA_ROTATION_FINE_DEG", raising=False)
    monkeypatch.setenv("CAMERA_CENTER_ZOOM", "2")

    # 行番号がそのまま明るさになるフレーム（400 行 → 0..199）
    frame = np.zeros((400, 200, 3), dtype=np.uint8)
    for row in range(400):
        frame[row, :, :] = row // 2

    oriented = service.orient_frame(frame)
    assert oriented.shape == frame.shape
    # 2 倍なら出力の上端は元の 100 行目（値 50）、下端は 299 行目（値 149）
    assert int(oriented[0, 100, 0]) == pytest.approx(50, abs=2)
    assert int(oriented[-1, 100, 0]) == pytest.approx(149, abs=2)


def test_rotation_and_crop_share_one_pass(service, monkeypatch) -> None:
    """回転と切り出しを併用しても黒い角が出ず、寸法も変わらない。"""
    monkeypatch.delenv("CAMERA_STREAM_ROTATION", raising=False)
    monkeypatch.setenv("CAMERA_ROTATION_FINE_DEG", str(REAL_TILT))
    monkeypatch.setenv("CAMERA_CENTER_ZOOM", "1.5")

    white = np.full((320, 180, 3), 255, dtype=np.uint8)
    oriented = service.orient_frame(white)
    assert oriented.shape == white.shape
    assert oriented.min() == 255
