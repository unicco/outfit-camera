"""Context-aware outfit recommendation utilities."""

from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from ..settings import Settings
from ..utils.timezone_utils import TimezoneUtils
from ..wardrobe_models import ClothingCategory, ClothingItem, ClothingStatus
from .environment import WeatherSnapshot

logger = logging.getLogger(__name__)

FORMALITY_LABELS_JA = {
    "formal": "かっちり",
    "casual": "普段着",
    "relaxed": "おめかし",
    "sporty": "だらだら",
}

SEASONS = ["spring", "summer", "autumn", "winter"]
WEATHERS = ["sunny", "cloudy", "rainy", "snowy"]


@dataclass(slots=True)
class RecommendationContext:
    """Resolved context used for scoring."""

    current_season: str
    target_formality: str
    weather_condition: str
    temperature: Optional[float]
    occasion: Optional[str]
    user_schedule: Sequence[str]
    formality_reason: Optional[str] = None
    layer_requirement: Optional[str] = None
    temperature_reason: Optional[str] = None


@dataclass(slots=True)
class RecommendationItemData:
    """Intermediate representation of a wardrobe item evaluation."""

    item: ClothingItem
    score: float
    formality: Dict[str, float]
    season: Dict[str, float]
    weather: Dict[str, float]
    rationale: List[str] = field(default_factory=list)


@dataclass(slots=True)
class OutfitRecommendationData:
    """Combination of multiple items scored as one outfit."""

    score: float
    items: List[RecommendationItemData]
    suggested_for: str
    rationale: List[str]


class FormalityAnalyzer:
    """Heuristic formality estimator."""

    CATEGORY_WEIGHTS: Dict[ClothingCategory, Dict[str, float]] = {
        ClothingCategory.TOPS: {
            "formal": 0.35,
            "casual": 0.35,
            "relaxed": 0.2,
            "sporty": 0.1,
        },
        ClothingCategory.BOTTOMS: {
            "formal": 0.4,
            "casual": 0.3,
            "relaxed": 0.2,
            "sporty": 0.1,
        },
        ClothingCategory.OUTERWEAR: {
            "formal": 0.45,
            "casual": 0.25,
            "relaxed": 0.2,
            "sporty": 0.1,
        },
        ClothingCategory.SHOES: {
            "formal": 0.5,
            "casual": 0.25,
            "relaxed": 0.1,
            "sporty": 0.15,
        },
        ClothingCategory.ACCESSORIES: {
            "formal": 0.3,
            "casual": 0.3,
            "relaxed": 0.25,
            "sporty": 0.15,
        },
        ClothingCategory.BAG: {
            "formal": 0.35,
            "casual": 0.3,
            "relaxed": 0.2,
            "sporty": 0.15,
        },
    }

    def analyze(self, item: ClothingItem) -> tuple[Dict[str, float], List[str]]:
        reasons: List[str] = []
        weights = dict(self.CATEGORY_WEIGHTS.get(item.category, self._neutral()))

        # Occasion metadata directly maps to target styles
        for occasion in item.occasion or []:
            occasion_lower = occasion.lower()
            if occasion_lower in {"business", "formal", "office"}:
                weights["formal"] += 0.2
                reasons.append("ビジネス向けタグのため かっちり度を加点")
            elif occasion_lower in {"casual", "weekend"}:
                weights["casual"] += 0.15
                reasons.append("普段着向けのタグを検知")
            elif occasion_lower in {"date", "party", "dress"}:
                weights["relaxed"] += 0.2
                reasons.append("おめかし向けのタグを検知")
            elif occasion_lower in {"relax", "home", "lounge"}:
                weights["sporty"] += 0.2
                reasons.append("ラウンジ／おうちタグを検知")
            elif occasion_lower in {"athletic", "sport"}:
                weights["sporty"] += 0.2
                reasons.append("アクティブ用途のタグを検知")

        # Pattern influence
        pattern = (item.pattern or "").lower()
        if pattern:
            if pattern in {"solid", "無地", "plain"}:
                weights["formal"] += 0.1
                reasons.append("無地なので かっちり度を加点")
            elif pattern in {"stripe", "striped", "pinstripe"}:
                weights["formal"] += 0.05
                weights["casual"] += 0.05
                reasons.append("ストライプ柄で幅広いシーンに対応")
            elif pattern in {"floral", "print", "graphic", "チェック", "plaid"}:
                weights["casual"] += 0.15
                weights["relaxed"] += 0.1
                reasons.append("柄物のため普段着・おめかし度を強化")

        # Silhouette metadata
        silhouette = (item.silhouette_type or "").lower()
        if silhouette in {"tight", "slim", "tailored"}:
            weights["formal"] += 0.1
            reasons.append("シルエットが引き締まっているため かっちり度を加点")
        elif silhouette in {"loose", "oversized"}:
            weights["sporty"] += 0.15
            reasons.append("ゆったりシルエットで だらだら度を加点")

        # Color palette adjustments
        color_profile = _extract_color_profile(item)
        if color_profile.neutral_ratio >= 0.6:
            weights["formal"] += 0.1
            reasons.append("落ち着いた配色で かっちり度を加点")
        elif color_profile.vivid_ratio >= 0.5:
            weights["casual"] += 0.1
            reasons.append("鮮やかな色合いで 普段着度を加点")

        if color_profile.temperature == "warm":
            weights["relaxed"] += 0.05
            reasons.append("暖色寄りのため おめかし度を加点")
        elif color_profile.temperature == "cool":
            weights["formal"] += 0.05
            reasons.append("寒色寄りのため かっちり度を加点")

        normalized = _normalize_distribution(weights)
        return normalized, reasons

    @staticmethod
    def _neutral() -> Dict[str, float]:
        return {"formal": 0.25, "casual": 0.25, "relaxed": 0.25, "sporty": 0.25}


