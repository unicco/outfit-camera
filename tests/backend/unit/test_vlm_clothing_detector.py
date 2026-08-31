"""VLMClothingDetector のユニットテスト."""

import base64
import io
import json
import logging
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from coordinate_recorder.vlm_clothing_detector import (
    MAX_PHOTO_EDGE,
    VLMClothingDetector,
    _cap_encoded_image,
    _encode_jpeg,
    _extract_matches,
    _strip_json_fence,
)


def _jpeg_bytes(width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (128, 128, 128)).save(buffer, format="JPEG")
    return buffer.getvalue()


def _decode_size(image_b64: str) -> tuple:
    return Image.open(io.BytesIO(base64.b64decode(image_b64))).size


class TestVLMClothingDetectorInit:
    """初期化テスト."""

    def test_init_with_api_key(self):
        """明示的に API キーを渡した場合."""
        detector = VLMClothingDetector(api_key="test-key")
        assert detector.api_key == "test-key"
        assert detector.is_available is True

    def test_init_from_env(self, monkeypatch):
        """環境変数から API キーを取得する場合."""
        monkeypatch.setenv("GEMINI_API_KEY", "env-key")
        detector = VLMClothingDetector()
        assert detector.api_key == "env-key"
        assert detector.is_available is True

    def test_init_no_key(self, monkeypatch):
        """API キーが未設定の場合、is_available が False."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        detector = VLMClothingDetector()
        assert detector.is_available is False


class TestBuildMatchingPrompt:
    """プロンプト構築テスト."""

    @pytest.fixture()
    def prompt(self):
        return VLMClothingDetector(api_key="test")._build_matching_prompt()

    def test_prompt_contains_json_instruction(self, prompt):
        """プロンプトに JSON 配列の指示が含まれる."""
        assert "JSON" in prompt
        assert "position" in prompt
        assert "type" in prompt

    def test_prompt_asks_for_wardrobe_item_number(self, prompt):
        """ワードローブのアイテム番号を返させる指示が含まれる."""
        assert "wardrobe_item_number" in prompt

    def test_prompt_mentions_layering(self, prompt):
        """重ね着に関する指示が含まれる."""
        assert "重ね着" in prompt

    def test_prompt_mentions_shoes_and_bag(self, prompt):
        """靴・バッグの位置指定が含まれる."""
        assert "feet" in prompt
        assert "hand" in prompt


class TestPositionToBbox:
    """位置情報から bbox 推定のテスト."""

    @pytest.fixture()
    def detector(self):
        return VLMClothingDetector(api_key="test")

    def test_upper_body(self, detector):
        """上半身の bbox が画像上部に配置される."""
        bbox = detector._position_to_bbox("upper_body", 400, 600)
        assert bbox["x"] == 200.0  # 中心
        assert bbox["y"] == 180.0  # 600 * 0.30
        assert bbox["width"] == 240.0  # 400 * 0.6
        assert bbox["height"] == 210.0  # 600 * 0.35

    def test_lower_body(self, detector):
        """下半身の bbox が画像下部に配置される."""
        bbox = detector._position_to_bbox("lower_body", 400, 600)
        assert bbox["y"] == 390.0  # 600 * 0.65

    def test_feet(self, detector):
        """足元の bbox が画像最下部に配置される."""
        bbox = detector._position_to_bbox("feet", 400, 600)
        assert bbox["y"] == 540.0  # 600 * 0.90

    def test_full_body(self, detector):
        """全身の bbox が画像中央に大きく配置される."""
        bbox = detector._position_to_bbox("full_body", 400, 600)
        assert bbox["y"] == 300.0  # 600 * 0.50
        assert bbox["height"] == 420.0  # 600 * 0.70

    def test_unknown_position_defaults_to_full_body(self, detector):
        """未知の位置は full_body と同じ bbox を返す."""
        unknown = detector._position_to_bbox("unknown_pos", 400, 600)
        full = detector._position_to_bbox("full_body", 400, 600)
        assert unknown == full


class TestMatchWithWardrobe:
    """Gemini 一括マッチングのモックテスト（本番が通る唯一の経路）."""

    @pytest.fixture()
    def detector(self):
        return VLMClothingDetector(api_key="test-key")

    @pytest.fixture()
    def sample_image(self):
        return np.zeros((600, 400, 3), dtype=np.uint8)

    @pytest.fixture()
    def wardrobe_items(self):
        return [
            {
                "id": "item-jacket",
                "name": "ネイビージャケット",
                "category": "outerwear",
                "subcategory": "jacket",
                "thumbnail": _jpeg_bytes(200, 200),
            },
            {
                "id": "item-pants",
                "name": "黒パンツ",
                "category": "bottoms",
                "subcategory": "pants",
                "thumbnail": _jpeg_bytes(200, 200),
            },
        ]

    @patch("coordinate_recorder.vlm_clothing_detector.requests")
    def test_successful_matching(
        self, mock_requests, detector, sample_image, wardrobe_items
    ):
        """マッチした番号が ID に解決され、種類・色・レイヤーがそのまま返る."""
        matches = [
            {
                "candidates": [{"wardrobe_item_number": 1, "confidence": 0.92}],
                "type": "jacket",
                "color": "navy",
                "color_hex": "#1B2A4A",
                "position": "upper_body",
                "layer": "outer",
            },
            {
                "candidates": [],
                "type": "shoes",
                "color": "white",
                "color_hex": "#FFFFFF",
                "position": "feet",
                "layer": "1",
            },
        ]
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": json.dumps(matches)}]}}]
        }
        mock_response.raise_for_status.return_value = None
        mock_requests.post.return_value = mock_response

        results = detector.match_with_wardrobe(sample_image, wardrobe_items)

        assert len(results) == 2
        assert results[0]["wardrobe_item_id"] == "item-jacket"
        assert results[0]["wardrobe_candidates"] == [
            {"wardrobe_item_id": "item-jacket", "confidence": 0.92}
        ]
        assert results[0]["type"] == "jacket"
        assert results[0]["color"] == "navy"
        assert results[0]["color_hex"] == "#1B2A4A"
        assert results[0]["position"] == "upper_body"
        assert results[0]["layer"] == "outer"
        assert results[0]["confidence"] == 0.92

        # ワードローブに該当なしでも、検出したアイテムとしては返る
        assert results[1]["wardrobe_item_id"] is None
        assert results[1]["wardrobe_candidates"] == []
        assert results[1]["type"] == "shoes"

    @patch("coordinate_recorder.vlm_clothing_detector.requests")
    def test_api_error_returns_empty(
        self, mock_requests, detector, sample_image, wardrobe_items
    ):
        """API エラー時に空リストを返す."""
        mock_requests.post.side_effect = Exception("API error")

        assert detector.match_with_wardrobe(sample_image, wardrobe_items) == []

    @patch("coordinate_recorder.vlm_clothing_detector.requests")
    def test_default_confidence(
        self, mock_requests, detector, sample_image, wardrobe_items
    ):
        """confidence が未指定の場合デフォルト 0.8."""
        matches = [{"candidates": [{"wardrobe_item_number": 1}], "type": "jacket"}]
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": json.dumps(matches)}]}}]
        }
        mock_response.raise_for_status.return_value = None
        mock_requests.post.return_value = mock_response

        results = detector.match_with_wardrobe(sample_image, wardrobe_items)

        assert results[0]["confidence"] == 0.8
        assert results[0]["wardrobe_candidates"][0]["confidence"] == 0.8

    def test_returns_empty_when_unavailable(
        self, monkeypatch, sample_image, wardrobe_items
    ):
        """API キー未設定時に空リストを返す."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        detector = VLMClothingDetector()

        assert detector.match_with_wardrobe(sample_image, wardrobe_items) == []


