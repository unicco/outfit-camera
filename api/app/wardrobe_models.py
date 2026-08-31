"""Wardrobe management database models."""

import enum
import uuid
from typing import Optional

from sqlalchemy import (
    JSON,
    Column,
    Date,
    DateTime,
    Enum,
    Float,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.sql import func

from .models import Base


class ClothingStatus(str, enum.Enum):
    """Status values for clothing items."""

    ACTIVE = "ACTIVE"
    DISPOSAL_CONSIDERATION = "DISPOSAL_CONSIDERATION"
    SELLING = "SELLING"
    DISPOSED = "DISPOSED"


class ClothingCategory(str, enum.Enum):
    """Category values for clothing items."""

    TOPS = "TOPS"
    BOTTOMS = "BOTTOMS"
    SHOES = "SHOES"
    OUTERWEAR = "OUTERWEAR"
    ACCESSORIES = "ACCESSORIES"
    UNDERWEAR = "UNDERWEAR"
    DRESSES = "DRESSES"
    SETS = "SETS"
    BAG = "BAG"
    OTHER = "OTHER"


class ClothingItem(Base):
    """Represents individual clothing pieces in the wardrobe inventory."""

    __tablename__ = "clothing_items"
    __table_args__ = (
        # パフォーマンス最適化のためのインデックス
        Index("idx_clothing_status", "status"),
        Index("idx_clothing_usage_count", "usage_count"),
        Index("idx_clothing_purchase_price", "purchase_price"),
        Index("idx_clothing_purchase_date", "purchase_date"),
        # 複合インデックス（ステータスとカテゴリでよくフィルタするため）
        Index("idx_clothing_status_category", "status", "category"),
    )

    # Primary key (use String for SQLite compatibility)
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Basic information
    name = Column(String(255), nullable=False)  # User-friendly name
    category: Column[ClothingCategory] = Column(
        Enum(ClothingCategory, name="clothingcategory"), nullable=False, index=True
    )  # shirt, pants, shoes, etc.
    subcategory = Column(String(50), nullable=True)  # oxford, t-shirt, jeans, chinos
    brand = Column(String(100), nullable=True)

    # Colors and patterns
    colors_palette = Column(
        JSON, nullable=True
    )  # 5色パレット {"palette": [{"hex": "#FF5733", "position": 1}, ...], "extraction_method": "eyedropper"}
    pattern = Column(String(50), nullable=True)  # solid, striped, checkered, floral

    # Physical properties
    material = Column(String(100), nullable=True)  # cotton, wool, polyester, leather
    size = Column(String(20), nullable=True)  # S, M, L, XL, or specific measurements

    # Purchase information
    purchase_date = Column(Date, nullable=True)
    purchase_price = Column(Float, nullable=True)
    purchase_location = Column(String(200), nullable=True)

    # Sale information (issue #823)
    sale_platform = Column(String(50), nullable=True)  # mercari, zozoused, etc.
    sale_price = Column(Float, nullable=True)  # 売却価格
    sale_commission = Column(Float, nullable=True)  # 手数料
    disposal_date = Column(Date, nullable=True)  # 処分日

    # Usage information
    season = Column(JSON, nullable=True)  # ["spring", "summer", "autumn", "winter"]
    occasion = Column(
        JSON, nullable=True
    )  # ["casual", "business", "formal", "athletic"]

    # Care and maintenance
    care_instructions = Column(Text, nullable=True)

    # Status
    status: Column[ClothingStatus] = Column(
        Enum(ClothingStatus, name="clothingstatus"),
        nullable=False,
        default=ClothingStatus.ACTIVE,
    )  # active, stored, donated, retired

    # Images
    image_urls = Column(JSON, nullable=True)  # List of image URLs
    image_metadata = Column(
        JSON, nullable=True
    )  # Detailed image metadata including thumbnails

    # Additional metadata
    tags = Column(JSON, nullable=True)  # Custom tags for search/filter

    # Jina AI embedding fields
    embedding_vector = Column(JSON, nullable=True)  # Jina embedding as JSON array
    embedding_computed_at = Column(
        DateTime(timezone=True), nullable=True
    )  # When embedding was computed
    embedding_model_version = Column(
        String(50), nullable=True
    )  # Model version used (e.g., "jina-embeddings-v4")

    # 属性検出フィールド (Issue #1045)
    silhouette_type = Column(String(50), nullable=True)  # tight, regular, loose
    silhouette_features = Column(
        JSON, nullable=True
    )  # アスペクト比、solidity等の詳細特徴量
    sleeve_length = Column(
        String(50), nullable=True
    )  # long_sleeve, short_sleeve, sleeveless
    neckline_type = Column(
        String(50), nullable=True
    )  # round, v_neck, collar等（将来実装）
    attributes_metadata = Column(JSON, nullable=True)  # その他の属性情報

    # Issue #1059 統合フィールド
    pattern_type = Column(String(50), nullable=True)  # striped, gradient, rainbow, etc
    design_complexity = Column(String(20), nullable=True)  # simple, moderate, complex
    color_harmony_score = Column(Float, nullable=True)  # 0.0-1.0 (将来実装)

    # Wear history fields
    last_used_date = Column(Date, nullable=True)  # Last time this item was worn
    default_usage_count = Column(
        Integer, nullable=True, default=0
    )  # Historical usage frequency
    usage_count = Column(
        Integer, nullable=True, default=0
    )  # Current usage count from outfit records

    # TPO 推薦用の分析結果
    season_suitability = Column(JSON, nullable=True)
    weather_suitability = Column(JSON, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Backward compatibility properties for color access
    @property
    def color_primary(self) -> str:
        """Get primary color from colors_palette for backward compatibility."""
        colors_palette = getattr(self, "colors_palette", None)
        if colors_palette and isinstance(colors_palette, dict):
            palette = colors_palette.get("palette", [])
            if palette and isinstance(palette, list) and len(palette) > 0:
                first_color = palette[0]
                if isinstance(first_color, dict) and "hex" in first_color:
                    hex_value = first_color["hex"]
                    return hex_value if isinstance(hex_value, str) else "#808080"
        return "#808080"  # Default gray if no color found

    @color_primary.setter
    def color_primary(self, value: str) -> None:
        """Set primary color by updating colors_palette."""
        colors_palette = getattr(self, "colors_palette", None)
        if not colors_palette:
            self.colors_palette = {"palette": [], "extraction_method": "manual"}  # type: ignore
            colors_palette = self.colors_palette

        if isinstance(colors_palette, dict) and "palette" not in colors_palette:
            colors_palette["palette"] = []

        # Update first color or add new one
        if isinstance(colors_palette, dict) and isinstance(
            colors_palette.get("palette"), list
        ):
            palette = colors_palette["palette"]
            if len(palette) > 0:
                palette[0] = {"hex": value, "position": 1}
            else:
                palette.append({"hex": value, "position": 1})

    @property
    def color_secondary(self) -> str | None:
        """Get secondary color from colors_palette for backward compatibility."""
        colors_palette = getattr(self, "colors_palette", None)
        if colors_palette and isinstance(colors_palette, dict):
            palette = colors_palette.get("palette", [])
            if palette and isinstance(palette, list) and len(palette) > 1:
                second_color = palette[1]
                if isinstance(second_color, dict) and "hex" in second_color:
                    hex_value = second_color["hex"]
                    return hex_value if isinstance(hex_value, str) else None
        return None  # No secondary color

    @color_secondary.setter
    def color_secondary(self, value: str) -> None:
        """Set secondary color by updating colors_palette."""
        colors_palette = getattr(self, "colors_palette", None)
        if not colors_palette:
            self.colors_palette = {"palette": [], "extraction_method": "manual"}  # type: ignore
            colors_palette = self.colors_palette

        if isinstance(colors_palette, dict) and "palette" not in colors_palette:
            colors_palette["palette"] = []

        # Ensure we have at least one color (primary)
        if isinstance(colors_palette, dict) and isinstance(
            colors_palette.get("palette"), list
        ):
            palette = colors_palette["palette"]
            while len(palette) < 2:
                if len(palette) == 0:
                    palette.append({"hex": "#808080", "position": 1})
                else:
                    palette.append({"hex": "#C0C0C0", "position": 2})

            # Update second color
            if len(palette) >= 2:
                palette[1] = {"hex": value, "position": 2}

    @property
    def sale_net_amount(self) -> Optional[float]:
        """売却後の手取り金額（売却価格 - 手数料）."""
        if self.sale_price is None:
            return None
        commission = self.sale_commission or 0.0
        return float(self.sale_price - commission)

    @property
    def sale_profit_loss(self) -> Optional[float]:
        """売却での損益（手取り金額 - 購入価格）."""
        if self.sale_price is None or self.purchase_price is None:
            return None
        net_amount = self.sale_net_amount
        if net_amount is None:
            return None
        return float(net_amount - self.purchase_price)

    @property
    def cost_per_wear(self) -> Optional[float]:
        """1回あたりの金額（issue #823要件）.

        計算式: (購入価格 - 売却手取り金額) / 着用回数
        売却していない場合は: 購入価格 / 着用回数
        """
        if self.purchase_price is None:
            return None

        # Total wear count calculation
        total_wears = (self.default_usage_count or 0) + (self.usage_count or 0)
        if total_wears <= 0:
            return None

        if self.sale_price is not None:
            # 売却済の場合：購入価格 - 売却手取り金額
            net_amount = self.sale_net_amount or 0.0
            cost_basis = self.purchase_price - net_amount
        else:
            # 未売却の場合：購入価格のみ
            cost_basis = self.purchase_price

        return float(cost_basis / total_wears)

    # Indexes for performance
    __table_args__ = (
        Index("idx_clothing_category", "category"),
        Index("idx_clothing_status", "status"),
        Index("idx_clothing_category_status", "category", "status"),
    )