class SeasonSuitabilityAnalyzer:
    """Estimate seasonal affinity from metadata and colors."""

    MATERIAL_HINTS = {
        "wool": "winter",
        "cashmere": "winter",
        "down": "winter",
        "fleece": "winter",
        "linen": "summer",
        "cotton": "summer",
        "silk": "spring",
        "leather": "autumn",
    }

    def analyze(
        self, item: ClothingItem, color_profile: "ColorProfile"
    ) -> tuple[Dict[str, float], List[str]]:
        scores = {season: 0.25 for season in SEASONS}
        reasons: List[str] = []

        if item.season:
            for season in item.season:
                key = season.lower()
                if key in scores:
                    scores[key] += 0.4
                    reasons.append(f"ユーザー設定で{key}向けに指定")

        material = (item.material or "").lower()
        for keyword, season in self.MATERIAL_HINTS.items():
            if keyword in material:
                scores[season] += 0.2
                reasons.append(f"素材({keyword})から{season}向けと判断")

        sleeve = (item.sleeve_length or "").lower()
        if sleeve:
            if sleeve in {"long", "long_sleeve", "full"}:
                scores["winter"] += 0.1
                scores["autumn"] += 0.05
            elif sleeve in {"short", "short_sleeve"}:
                scores["summer"] += 0.15
                scores["spring"] += 0.05
            elif sleeve in {"sleeveless"}:
                scores["summer"] += 0.2

        # Color temperature hints
        if color_profile.temperature == "warm":
            scores["autumn"] += 0.1
            scores["winter"] += 0.05
        elif color_profile.temperature == "cool":
            scores["spring"] += 0.05
            scores["summer"] += 0.1

        return _normalize_distribution(scores), reasons


