export interface DailyStatus {
  status: {
    captured_today: boolean;
    capture_count: number;
    last_capture?: string;
  };
}

export type ViewMode =
  | 'capture'
  | 'list'
  | 'wardrobe'
  | 'rental'
  | 'wardrobe-detail'
  | 'wardrobe-register'
  | 'wardrobe-edit'
  | 'photo-clothing-selection'
  | 'upload'
  | 'analytics';

export interface ToastMessage {
  text: string;
  type: 'success' | 'error';
}
