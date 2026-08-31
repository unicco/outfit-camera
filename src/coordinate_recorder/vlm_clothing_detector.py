"""VLM（Vision Language Model）を使用した衣類検出モジュール.

Gemini API に全身写真とワードローブのサムネイルを一括で送り、着ているアイテムを
ワードローブのどれに該当するか紐づけて返す。Roboflow では検出困難な重ね着・
ワンピース・靴・バッグにも対応。

API キーは GEMINI_API_KEY から取得する。
"""

import base64
import io
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

import numpy as np
import requests
from PIL import Image

logger = logging.getLogger(__name__)

# API エンドポイント
GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/"
    "models/gemini-2.5-flash:generateContent"
)

# VLM へ送るときだけの長辺上限。保存済の画像・bbox の座標系には触れない。
# 上限値の根拠と「一律ダウンスケールは Gemini のトークンを減らさない」実測は
# docs/api/features/vlm-image-tokens.md
MAX_PHOTO_EDGE = 2048
MAX_WARDROBE_EDGE = 384

JPEG_QUALITY = 85


def _encode_jpeg(pil_image: Image.Image, max_edge: int) -> bytes:
    """長辺が max_edge を超えていれば縮めてから JPEG バイト列にする."""
    width, height = pil_image.size
    if max(width, height) > max_edge:
        scale = max_edge / max(width, height)
        pil_image = pil_image.resize(
            (max(1, round(width * scale)), max(1, round(height * scale))),
            Image.LANCZOS,
        )

    buffer = io.BytesIO()
    pil_image.save(buffer, format="JPEG", quality=JPEG_QUALITY)
    return buffer.getvalue()


def _cap_encoded_image(image_bytes: bytes, max_edge: int) -> Optional[bytes]:
    """エンコード済画像を長辺 max_edge に収める。収まっていれば原本を返す.

    thumb_200 は既に上限内なので、再エンコードによる二重圧縮を避ける。
    寸法を確かめられなかった画像は None を返して送信対象から外す。原本を送る
    フォールバックにすると、Pillow が開けないほど巨大な画像＝最も上限が要る入力で
    ガードがすり抜ける。
    """
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            if max(img.size) <= max_edge:
                return image_bytes
            return _encode_jpeg(img.convert("RGB"), max_edge)
    except Exception as e:
        logger.warning("Skipping wardrobe image that could not be sized: %s", e)
        return None


# ```json フェンス（responseMimeType 指定下では通常付かないが、付いたら剥がす）。
# 言語タグは中身を見ずに丸ごと飛ばす。json / JSON / 何も無し のどれで来ても
# 剥がせないと、この関数が救おうとしている全損にそのまま落ちる
_JSON_FENCE_RE = re.compile(r"^```[A-Za-z0-9_+-]*\s*(.*?)\s*```$", re.DOTALL)

# 配列でなく単品の dict が返るゆらぎを救うための目印。ここを持たない dict
# （{"items": [...]} のような包み）は救わない。包みを 1 件として扱うと
# type=unknown の偽の検出をでっち上げることになる
_MATCH_KEYS = ("candidates", "type", "wardrobe_item_number")


def _strip_json_fence(text: str) -> str:
    """```json フェンスが付いていれば剥がす."""
    stripped = text.strip()
    match = _JSON_FENCE_RE.match(stripped)
    return match.group(1) if match else stripped