class WeatherSuitabilityAnalyzer:
    """Score items for weather conditions."""

    def analyze(
        self,
        item: ClothingItem,
        season_scores: Dict[str, float],
    ) -> tuple[Dict[str, float], List[str]]:
        scores = {weather: 0.25 for weather in WEATHERS}
        reasons: List[str] = []

        temperature_bias = {
            "winter": ("snowy", 0.3),
            "summer": ("sunny", 0.2),
            "spring": ("cloudy", 0.1),
            "autumn": ("rainy", 0.1),
        }
        for season, (weather, boost) in temperature_bias.items():
            scores[weather] += season_scores.get(season, 0.0) * boost

        material = (item.material or "").lower()
        if any(keyword in material for keyword in ("waterproof", "gore-tex", "shell")):
            scores["rainy"] += 0.3
            reasons.append("撥水素材のため雨天向き")
        if "wool" in material or "down" in material:
            scores["snowy"] += 0.25
            reasons.append("保温素材で寒冷地向け")
        if "linen" in material or "mesh" in material:
            scores["sunny"] += 0.25
            reasons.append("通気性素材で晴天・暑さに適応")

        if item.tags:
            for tag in item.tags:
                t = tag.lower()
                if "rain" in t or "umbrella" in t:
                    scores["rainy"] += 0.2
                if "heat" in t or "cool" in t:
                    scores["sunny"] += 0.15
                if "thermal" in t:
                    scores["snowy"] += 0.2

        return _normalize_distribution(scores), reasons


