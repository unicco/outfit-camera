# Re-export models from models.py for backward compatibility
from .models import OutfitRecord, OutfitItem, OutfitExternalRentalItem

__all__ = ["OutfitRecord", "OutfitItem", "OutfitExternalRentalItem"]
