/**
 * Component to display outfit items in a 2x2 grid for calendar cells
 */
import React, { useState } from 'react';
import { Shirt } from 'lucide-react';
import { OutfitItem } from '../../types/outfit';
import { ExtendedClothingItem } from '../../types/wardrobe';

interface OutfitItemGridProps {
  outfitItems?: OutfitItem[];
  apiUrl: string;
  size?: 'small' | 'medium' | 'large';
}

export const OutfitItemGrid: React.FC<OutfitItemGridProps> = ({
  outfitItems,
  // apiUrl, // 現在未使用
  size = 'small',
}) => {
  // State to track image load errors
  const [imageErrors, setImageErrors] = useState<{ [key: string]: boolean }>(
    {}
  );

  // Take up to 4 items for the 2x2 grid (with null safety)
  const displayItems = (outfitItems || []).slice(0, 4);

  // Fill remaining slots with empty placeholders
  const gridItems: (OutfitItem | null)[] = [...displayItems];
  while (gridItems.length < 4) {
    gridItems.push(null);
  }

  const handleImageError = (itemId: string) => {
    setImageErrors(prev => ({ ...prev, [itemId]: true }));
  };

  const getImageUrl = (clothingItem?: ExtendedClothingItem): string | null => {
    if (!clothingItem) {
      return null;
    }

    // Handle imageUrls in both camelCase and snake_case formats
    const imageUrls =
      clothingItem.imageUrls ||
      (clothingItem as unknown as Record<string, unknown>).image_urls;

    if (imageUrls) {
      // New structure with thumbnails
      if (typeof imageUrls === 'object' && !Array.isArray(imageUrls)) {
        const imageUrlsObj = imageUrls as Record<string, unknown>;

        // Prefer thumbnail for better performance
        const thumbnails = imageUrlsObj.thumbnails as Record<string, unknown>;
        if (thumbnails?.thumb_200) {
          return thumbnails.thumb_200 as string;
        }
        if (thumbnails?.thumb_400) {
          return thumbnails.thumb_400 as string;
        }
        if (imageUrlsObj.original) {
          return imageUrlsObj.original as string;
        }
      }
      // Legacy array structure
      else if (Array.isArray(imageUrls) && imageUrls.length > 0) {
        return imageUrls[0];
      }
    }

    // If no image URLs, we'll show a color square instead
    return null;
  };

  const getIconSize = () => {
    switch (size) {
      case 'small':
        return 'w-3 h-3'; // Increased proportionally
      case 'medium':
        return 'w-5 h-5';
      case 'large':
        return 'w-8 h-8';
      default:
        return 'w-3 h-3';
    }
  };

  return (
    <div className="grid grid-cols-2 gap-1 w-full aspect-square">
      {gridItems.map((outfitItem, index) => (
        <div
          key={outfitItem ? outfitItem.id : `empty-${index}`}
          className={`w-full aspect-square bg-gray-100 rounded-sm overflow-hidden border border-gray-200 flex items-center justify-center`}
        >
          {outfitItem ? (
            <>
              {(() => {
                // Handle both camelCase and snake_case property access
                const clothingItemData =
                  outfitItem.clothingItem ||
                  (outfitItem as unknown as Record<string, unknown>)
                    .clothing_item;
                const imageUrl = getImageUrl(
                  clothingItemData as ExtendedClothingItem | undefined
                );
                const hasImageError = imageErrors[outfitItem.id];

                return imageUrl && !hasImageError ? (
                  <img
                    src={imageUrl}
                    alt={(clothingItemData as ExtendedClothingItem)?.name || ''}
                    className="w-full h-full object-cover"
                    onError={() => handleImageError(outfitItem.id)}
                  />
                ) : (
                  <div
                    className="w-full h-full flex items-center justify-center"
                    style={{
                      backgroundColor:
                        (clothingItemData as ExtendedClothingItem)
                          ?.colorPrimary ||
                        (clothingItemData as unknown as Record<string, unknown>)
                          ?.color_primary ||
                        '#gray',
                    }}
                  >
                    <Shirt
                      className={`${getIconSize()} text-white opacity-70`}
                    />
                  </div>
                );
              })()}
            </>
          ) : (
            <div className="w-full h-full bg-gray-50 border-dashed border-gray-300 flex items-center justify-center">
              <div className={`${getIconSize()} text-gray-300`}>
                {/* Empty slot */}
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
};