class TPORecommendationService:
    """High level orchestration for TPO recommendations."""

    def __init__(self, db: Session, settings: Optional[Settings] = None) -> None:
        self._db = db
        self._settings = settings
        self._formality = FormalityAnalyzer()
        self._season = SeasonSuitabilityAnalyzer()
        self._weather = WeatherSuitabilityAnalyzer()
        self._now = TimezoneUtils.now_jst()

    def build_context(
        self,
        weather: Optional[str],
        temperature: Optional[float],
        occasion: Optional[str],
        user_schedule: Optional[Sequence[str]],
        target_override: Optional[str] = None,
        formality_reason: Optional[str] = None,
    ) -> RecommendationContext:
        season = _determine_season(self._now)
        schedule = tuple(user_schedule or [])
        target = target_override or _resolve_formality(occasion, schedule)
        weather_condition = weather or "cloudy"
        if weather_condition not in WEATHERS:
            weather_condition = "cloudy"
        layer_requirement, temperature_reason = _resolve_layer_requirement(temperature)
        return RecommendationContext(
            current_season=season,
            target_formality=target,
            weather_condition=weather_condition,
            temperature=temperature,
            occasion=occasion,
            user_schedule=schedule,
            formality_reason=formality_reason,
            layer_requirement=layer_requirement,
            temperature_reason=temperature_reason,
        )

    def recommend_outfits(
        self,
        context: RecommendationContext,
        weather_snapshot: Optional[WeatherSnapshot],
        limit: int = 5,
    ) -> List[OutfitRecommendationData]:
        items = self._load_active_items()
        evaluated = [
            self._evaluate_item(item, context, weather_snapshot) for item in items
        ]
        evaluated = [entry for entry in evaluated if entry is not None]

        if not evaluated:
            logger.info("No active wardrobe items available for recommendations")
            return []

        outfits = self._compose_outfits(evaluated, context, limit)
        return outfits[:limit]

    # --- internal helpers -------------------------------------------------

    def _load_active_items(self) -> List[ClothingItem]:
        query = (
            self._db.query(ClothingItem)
            .filter(ClothingItem.status == ClothingStatus.ACTIVE)
            .filter(
                ClothingItem.category.in_(
                    [
                        ClothingCategory.TOPS,
                        ClothingCategory.BOTTOMS,
                        ClothingCategory.OUTERWEAR,
                        ClothingCategory.SHOES,
                        ClothingCategory.ACCESSORIES,
                        ClothingCategory.BAG,
                    ]
                )
            )
        )
        return query.all()

    def _evaluate_item(
        self,
        item: ClothingItem,
        context: RecommendationContext,
        weather_snapshot: Optional[WeatherSnapshot],
    ) -> Optional[RecommendationItemData]:
        formality_scores, formality_reasons = self._formality.analyze(item)
        color_profile = _extract_color_profile(item)
        season_scores, season_reasons = self._season.analyze(item, color_profile)
        weather_scores, weather_reasons = self._weather.analyze(item, season_scores)

        _maybe_update_json(item, "season_suitability", season_scores)
        _maybe_update_json(item, "weather_suitability", weather_scores)

        # Weighted scoring
        target_formality_score = formality_scores.get(context.target_formality, 0.0)
        current_season_score = season_scores.get(context.current_season, 0.0)
        weather_condition_score = weather_scores.get(context.weather_condition, 0.0)

        temperature_bonus = 0.0
        if context.temperature is not None:
            temperature_bonus = _temperature_alignment_bonus(
                context.temperature, season_scores
            )

        if weather_snapshot is not None:
            weather_bonus = _precipitation_bonus(weather_snapshot, weather_scores)
        else:
            weather_bonus = 0.0

        layer_bonus, layer_reason = _layer_match_bonus(item, context.layer_requirement)

        final_score = (
            target_formality_score * 0.5
            + current_season_score * 0.2
            + weather_condition_score * 0.2
            + temperature_bonus * 0.05
            + weather_bonus * 0.05
            + layer_bonus
        )

        rationale = formality_reasons + season_reasons + weather_reasons
        if temperature_bonus > 0:
            rationale.append("気温条件と適合")
        if weather_bonus > 0:
            rationale.append("天候予測と適合")
        if layer_reason:
            rationale.append(layer_reason)

        return RecommendationItemData(
            item=item,
            score=final_score,
            formality=formality_scores,
            season=season_scores,
            weather=weather_scores,
            rationale=rationale,
        )

    def _compose_outfits(
        self,
        evaluated: Sequence[RecommendationItemData],
        context: RecommendationContext,
        limit: int,
    ) -> List[OutfitRecommendationData]:
        by_category: Dict[ClothingCategory, List[RecommendationItemData]] = {}
        for entry in evaluated:
            by_category.setdefault(entry.item.category, []).append(entry)

        for entries in by_category.values():
            entries.sort(key=lambda e: e.score, reverse=True)

        tops = by_category.get(ClothingCategory.TOPS, [])[:3]
        bottoms = by_category.get(ClothingCategory.BOTTOMS, [])[:3]
        outers = by_category.get(ClothingCategory.OUTERWEAR, [])[:2]
        shoes = by_category.get(ClothingCategory.SHOES, [])[:2]
        bags = by_category.get(ClothingCategory.BAG, [])[:2]
        accessories = by_category.get(ClothingCategory.ACCESSORIES, [])[:2]

        combinations: List[List[RecommendationItemData]] = []
        outer_required = context.layer_requirement in {
            "light-outer",
            "mid-outer",
            "heavy-outer",
        }
        if tops and bottoms:
            outer_candidates: List[Optional[RecommendationItemData]] = []
            if outers:
                outer_candidates.extend(outers)
            if not outer_required:
                outer_candidates.append(None)
            if not outer_candidates:
                outer_candidates = [None]

            shoe_candidates: List[Optional[RecommendationItemData]] = (
                shoes[:] if shoes else [None]
            )
            bag_candidates: List[Optional[RecommendationItemData]] = (
                bags[:] if bags else [None]
            )

            for top_entry, bottom_entry in itertools.product(tops, bottoms):
                base_combo = [top_entry, bottom_entry]
                for outer_entry, shoe_entry, bag_entry in itertools.product(
                    outer_candidates,
                    shoe_candidates,
                    bag_candidates,
                ):
                    if outer_required and outer_entry is None:
                        continue
                    if (
                        context.layer_requirement in {"short", "long-sleeve"}
                        and outer_entry is not None
                    ):
                        continue
                    if shoes and shoe_entry is None:
                        continue
                    if bags and bag_entry is None:
                        continue

                    combo = list(base_combo)
                    if outer_entry is not None:
                        combo.append(outer_entry)
                    if shoe_entry is not None:
                        combo.append(shoe_entry)
                    if bag_entry is not None:
                        combo.append(bag_entry)
                    combinations.append(combo)
        else:
            # fallback: recommend top-scoring single pieces
            combinations = [[entry] for entry in evaluated[:limit]]

        outfit_recommendations: List[OutfitRecommendationData] = []
        target_label = FORMALITY_LABELS_JA.get(context.target_formality, "TPO")
        used_top_ids: set[str] = set()
        used_bottom_ids: set[str] = set()

        for combo in combinations:
            if not combo:
                continue
            avg_score = sum(entry.score for entry in combo) / len(combo)
            rationales = _build_outfit_rationales(combo, context)
            # Accessories: append best one if available and not already in combo
            categories = {entry.item.category for entry in combo}
            if outer_required and ClothingCategory.OUTERWEAR not in categories:
                continue
            if (
                context.layer_requirement in {"short", "long-sleeve"}
                and ClothingCategory.OUTERWEAR in categories
            ):
                continue
            if shoes and ClothingCategory.SHOES not in categories:
                continue
            if bags and ClothingCategory.BAG not in categories:
                continue

            top_ids = {
                entry.item.id
                for entry in combo
                if entry.item.category == ClothingCategory.TOPS
            }
            bottom_ids = {
                entry.item.id
                for entry in combo
                if entry.item.category == ClothingCategory.BOTTOMS
            }
            if (used_top_ids & top_ids) or (used_bottom_ids & bottom_ids):
                continue

            # Avoid combining patterned top and bottom together
            top_patterned = any(
                _is_patterned(entry.item.pattern)
                for entry in combo
                if entry.item.category == ClothingCategory.TOPS
            )
            bottom_patterned = any(
                _is_patterned(entry.item.pattern)
                for entry in combo
                if entry.item.category == ClothingCategory.BOTTOMS
            )
            if top_patterned and bottom_patterned:
                continue

            if accessories:
                accessory = accessories[0]
                if accessory not in combo:
                    combo_with_accessory = combo + [accessory]
                    outfit_recommendations.append(
                        OutfitRecommendationData(
                            score=avg_score * 0.98 + accessory.score * 0.02,
                            items=list(combo_with_accessory),
                            suggested_for=target_label,
                            rationale=rationales
                            + [f"アクセサリー『{accessory.item.name}』で仕上げを追加"],
                        )
                    )
            outfit_recommendations.append(
                OutfitRecommendationData(
                    score=avg_score,
                    items=list(combo),
                    suggested_for=target_label,
                    rationale=rationales,
                )
            )
            used_top_ids.update(top_ids)
            used_bottom_ids.update(bottom_ids)

        outfit_recommendations.sort(key=lambda r: r.score, reverse=True)
        if self._db.dirty:
            self._db.commit()
        return outfit_recommendations[:limit]


