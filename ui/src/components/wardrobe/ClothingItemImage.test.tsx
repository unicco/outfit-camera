import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {
  ClothingItemImage,
  ClothingItemGridImage,
  ClothingItemDetailImage,
} from './ClothingItemImage';

// Mock image loading
vi.stubGlobal(
  'Image',
  class {
    src = '';
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;

    constructor() {
      setTimeout(() => {
        if (this.onload) this.onload();
      }, 0);
    }
  }
);

describe('ClothingItemImage', () => {
  const defaultProps = {
    imageUrl: 'https://example.com/image.jpg',
    alt: 'Test clothing item',
  };

  it('renders with loading state initially', () => {
    render(<ClothingItemImage {...defaultProps} />);

    const container = screen.getByRole('img').parentElement;
    expect(container?.querySelector('.animate-pulse')).toBeInTheDocument();
  });

  it('removes loading state after image loads', async () => {
    render(<ClothingItemImage {...defaultProps} />);

    const img = screen.getByRole('img') as HTMLImageElement;
    img.dispatchEvent(new Event('load'));

    await waitFor(() => {
      const container = screen.getByRole('img').parentElement;
      expect(
        container?.querySelector('.animate-pulse')
      ).not.toBeInTheDocument();
    });
  });

  it('shows error state when image fails to load', async () => {
    render(<ClothingItemImage {...defaultProps} />);

    const img = screen.getByRole('img') as HTMLImageElement;
    img.dispatchEvent(new Event('error'));

    await waitFor(() => {
      // The img element is hidden but still exists in DOM when error occurs
      expect(screen.queryByRole('img')).not.toBeInTheDocument();
      expect(screen.getByLabelText('Image failed to load')).toBeInTheDocument();
    });
  });

  it('uses thumbnail URL when provided', () => {
    const thumbnails = {
      thumb_200: 'https://example.com/thumb_200.jpg',
      thumb_400: 'https://example.com/thumb_400.jpg',
    };

    render(<ClothingItemImage {...defaultProps} thumbnails={thumbnails} />);

    const img = screen.getByRole('img') as HTMLImageElement;
    expect(img.src).toBe(thumbnails.thumb_200);
  });

  it('handles click events', async () => {
    const handleClick = vi.fn();
    const user = userEvent.setup();

    render(<ClothingItemImage {...defaultProps} onClick={handleClick} />);

    await user.click(screen.getByRole('img').parentElement!);
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it('sets loading attribute based on priority', () => {
    const { rerender } = render(<ClothingItemImage {...defaultProps} />);
    expect(screen.getByRole('img')).toHaveAttribute('loading', 'lazy');

    rerender(<ClothingItemImage {...defaultProps} priority />);
    expect(screen.getByRole('img')).toHaveAttribute('loading', 'eager');
  });
});

describe('ClothingItemGridImage', () => {
  it('applies aspect-square class', () => {
    render(<ClothingItemGridImage imageUrl="test.jpg" alt="Test" />);

    const container = screen.getByRole('img').parentElement;
    expect(container).toHaveClass('aspect-square');
  });
});

describe('ClothingItemDetailImage', () => {
  const props = {
    imageUrl: 'https://example.com/full.jpg',
    thumbnails: {
      thumb_200: 'https://example.com/thumb_200.jpg',
      thumb_400: 'https://example.com/thumb_400.jpg',
    },
    alt: 'Detail view',
  };

  it('starts with thumbnail in detail view', () => {
    render(<ClothingItemDetailImage {...props} />);

    const img = screen.getByRole('img') as HTMLImageElement;
    expect(img.src).toBe(props.thumbnails.thumb_400);
  });

  it('toggles to full size on click', async () => {
    const user = userEvent.setup();
    render(<ClothingItemDetailImage {...props} />);

    const container = screen.getByRole('img').parentElement;
    await user.click(container!);

    // Component should update to use full imageUrl
    await waitFor(() => {
      const img = screen.getByRole('img') as HTMLImageElement;
      expect(img.src).toBe(props.imageUrl);
    });
  });
});