class TestImageSizeCap:
    """VLM へ送る画像の長辺上限."""

    def test_encode_jpeg_shrinks_long_edge(self):
        """長辺が上限を超えたらアスペクト比を保って縮める."""
        pil_image = Image.new("RGB", (4000, 3000))
        result = _encode_jpeg(pil_image, 2048)

        assert Image.open(io.BytesIO(result)).size == (2048, 1536)

    def test_encode_jpeg_keeps_size_within_cap(self):
        """上限内なら寸法を変えない."""
        pil_image = Image.new("RGB", (1920, 1080))
        result = _encode_jpeg(pil_image, 2048)

        assert Image.open(io.BytesIO(result)).size == (1920, 1080)

    def test_cap_encoded_image_returns_original_bytes_within_cap(self):
        """上限内のバイト列は再エンコードせず原本を返す."""
        original = _jpeg_bytes(200, 200)

        assert _cap_encoded_image(original, 384) is original

    def test_cap_encoded_image_shrinks_oversized(self):
        """上限を超えるバイト列は縮める."""
        original = _jpeg_bytes(764, 1274)
        result = _cap_encoded_image(original, 384)

        assert Image.open(io.BytesIO(result)).size == (230, 384)

    def test_encode_jpeg_keeps_size_at_exact_cap(self):
        """長辺が上限ちょうどならリサイズしない."""
        pil_image = Image.new("RGB", (2048, 1536))
        result = _encode_jpeg(pil_image, 2048)

        assert Image.open(io.BytesIO(result)).size == (2048, 1536)

    def test_cap_encoded_image_returns_none_for_undecodable(self):
        """寸法を確かめられない画像は送信対象から外す."""
        garbage = b"<html>not an image</html>"

        assert _cap_encoded_image(garbage, 384) is None

    @patch("coordinate_recorder.vlm_clothing_detector.requests")
    def test_match_with_wardrobe_caps_photo_without_touching_input(self, mock_requests):
        """送信する全身写真は縮むが、bbox の座標系になる入力配列は元のまま."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": json.dumps([])}]}}]
        }
        mock_response.raise_for_status.return_value = None
        mock_requests.post.return_value = mock_response

        image = np.zeros((4000, 3000, 3), dtype=np.uint8)
        detector = VLMClothingDetector(api_key="test-key")
        detector.match_with_wardrobe(
            image,
            [
                {
                    "id": "item-1",
                    "name": "サムネイル済",
                    "category": "tops",
                    "thumbnail": _jpeg_bytes(200, 200),
                }
            ],
        )

        # 全身写真はワードローブのサムネイルより後に積むので最後の inlineData
        parts = mock_requests.post.call_args.kwargs["json"]["contents"][0]["parts"]
        photo_b64 = [p["inlineData"]["data"] for p in parts if "inlineData" in p][-1]
        assert max(_decode_size(photo_b64)) == MAX_PHOTO_EDGE

        # ダウンスケールは送信用だけ。保存済の画像・bbox の座標系には触れない
        assert image.shape == (4000, 3000, 3)

    @patch("coordinate_recorder.vlm_clothing_detector.requests")
    def test_match_with_wardrobe_caps_thumbnails(self, mock_requests):
        """thumb_200 が無く原寸へフォールバックしたアイテムも上限に収める."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": json.dumps([])}]}}]
        }
        mock_response.raise_for_status.return_value = None
        mock_requests.post.return_value = mock_response

        detector = VLMClothingDetector(api_key="test-key")
        detector.match_with_wardrobe(
            np.zeros((600, 400, 3), dtype=np.uint8),
            [
                {
                    "id": "item-1",
                    "name": "サムネイル済",
                    "category": "tops",
                    "thumbnail": _jpeg_bytes(200, 200),
                },
                {
                    "id": "item-2",
                    "name": "原寸フォールバック",
                    "category": "tops",
                    "thumbnail": _jpeg_bytes(764, 1274),
                },
            ],
        )

        parts = mock_requests.post.call_args.kwargs["json"]["contents"][0]["parts"]
        images = [
            _decode_size(p["inlineData"]["data"]) for p in parts if "inlineData" in p
        ]
        # ワードローブ 2 枚 + 全身写真 1 枚
        assert images[0] == (200, 200)
        assert images[1] == (230, 384)
        assert images[2] == (400, 600)

    @patch("coordinate_recorder.vlm_clothing_detector.requests")
    def test_match_with_wardrobe_skips_unsizable_without_shifting_numbers(
        self, mock_requests
    ):
        """開けないサムネイルは飛ばし、VLM に渡す番号と解決先をずらさない."""
        matches = [{"candidates": [{"wardrobe_item_number": 2, "confidence": 0.9}]}]
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": json.dumps(matches)}]}}]
        }
        mock_response.raise_for_status.return_value = None
        mock_requests.post.return_value = mock_response

        detector = VLMClothingDetector(api_key="test-key")
        results = detector.match_with_wardrobe(
            np.zeros((600, 400, 3), dtype=np.uint8),
            [
                {
                    "id": "item-1",
                    "name": "正常",
                    "category": "tops",
                    "thumbnail": _jpeg_bytes(200, 200),
                },
                {
                    "id": "item-broken",
                    "name": "開けない",
                    "category": "tops",
                    "thumbnail": b"<html>not an image</html>",
                },
                {
                    "id": "item-3",
                    "name": "正常",
                    "category": "shoes",
                    "thumbnail": _jpeg_bytes(200, 200),
                },
            ],
        )

        parts = mock_requests.post.call_args.kwargs["json"]["contents"][0]["parts"]
        labels = [p["text"] for p in parts if p.get("text", "").startswith("#")]
        assert labels == ["#1 tops", "#2 shoes"]

        # #2 は詰めたあとの 2 番目＝item-3 に解決される（item-broken を飛ばした分がずれない）
        assert results[0]["wardrobe_candidates"][0]["wardrobe_item_id"] == "item-3"