# --- helper utilities -----------------------------------------------------


@dataclass(slots=True)
class ColorProfile:
    temperature: str
    neutral_ratio: float
    vivid_ratio: float


def _extract_color_profile(item: ClothingItem) -> ColorProfile:
    palette_data = item.colors_palette or {}
    palette = []
    if isinstance(palette_data, dict):
        palette = palette_data.get("palette", [])
    elif isinstance(palette_data, list):
        palette = palette_data

    if not isinstance(palette, list) or not palette:
        return ColorProfile(temperature="neutral", neutral_ratio=0.5, vivid_ratio=0.5)

    neutral_count = 0
    vivid_count = 0
    warm_score = 0.0
    cool_score = 0.0
    total = 0

    for entry in palette:
        if not isinstance(entry, dict):
            continue
        hex_value = entry.get("hex")
        if not isinstance(hex_value, str) or not hex_value:
            continue
        rgb = _hex_to_rgb(hex_value)
        saturation = _saturation(rgb)
        if saturation < 0.15:
            neutral_count += 1
        else:
            vivid_count += 1
        warm_score += rgb[0] + rgb[1] * 0.5
        cool_score += rgb[2] + rgb[1] * 0.3
        total += 1

    if total == 0:
        return ColorProfile(temperature="neutral", neutral_ratio=0.5, vivid_ratio=0.5)

    temperature = "neutral"
    if warm_score > cool_score * 1.1:
        temperature = "warm"
    elif cool_score > warm_score * 1.1:
        temperature = "cool"

    return ColorProfile(
        temperature=temperature,
        neutral_ratio=neutral_count / total,
        vivid_ratio=vivid_count / total,
    )