def _extract_matches(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Gemini の応答からマッチ配列を取り出す.

    ここが空リストや例外になると、呼び出し元は検出そのものを失敗として扱う
    （api/app/routers/ai_detection.py の `if not vlm_matches: return None`）。
    フォールバック先が無いので、素通しでなく理由を添えて弾く。

    Raises:
        ValueError: 応答からマッチ配列を取り出せなかった場合（理由つき）

    """
    candidates = result.get("candidates") or []
    if not candidates:
        block_reason = result.get("promptFeedback", {}).get("blockReason", "unknown")
        raise ValueError(f"no candidates in response (blockReason={block_reason})")

    candidate = candidates[0]
    finish_reason = candidate.get("finishReason")
    # thinking トークンも出力枠を食うため、品目が増えると打ち切られうる
    if finish_reason not in (None, "STOP"):
        logger.warning(
            "VLM response did not finish normally (finishReason=%s)", finish_reason
        )

    parts = candidate.get("content", {}).get("parts") or []
    text = next((p["text"] for p in parts if isinstance(p, dict) and "text" in p), None)
    if text is None:
        raise ValueError(
            f"no text part in response (parts={len(parts)}, "
            f"finishReason={finish_reason})"
        )

    matches = json.loads(_strip_json_fence(text))

    if isinstance(matches, dict) and any(k in matches for k in _MATCH_KEYS):
        matches = [matches]
    if not isinstance(matches, list):
        raise ValueError(f"expected a JSON array, got {type(matches).__name__}")

    return matches


class VLMClothingDetector:
    """Gemini ベースの衣類検出クラス."""

    def __init__(self, api_key: Optional[str] = None):
        """初期化.

        Args:
            api_key: Gemini API キー（省略時は環境変数 GEMINI_API_KEY から取得）

        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")

        if not self.api_key:
            logger.warning("GEMINI_API_KEY not set, VLM detection disabled")
        else:
            logger.info("VLM detection enabled: gemini")

    @property
    def is_available(self) -> bool:
        """API キーが設定されているかどうか."""
        return self.api_key is not None

    def match_with_wardrobe(
        self,
        image: np.ndarray,
        wardrobe_items: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """全身写真とワードローブ全アイテムを一括で VLM に送り、マッチングを行う.

        Args:
            image: 全身写真 (RGB numpy array)
            wardrobe_items: ワードローブアイテムのリスト。各アイテムは以下を含む:
                - id: アイテム ID
                - name: アイテム名
                - category: カテゴリ
                - subcategory: サブカテゴリ
                - thumbnail: サムネイル画像バイト列 (JPEG)

        Returns:
            マッチング結果リスト。各アイテム:
            - wardrobe_item_id: マッチしたワードローブアイテムの ID (null=新アイテム)
            - type: 衣類の種類
            - color: 色の説明
            - position: 位置
            - layer: レイヤー順
            - confidence: 確信度

        """
        if not self.is_available or not wardrobe_items:
            return []

        response: Optional[requests.Response] = None

        try:
            # 全身写真を base64 エンコード
            photo_b64 = base64.b64encode(
                _encode_jpeg(Image.fromarray(image), MAX_PHOTO_EDGE)
            ).decode()

            # ワードローブアイテムのパーツを構築
            parts: List[Dict[str, Any]] = []
            item_index: List[Dict[str, Any]] = []

            for item in wardrobe_items:
                thumbnail = _cap_encoded_image(item["thumbnail"], MAX_WARDROBE_EDGE)
                if thumbnail is None:
                    continue

                # 番号は item_index の位置に合わせる。VLM が返す番号をここで引くので、
                # スキップした分を詰めないと解決先が 1 つずれる
                number = len(item_index) + 1
                subcategory = item.get("subcategory", "")
                label = f'#{number} {item["category"]} {subcategory}'.strip()
                parts.append({"text": label})
                parts.append(
                    {
                        "inlineData": {
                            "mimeType": "image/jpeg",
                            "data": base64.b64encode(thumbnail).decode(),
                        }
                    }
                )
                item_index.append(item)

            # 全身写真とプロンプトを追加
            parts.append({"text": "\n---\n今日の全身写真:"})
            parts.append({"inlineData": {"mimeType": "image/jpeg", "data": photo_b64}})
            parts.append({"text": self._build_matching_prompt()})

            response = requests.post(
                f"{GEMINI_API_URL}?key={self.api_key}",
                json={
                    "contents": [{"parts": parts}],
                    "generationConfig": {
                        "temperature": 0.1,
                        "responseMimeType": "application/json",
                    },
                },
                timeout=60,
            )
            response.raise_for_status()

            result = response.json()
            matches = _extract_matches(result)

            usage = result.get("usageMetadata", {})
            # thoughtsTokenCount は出力課金なのに candidatesTokenCount に含まれない。
            # モデルを上げるときの出力コストはこれを足さないと見えない
            logger.info(
                "VLM wardrobe matching: %d items matched "
                "(model: %s, tokens: %d input, %d output, %d thoughts)",
                len(matches),
                result.get("modelVersion", "unknown"),
                usage.get("promptTokenCount", 0),
                usage.get("candidatesTokenCount", 0),
                usage.get("thoughtsTokenCount", 0),
            )

            # アイテム番号を ID に変換
            results = []
            for m in matches:
                # 1 要素の型崩れで検出を全損させない
                if not isinstance(m, dict):
                    logger.warning("Skipping non-object match entry: %.100s", m)
                    continue

                candidates = m.get("candidates", [])

                # 旧形式（wardrobe_item_number 直接）との後方互換
                if not candidates and "wardrobe_item_number" in m:
                    num = m.get("wardrobe_item_number")
                    conf = float(m.get("confidence", 0.8))
                    if num is not None:
                        candidates = [{"wardrobe_item_number": num, "confidence": conf}]

                # 候補を ID に変換
                resolved_candidates = []
                for c in candidates:
                    num = c.get("wardrobe_item_number")
                    if num is not None and 1 <= num <= len(item_index):
                        resolved_candidates.append(
                            {
                                "wardrobe_item_id": item_index[num - 1]["id"],
                                "confidence": float(c.get("confidence", 0.8)),
                            }
                        )

                # 最も confidence が高い候補の情報をメインに使う
                best_confidence = (
                    resolved_candidates[0]["confidence"] if resolved_candidates else 0.8
                )
                best_wardrobe_id = (
                    resolved_candidates[0]["wardrobe_item_id"]
                    if resolved_candidates
                    else None
                )

                results.append(
                    {
                        "wardrobe_item_id": best_wardrobe_id,
                        "wardrobe_candidates": resolved_candidates,
                        "type": m.get("type", "unknown"),
                        "color": m.get("color", ""),
                        "color_hex": m.get("color_hex", ""),
                        "position": m.get("position", "full_body"),
                        "layer": m.get("layer", ""),
                        "confidence": best_confidence,
                    }
                )

            return results

        except Exception as e:
            # 応答本文の先頭を残さないと、上のどの分岐で落ちたか後から分からない
            logger.error(
                "VLM wardrobe matching failed: %s: %.500s",
                e,
                getattr(response, "text", None),
            )
            return []

    def _build_matching_prompt(self) -> str:
        """ワードローブマッチング用プロンプトを構築."""
        return """上記はワードローブに登録された全アイテムの画像です。
最後の写真は今日の全身写真です。

全身写真の人物が着ている/持っている各アイテムについて、ワードローブのどれに該当するか特定してください。
似たアイテムが複数ある場合は、候補を最大3つまで挙げてください。

JSON 配列で返してください:
[
  {
    "candidates": [
      {"wardrobe_item_number": 該当するアイテム番号（整数）, "confidence": 0.0-1.0},
      ...最大3件。該当なしの場合は空配列 []
    ],
    "type": "衣類の種類。以下から選択: coat, jacket, vest, dress, shirt, sweater, t-shirt, cardigan, hoodie, pants, skirt, shoes, sneakers, boot, sandal, bag, hat, belt, scarf",
    "color": "色の説明（英語）",
    "color_hex": "メインカラーの hex コード（例: #1B2A4A）",
    "position": "位置（upper_body / lower_body / full_body / feet / hand / head / waist）",
    "layer": "レイヤー順（outer が最も外側、1, 2, 3... で内側へ）"
  }
]

ルール:
- 写真に写っている衣類1つにつき1エントリ（同じ服を複数回記載しない）
- 重ね着: 外側のアウターと内側のインナーは別アイテムなので別エントリにする
- 靴のマッチング: 全身写真では靴が小さく写るため、色・形状・素材の特徴に注目してワードローブと照合する
- ワードローブに該当がなければ candidates を空配列にする
- candidates 内は confidence 降順で並べる
- color_hex は衣類の最も目立つ色の hex コードを返す（柄物の場合はベースカラー）
- JSON 配列のみを返す（説明文不要）"""

    def _position_to_bbox(
        self, position: str, img_w: int, img_h: int
    ) -> Dict[str, float]:
        """位置情報からおおよその bbox を推定.

        人物が画像の中央にいると仮定し、位置に応じたバウンディングボックスを返す。

        Args:
            position: 衣類の位置（upper_body, lower_body, etc.）
            img_w: 画像の幅
            img_h: 画像の高さ

        Returns:
            bbox 辞書 (x, y, width, height) — x, y は中心座標

        """
        center_x = img_w / 2
        body_width = img_w * 0.6  # 体幅は画像幅の約 60%

        position_map = {
            "upper_body": {
                "x": center_x,
                "y": img_h * 0.30,
                "width": body_width,
                "height": img_h * 0.35,
            },
            "lower_body": {
                "x": center_x,
                "y": img_h * 0.65,
                "width": body_width,
                "height": img_h * 0.35,
            },
            "full_body": {
                "x": center_x,
                "y": img_h * 0.50,
                "width": body_width,
                "height": img_h * 0.70,
            },
            "feet": {
                "x": center_x,
                "y": img_h * 0.90,
                "width": body_width * 0.7,
                "height": img_h * 0.15,
            },
            "hand": {
                "x": img_w * 0.20,
                "y": img_h * 0.55,
                "width": body_width * 0.5,
                "height": img_h * 0.30,
            },
            "head": {
                "x": center_x,
                "y": img_h * 0.10,
                "width": body_width * 0.5,
                "height": img_h * 0.15,
            },
            "waist": {
                "x": center_x,
                "y": img_h * 0.50,
                "width": body_width,
                "height": img_h * 0.10,
            },
        }

        # 未知の位置は full_body として扱う
        return position_map.get(
            position,
            {
                "x": center_x,
                "y": img_h * 0.50,
                "width": body_width,
                "height": img_h * 0.70,
            },
        )