def _gemini_response(text: str, **extra) -> dict:
    """text をそのまま返す Gemini 応答（成功形）."""
    return {
        "candidates": [
            {"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}
        ],
        **extra,
    }


class TestStripJsonFence:
    """```json フェンス剥がし."""

    def test_plain_json_untouched(self):
        """フェンスが無ければそのまま返す."""
        assert _strip_json_fence('[{"type": "jacket"}]') == '[{"type": "jacket"}]'

    def test_strips_json_fence(self):
        """```json フェンスを剥がす."""
        assert _strip_json_fence('```json\n[{"type": "jacket"}]\n```') == (
            '[{"type": "jacket"}]'
        )

    def test_strips_uppercase_language_tag(self):
        """言語タグの大小文字で剥がせなくならない."""
        assert _strip_json_fence("```JSON\n[]\n```") == "[]"

    def test_strips_unexpected_language_tag(self):
        """想定外の言語タグでも剥がす."""
        assert _strip_json_fence("```javascript\n[]\n```") == "[]"

    def test_strips_bare_fence(self):
        """言語指定の無いフェンスも剥がす."""
        assert _strip_json_fence("```\n[]\n```") == "[]"

    def test_keeps_inner_fence_like_text(self):
        """本文中の ``` は前後のフェンスとしてのみ扱う."""
        assert _strip_json_fence('```json\n["a```b"]\n```') == '["a```b"]'


class TestExtractMatches:
    """Gemini 応答からマッチ配列を取り出す."""

    def test_walks_parts_to_find_text(self):
        """text 以外のパーツが先頭でも text を拾う（parts[0] 決め打ちをやめた）."""
        result = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"inlineData": {"mimeType": "image/png", "data": "x"}},
                            {"text": '[{"type": "jacket"}]'},
                        ]
                    }
                }
            ]
        }

        assert _extract_matches(result) == [{"type": "jacket"}]

    def test_empty_candidates_raises_with_block_reason(self):
        """candidates が空なら blockReason を添えて弾く."""
        result = {"candidates": [], "promptFeedback": {"blockReason": "SAFETY"}}

        with pytest.raises(ValueError, match="SAFETY"):
            _extract_matches(result)

    def test_missing_candidates_key_raises(self):
        """candidates キーごと無い応答も弾く."""
        with pytest.raises(ValueError, match="no candidates"):
            _extract_matches({})

    def test_no_text_part_raises_with_finish_reason(self):
        """text パーツが無ければ finishReason を添えて弾く."""
        result = {
            "candidates": [{"content": {"parts": []}, "finishReason": "MAX_TOKENS"}]
        }

        with pytest.raises(ValueError, match="MAX_TOKENS"):
            _extract_matches(result)

    def test_warns_when_finish_reason_is_not_stop(self, caplog):
        """finishReason が STOP 以外なら warning を残してパースは続行する."""
        result = _gemini_response("[]")
        result["candidates"][0]["finishReason"] = "MAX_TOKENS"

        with caplog.at_level(logging.WARNING):
            assert _extract_matches(result) == []

        assert "MAX_TOKENS" in caplog.text

    def test_accepts_fenced_response(self):
        """フェンス付きの応答もパースできる."""
        result = _gemini_response('```json\n[{"type": "shoes"}]\n```')

        assert _extract_matches(result) == [{"type": "shoes"}]

    def test_wraps_single_match_dict(self):
        """配列でなく単品の dict が返ったら 1 件の配列として救う."""
        result = _gemini_response('{"type": "jacket", "candidates": []}')

        assert _extract_matches(result) == [{"type": "jacket", "candidates": []}]

    def test_rejects_wrapper_dict(self):
        """マッチの目印が無い包み dict は救わず弾く（偽の検出を作らない）."""
        result = _gemini_response('{"items": [{"type": "jacket"}]}')

        with pytest.raises(ValueError, match="expected a JSON array, got dict"):
            _extract_matches(result)

    def test_rejects_scalar(self):
        """配列でも dict でもない応答は型名を添えて弾く."""
        result = _gemini_response('"not a list"')

        with pytest.raises(ValueError, match="got str"):
            _extract_matches(result)

    def test_invalid_json_raises(self):
        """途中で切れた JSON は json.loads の例外がそのまま上がる."""
        result = _gemini_response('[{"type": "jack')

        with pytest.raises(ValueError):
            _extract_matches(result)