def _hex_to_rgb(color: str) -> tuple[float, float, float]:
    color = color.lstrip("#")
    if len(color) == 3:
        color = "".join([c * 2 for c in color])
    try:
        r = int(color[0:2], 16) / 255.0
        g = int(color[2:4], 16) / 255.0
        b = int(color[4:6], 16) / 255.0
    except ValueError:
        return (0.5, 0.5, 0.5)
    return (r, g, b)


def _saturation(rgb: tuple[float, float, float]) -> float:
    max_val = max(rgb)
    min_val = min(rgb)
    if max_val == 0:
        return 0.0
    return (max_val - min_val) / max_val


def _normalize_distribution(values: Dict[str, float]) -> Dict[str, float]:
    total = sum(max(v, 0.0) for v in values.values())
    if total <= 0:
        size = len(values)
        return {key: 1.0 / size for key in values}
    return {key: max(val, 0.0) / total for key, val in values.items()}


def _determine_season(current: datetime) -> str:
    month = TimezoneUtils.to_jst(current).month
    if month in (3, 4, 5):
        return "spring"
    if month in (6, 7, 8):
        return "summer"
    if month in (9, 10, 11):
        return "autumn"
    return "winter"


def _resolve_formality(occasion: Optional[str], schedule: Sequence[str]) -> str:
    if occasion:
        key = occasion.lower()
        if key in {"business", "formal", "office"}:
            return "formal"
        if key in {"casual", "weekend"}:
            return "casual"
        if key in {"date", "friends", "outing"}:
            return "relaxed"
        if key in {"sport", "gym", "athletic"}:
            return "sporty"
    for entry in schedule:
        key = entry.lower()
        if "会議" in entry or key in {"meeting", "presentation"}:
            return "formal"
        if any(
            keyword in entry for keyword in ("取締役会", "打ち合わせ", "委員会", "収録")
        ):
            return "formal"
        if any(
            keyword in entry
            for keyword in ("お茶", "ランチ", "ご飯", "飲み会", "ディナー")
        ):
            return "relaxed"
        if "運動" in entry or key in {"run", "gym"}:
            return "sporty"
    return "casual"


def _resolve_layer_requirement(
    temperature: Optional[float],
) -> tuple[Optional[str], Optional[str]]:
    if temperature is None:
        return None, None

    if temperature >= 25:
        return "short", "体感温度が25℃以上のため 半袖アイテムで涼しく"
    if 20 <= temperature <= 24:
        return "long-sleeve", "体感温度が20〜24℃のため 長袖や薄手トップスが快適"
    if 15 <= temperature <= 19:
        return "light-outer", "体感温度が15〜19℃のため 薄手アウターを羽織ると安心"
    if 10 <= temperature <= 14:
        return "mid-outer", "体感温度が10〜14℃のため 中綿アウターが活躍します"
    return "heavy-outer", "体感温度が9℃以下のため ダウンなど厚手アウターが必要です"


def _temperature_alignment_bonus(
    temperature: float, season_scores: Dict[str, float]
) -> float:
    if temperature >= 26:
        return season_scores.get("summer", 0.0)
    if temperature <= 12:
        return season_scores.get("winter", 0.0)
    return max(season_scores.get("spring", 0.0), season_scores.get("autumn", 0.0))


def _precipitation_bonus(
    snapshot: WeatherSnapshot, weather_scores: Dict[str, float]
) -> float:
    if snapshot.umbrella_required:
        return weather_scores.get("rainy", 0.0)
    return weather_scores.get(snapshot.condition, 0.0)


def _build_outfit_rationales(
    combo: Sequence[RecommendationItemData], context: RecommendationContext
) -> List[str]:
    reasons = []
    for entry in combo:
        item = entry.item
        formal_score = entry.formality.get(context.target_formality, 0.0)
        season_score = entry.season.get(context.current_season, 0.0)
        weather_score = entry.weather.get(context.weather_condition, 0.0)
        reasons.append(
            "・{name}: フォーマル度{formal:.0%} / 季節適性{season:.0%} / 天気適性{weather:.0%}".format(
                name=item.name,
                formal=formal_score,
                season=season_score,
                weather=weather_score,
            )
        )
    return reasons


