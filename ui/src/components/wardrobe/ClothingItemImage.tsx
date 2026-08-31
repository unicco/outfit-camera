import React, { useState } from 'react';
import { cn } from '@/lib/utils';
import { Image as ImageIcon } from 'lucide-react';

interface Thumbnails {
  thumb_200: string;
  thumb_400: string;
}

interface ClothingItemImageProps {
  imageUrl: string;
  thumbnails?: Thumbnails;
  alt: string;
  className?: string;
  priority?: boolean;
  onClick?: () => void;
}

export function ClothingItemImage({
  imageUrl,
  thumbnails,
  alt,
  className,
  priority = false,
  onClick,
}: ClothingItemImageProps) {
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(false);
  const [currentSrc, setCurrentSrc] = useState(() => {
    // Start with smallest thumbnail if available
    return thumbnails?.thumb_200 || imageUrl;
  });

  // Update currentSrc when imageUrl or thumbnails change
  React.useEffect(() => {
    const newSrc = thumbnails?.thumb_200 || imageUrl;
    if (newSrc !== currentSrc) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- 親 props 変化に追従した画像 src 切替とロード状態リセット
      setCurrentSrc(newSrc);
      setIsLoading(true);
      setError(false);
    }
  }, [imageUrl, thumbnails?.thumb_200, thumbnails?.thumb_400, currentSrc]);

  // Progressive loading: load larger image after thumbnail
  const handleLoad = () => {
    setIsLoading(false);

    // If we loaded a thumbnail and have a larger version, upgrade
    if (currentSrc === thumbnails?.thumb_200 && thumbnails?.thumb_400) {
      // Preload larger thumbnail
      const img = new Image();
      img.src = thumbnails.thumb_400;
      img.onload = () => {
        setCurrentSrc(thumbnails.thumb_400);
      };
    } else if (currentSrc === thumbnails?.thumb_400 && imageUrl) {
      // Optionally preload full image for detail views
      if (priority) {
        const img = new Image();
        img.src = imageUrl;
      }
    }
  };

  const handleError = () => {
    setIsLoading(false);
    setError(true);
  };

  return (
    <div
      className={cn('relative overflow-hidden bg-gray-100', className)}
      onClick={onClick}
    >
      {isLoading && (
        <div className="absolute inset-0 animate-pulse bg-gray-200" />
      )}

      {!error ? (
        <img
          src={currentSrc}
          alt={alt}
          loading={priority ? 'eager' : 'lazy'}
          onLoad={handleLoad}
          onError={handleError}
          className={cn(
            'w-full h-full object-cover transition-opacity duration-300',
            isLoading && 'opacity-0',
            onClick && 'cursor-pointer hover:scale-105 transition-transform'
          )}
        />
      ) : (
        <div
          className="flex items-center justify-center h-full"
          aria-label="Image failed to load"
        >
          <ImageIcon className="w-8 h-8 text-gray-400" />
        </div>
      )}
    </div>
  );
}

// Grid-specific variant
export function ClothingItemGridImage(props: ClothingItemImageProps) {
  return (
    <ClothingItemImage
      {...props}
      className={cn('aspect-square', props.className)}
    />
  );
}

// List-specific variant
export function ClothingItemListImage(props: ClothingItemImageProps) {
  return (
    <ClothingItemImage
      {...props}
      className={cn('w-20 h-20 rounded-lg', props.className)}
    />
  );
}

// Detail view variant
export function ClothingItemDetailImage(props: ClothingItemImageProps) {
  const [isFullSize, setIsFullSize] = useState(false);

  const handleClick = () => {
    setIsFullSize(!isFullSize);
    if (props.onClick) props.onClick();
  };

  // For detail view, disable progressive loading by setting thumbnails to null when full size
  const currentImageUrl = isFullSize
    ? props.imageUrl
    : props.thumbnails?.thumb_400 || props.imageUrl;
  const currentThumbnails = isFullSize
    ? undefined
    : { thumb_200: currentImageUrl, thumb_400: currentImageUrl };

  return (
    <ClothingItemImage
      {...props}
      imageUrl={currentImageUrl}
      thumbnails={currentThumbnails}
      priority={true}
      onClick={handleClick}
      className={cn('aspect-[3/4]', props.className)}
    />
  );
}