class TestMatchWithWardrobeResilience:
    """壊れた応答でも検出を全損させない."""

    @pytest.fixture()
    def detector(self):
        return VLMClothingDetector(api_key="test-key")

    @pytest.fixture()
    def sample_image(self):
        return np.zeros((600, 400, 3), dtype=np.uint8)

    @pytest.fixture()
    def wardrobe_items(self):
        return [
            {
                "id": "item-jacket",
                "name": "ネイビージャケット",
                "category": "outerwear",
                "subcategory": "jacket",
                "thumbnail": _jpeg_bytes(200, 200),
            }
        ]

    def _post(self, mock_requests, payload: dict, text: str = "") -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = payload
        mock_response.text = text
        mock_response.raise_for_status.return_value = None
        mock_requests.post.return_value = mock_response

    @patch("coordinate_recorder.vlm_clothing_detector.requests")
    def test_broken_response_logs_body_prefix(
        self, mock_requests, detector, sample_image, wardrobe_items, caplog
    ):
        """失敗時に応答先頭がログに残る（どの分岐で落ちたか後から分かる）."""
        body = '{"candidates": [], "promptFeedback": {"blockReason": "SAFETY"}}'
        self._post(mock_requests, json.loads(body), text=body)

        with caplog.at_level(logging.ERROR):
            assert detector.match_with_wardrobe(sample_image, wardrobe_items) == []

        assert "blockReason=SAFETY" in caplog.text
        assert "promptFeedback" in caplog.text

    @patch("coordinate_recorder.vlm_clothing_detector.requests")
    def test_log_body_is_truncated(
        self, mock_requests, detector, sample_image, wardrobe_items, caplog
    ):
        """応答本文は切り詰めてから残す."""
        body = "x" * 2000
        self._post(mock_requests, {"candidates": []}, text=body)

        with caplog.at_level(logging.ERROR):
            detector.match_with_wardrobe(sample_image, wardrobe_items)

        assert "x" * 500 in caplog.text
        assert "x" * 501 not in caplog.text

    @patch("coordinate_recorder.vlm_clothing_detector.requests")
    def test_request_failure_logs_without_response(
        self, mock_requests, detector, sample_image, wardrobe_items, caplog
    ):
        """リクエスト自体が失敗しても、応答未取得のまま落ちない."""
        mock_requests.post.side_effect = Exception("connection reset")

        with caplog.at_level(logging.ERROR):
            assert detector.match_with_wardrobe(sample_image, wardrobe_items) == []

        assert "connection reset" in caplog.text

    @patch("coordinate_recorder.vlm_clothing_detector.requests")
    def test_skips_non_object_match_entry(
        self, mock_requests, detector, sample_image, wardrobe_items, caplog
    ):
        """配列に混ざった非オブジェクト要素だけを飛ばし、残りは返す."""
        matches = [
            "unexpected",
            {"candidates": [{"wardrobe_item_number": 1, "confidence": 0.9}]},
        ]
        self._post(mock_requests, _gemini_response(json.dumps(matches)))

        with caplog.at_level(logging.WARNING):
            results = detector.match_with_wardrobe(sample_image, wardrobe_items)

        assert len(results) == 1
        assert results[0]["wardrobe_item_id"] == "item-jacket"
        assert "Skipping non-object match entry" in caplog.text

    @patch("coordinate_recorder.vlm_clothing_detector.requests")
    def test_logs_model_version_and_thoughts_tokens(
        self, mock_requests, detector, sample_image, wardrobe_items, caplog
    ):
        """modelVersion と thoughtsTokenCount をログに残す."""
        payload = _gemini_response(
            "[]",
            modelVersion="gemini-2.5-flash",
            usageMetadata={
                "promptTokenCount": 1200,
                "candidatesTokenCount": 340,
                "thoughtsTokenCount": 512,
            },
        )
        self._post(mock_requests, payload)

        with caplog.at_level(logging.INFO):
            detector.match_with_wardrobe(sample_image, wardrobe_items)

        assert "gemini-2.5-flash" in caplog.text
        assert "512 thoughts" in caplog.text