def _maybe_update_json(
    item: ClothingItem, attribute: str, value: Dict[str, float]
) -> None:
    existing = getattr(item, attribute, None)
    if not isinstance(existing, dict) or _distribution_changed(existing, value):
        setattr(item, attribute, value)


def _distribution_changed(old: Dict[str, float], new: Dict[str, float]) -> bool:
    for key, new_value in new.items():
        if abs(new_value - float(old.get(key, 0.0))) > 0.05:
            return True
    return False


def _layer_match_bonus(
    item: ClothingItem, layer_requirement: Optional[str]
) -> tuple[float, Optional[str]]:
    if not layer_requirement:
        return 0.0, None

    category = item.category
    sleeve = (getattr(item, "sleeve_length", "") or "").lower()
    seasons = {season.lower() for season in (item.season or [])}
    material = (item.material or "").lower()

    def is_short_sleeve() -> bool:
        if sleeve in {"short", "short_sleeve", "半袖", "short-sleeved"}:
            return True
        if sleeve in {"sleeveless", "ノースリーブ"}:
            return True
        return "summer" in seasons

    def is_long_sleeve() -> bool:
        if sleeve in {"long", "long_sleeve", "長袖", "long-sleeved"}:
            return True
        return bool(seasons & {"spring", "autumn", "winter"})

    def outer_weight(match_seasons: set[str]) -> bool:
        if category != ClothingCategory.OUTERWEAR:
            return False
        if match_seasons & seasons:
            return True
        if "down" in material and "winter" in match_seasons:
            return True
        if "fleece" in material and "winter" in match_seasons:
            return True
        return False

    if layer_requirement == "short":
        if category == ClothingCategory.OUTERWEAR:
            return -0.15, "暑さが想定されるためアウターは避けたい気温"
        if category == ClothingCategory.TOPS and is_short_sleeve():
            return 0.08, "半袖トップスが快適な気温帯"
        if category == ClothingCategory.TOPS and is_long_sleeve():
            return -0.05, "長袖よりも半袖が過ごしやすい気温"

    if layer_requirement == "long-sleeve":
        if category == ClothingCategory.TOPS and is_long_sleeve():
            return 0.07, "長袖トップスが快適な気温帯"
        if category == ClothingCategory.TOPS and is_short_sleeve():
            return -0.06, "半袖では肌寒く感じる気温"
        if category == ClothingCategory.OUTERWEAR:
            return -0.05, "薄手トップスで十分な気温"

    if layer_requirement == "light-outer":
        if outer_weight({"spring", "summer"}):
            return 0.1, "薄手アウターを羽織ると安心な気温帯"
        if category == ClothingCategory.OUTERWEAR:
            return 0.05, "軽量アウターで調整したい気温"
        if category == ClothingCategory.TOPS and is_short_sleeve():
            return -0.05, "薄手アウターが欲しい気温帯"

    if layer_requirement == "mid-outer":
        if outer_weight({"autumn"}):
            return 0.12, "中綿アウターが活躍する気温帯"
        if category == ClothingCategory.OUTERWEAR:
            return 0.08, "アウターで体温調節したい気温"
        if category == ClothingCategory.TOPS:
            return -0.07, "トップスだけでは肌寒い気温"

    if layer_requirement == "heavy-outer":
        if outer_weight({"winter"}):
            return 0.15, "厚手アウターが必須の気温帯"
        if category == ClothingCategory.OUTERWEAR:
            return 0.1, "アウターの防寒が必要"
        if category == ClothingCategory.TOPS:
            return -0.1, "トップスだけでは厳しい寒さ"

    return 0.0, None


def _is_patterned(pattern: Optional[str]) -> bool:
    if not pattern:
        return False
    normalized = pattern.strip().lower()
    if normalized in {"", "solid", "無地", "plain"}:
        return False
    return True
