import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterAll } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

import GooglePhotosBatchUploadPage from '../GooglePhotosBatchUploadPage';
import { uploadGooglePhotosBatch } from '@/services/googlePhotos';
import type { GooglePhotosBatchUploadResponse } from '@/services/googlePhotos';

vi.mock('@/services/googlePhotos', async () => {
  const actual = await vi.importActual<typeof import('@/services/googlePhotos')>(
    '@/services/googlePhotos'
  );
  return {
    ...actual,
    uploadGooglePhotosBatch: vi.fn(),
  };
});

type MutableURL = typeof URL & {
  createObjectURL?: (blob: Blob) => string;
  revokeObjectURL?: (url: string) => void;
};

const mutableURL = URL as MutableURL;
const originalCreateObjectURL = mutableURL.createObjectURL;
const originalRevokeObjectURL = mutableURL.revokeObjectURL;
const createObjectURLMock = vi.fn(() => 'blob:mock');
const revokeObjectURLMock = vi.fn();

mutableURL.createObjectURL = createObjectURLMock;
mutableURL.revokeObjectURL = revokeObjectURLMock;

const mockedUpload = vi.mocked(uploadGooglePhotosBatch);

beforeEach(() => {
  vi.clearAllMocks();
  createObjectURLMock.mockClear();
  revokeObjectURLMock.mockClear();
});

afterAll(() => {
  if (originalCreateObjectURL) {
    mutableURL.createObjectURL = originalCreateObjectURL;
  } else {
    delete mutableURL.createObjectURL;
  }
  if (originalRevokeObjectURL) {
    mutableURL.revokeObjectURL = originalRevokeObjectURL;
  } else {
    delete mutableURL.revokeObjectURL;
  }
});

describe('GooglePhotosBatchUploadPage', () => {
  const renderPage = () =>
    render(
      <MemoryRouter>
        <GooglePhotosBatchUploadPage />
      </MemoryRouter>
    );

  it('applies bulk metadata to all selected photos', () => {
    const { container } = renderPage();
    const file = new File(['demo'], 'bulk.jpg', { type: 'image/jpeg' });
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(fileInput, { target: { files: [file] } });

    const bulkLocationInput = screen.getByPlaceholderText('例: 北海道旅行 2010');
    fireEvent.change(bulkLocationInput, { target: { value: '共通メモ' } });

    const photoLocationInput = screen.getByPlaceholderText('例: 祖父母の家、札幌') as HTMLInputElement;
    expect(photoLocationInput.value).toBe('');

    fireEvent.click(screen.getByRole('button', { name: 'すべての写真に適用' }));

    expect(photoLocationInput.value).toBe('共通メモ');
  });

  it('uploads selected files and shows success result', async () => {
    const user = userEvent.setup();
    const file = new File(['sample'], 'first.jpg', { type: 'image/jpeg' });
    const response: GooglePhotosBatchUploadResponse = {
      success: true,
      results: [
        {
          fileName: 'first.jpg',
          clientId: 'server-photo-1',
          success: true,
          mediaItemId: 'media-1',
        },
      ],
    };
    mockedUpload.mockResolvedValueOnce(response);

    const { container } = renderPage();

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(fileInput, { target: { files: [file] } });

    const captureInputs = container.querySelectorAll('input[type="datetime-local"]');
    captureInputs.forEach(input => {
      fireEvent.change(input, { target: { value: 'invalid-date' } });
    });

    const locationInput = screen.getByPlaceholderText('例: 祖父母の家、札幌');
    fireEvent.change(locationInput, { target: { value: '札幌' } });

    await user.click(screen.getByRole('button', { name: 'Google Photos にアップロード' }));

    await waitFor(() => {
      expect(mockedUpload).toHaveBeenCalledTimes(1);
    });

    const submittedForm = mockedUpload.mock.calls[0][0];
    const metadataRaw = submittedForm.get('metadata_json');
    expect(typeof metadataRaw).toBe('string');
    const metadata = JSON.parse(metadataRaw as string);
    expect(metadata).toHaveLength(1);
    expect(metadata[0]).toMatchObject({
      fileName: 'first.jpg',
      captureTime: null,
      locationName: '札幌',
    });

    await waitFor(() => {
      expect(
        screen.getByText('すべての写真を Google Photos にアップロードしました')
      ).toBeInTheDocument();
    });
    expect(screen.getByText('完了')).toBeInTheDocument();
  });
});
