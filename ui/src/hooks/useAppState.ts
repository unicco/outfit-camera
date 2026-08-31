import { useState, useEffect, useCallback } from 'react';
import type { ViewMode, DailyStatus, ToastMessage } from '@/types/app';
import type { OutfitRecord } from '@/types/outfit';
import type { ExtendedClothingItem } from '@/types/wardrobe';
import type { FilterState } from '@/components/wardrobe/WardrobeFilters';
import { apiClient } from '@/services/apiClient';
import { logger } from '@/utils/logger';

/**
 * アプリケーション全体の状態管理インターフェース
 */
const VALID_VIEW_MODES: ViewMode[] = [
  'capture',
  'list',
  'wardrobe',
  'rental',
  'wardrobe-detail',
  'wardrobe-register',
  'wardrobe-edit',
  'photo-clothing-selection',
  'upload',
  'analytics',
];

export interface AppState {
  // View Mode
  viewMode: ViewMode;
  animationClass: string;
  setViewModeWithAnimation: (newMode: ViewMode, animation?: string) => void;
  goBack: () => void;
  // Context-aware navigation
  setViewModeWithContext: (
    newMode: ViewMode,
    animation?: string,
    previousContext?: {
      viewMode: ViewMode;
      selectedPhotoForOutfit?: OutfitRecord | null;
      selectedClothingItem?: ExtendedClothingItem | null;
    }
  ) => void;

  // Data
  records: OutfitRecord[];
  dailyStatus: DailyStatus | null;
  fetchRecords: (dateFilter?: string) => Promise<void>;
  fetchDailyStatus: () => Promise<void>;

  // UI State
  loading: boolean;
  message: string;
  selectedPhoto: string | null;
  showDeleteConfirm: boolean;
  mobileMenuOpen: boolean;

  // Wardrobe State
  selectedClothingItem: ExtendedClothingItem | null;
  showNewItemDialog: boolean;
  showWardrobeAnalytics: boolean;
  selectedPhotoForOutfit: OutfitRecord | null;
  outfitRefreshTrigger: number;
  selectedDateForRegistration: Date | null;
  wardrobeFilters: FilterState;
  wardrobeShowDisposedItems: boolean;
  wardrobeShowListedItems: boolean;

  // Toast
  toastMessage: ToastMessage | null;
  showMessage: (text: string, type?: 'success' | 'error') => void;

  // Setters
  setLoading: (loading: boolean) => void;
  setMessage: (message: string) => void;
  setSelectedPhoto: (photo: string | null) => void;
  setShowDeleteConfirm: (show: boolean) => void;
  setMobileMenuOpen: (open: boolean) => void;
  setSelectedClothingItem: (item: ExtendedClothingItem | null) => void;
  setShowNewItemDialog: (show: boolean) => void;
  setShowWardrobeAnalytics: (show: boolean) => void;
  setSelectedPhotoForOutfit: (photo: OutfitRecord | null) => void;
  setOutfitRefreshTrigger: (
    trigger: number | ((prev: number) => number)
  ) => void;
  setSelectedDateForRegistration: (date: Date | null) => void;
  setWardrobeFilters: React.Dispatch<React.SetStateAction<FilterState>>;
  setWardrobeShowDisposedItems: React.Dispatch<React.SetStateAction<boolean>>;
  setWardrobeShowListedItems: React.Dispatch<React.SetStateAction<boolean>>;
}

/**
 * アプリケーション全体の状態を管理するカスタムフック
 * @returns AppState アプリケーションの状態とその操作関数
 */
export const useAppState = (initialViewMode?: ViewMode): AppState => {
  // URL から初期 viewMode を判定
  const getInitialViewMode = (): ViewMode => {
    if (window.location.pathname === '/rental') {
      return 'rental';
    }

    const hash = window.location.hash.slice(1); // '#' を除去
    return VALID_VIEW_MODES.includes(hash as ViewMode) ? (hash as ViewMode) : 'list';
  };

  const [viewMode, setViewMode] = useState<ViewMode>(
    initialViewMode ?? getInitialViewMode(),
  );
  const [animationClass, setAnimationClass] = useState('animate-fade-in');
  const [records, setRecords] = useState<OutfitRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [selectedPhoto, setSelectedPhoto] = useState<string | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [dailyStatus, setDailyStatus] = useState<DailyStatus | null>(null);
  const [selectedClothingItem, setSelectedClothingItem] =
    useState<ExtendedClothingItem | null>(null);
  const [showNewItemDialog, setShowNewItemDialog] = useState(false);
  const [showWardrobeAnalytics, setShowWardrobeAnalytics] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [toastMessage, setToastMessage] = useState<ToastMessage | null>(null);
  const [selectedPhotoForOutfit, setSelectedPhotoForOutfit] =
    useState<OutfitRecord | null>(null);
  const [outfitRefreshTrigger, setOutfitRefreshTrigger] = useState<number>(0);
  const [, setViewHistory] = useState<ViewMode[]>(['list']);
  const [selectedDateForRegistration, setSelectedDateForRegistration] =
    useState<Date | null>(null);
  const [wardrobeFilters, setWardrobeFilters] = useState<FilterState>({
    category: '',
    subcategory: '',
    season: '',
    tag: '',
    status: '',
  });
  const [wardrobeShowDisposedItems, setWardrobeShowDisposedItems] =
    useState(false);
  const [wardrobeShowListedItems, setWardrobeShowListedItems] = useState(false);
  // Context-aware navigation state
  const [navigationContext, setNavigationContext] = useState<{
    viewMode: ViewMode;
    selectedPhotoForOutfit?: OutfitRecord | null;
    selectedClothingItem?: ExtendedClothingItem | null;
    calendarMonth?: string | null;
  } | null>(null);
  // カレンダーで表示中の月（詳細画面から戻ったときに復元するため）
  const [calendarMonth, setCalendarMonth] = useState<Date | null>(null);

  const showMessage = (text: string, type: 'success' | 'error' = 'success') => {
    setToastMessage({ text, type });
    setTimeout(() => setToastMessage(null), 3000);
  };

  /**
   * アニメーション付きでビューモードを変更
   * @param newMode 新しいビューモード
   * @param animation アニメーションクラス名
   */
  const updateLocationForMode = (mode: ViewMode) => {
    if (mode === 'rental') {
      if (window.location.pathname !== '/rental') {
        window.history.pushState({ viewMode: mode }, '', '/rental');
      } else {
        window.history.replaceState({ viewMode: mode }, '', '/rental');
      }
      return;
    }

    const targetPath = mode === 'list' ? '/' : `/#${mode}`;
    const currentPath = `${window.location.pathname}${window.location.hash}`;
    if (currentPath === targetPath) {
      window.history.replaceState({ viewMode: mode }, '', targetPath);
    } else {
      window.history.pushState({ viewMode: mode }, '', targetPath);
    }
  };

  const setViewModeWithAnimation = (
    newMode: ViewMode,
    animation: string = 'animate-fade-in'
  ) => {
    setAnimationClass(animation);
    setViewMode(newMode);
    // ページ遷移時にスクロール位置をトップにリセット
    window.scrollTo(0, 0);

    // 履歴に追加（同じモードの連続は避ける）
    setViewHistory(prev => {
      if (prev[prev.length - 1] !== newMode) {
        return [...prev, newMode];
      }
      return prev;
    });

    updateLocationForMode(newMode);
  };

  /**
   * コンテキスト情報付きでビューモードを変更
   * @param newMode 新しいビューモード
   * @param animation アニメーションクラス名
   * @param previousContext 前画面のコンテキスト情報
   */
  const setViewModeWithContext = (
    newMode: ViewMode,
    animation: string = 'animate-fade-in',
    previousContext?: {
      viewMode: ViewMode;
      selectedPhotoForOutfit?: OutfitRecord | null;
      selectedClothingItem?: ExtendedClothingItem | null;
    }
  ) => {
    // 前画面のコンテキストを保存
    if (previousContext) {
      setNavigationContext(previousContext);
    }

    // 通常のナビゲーション実行
    setViewModeWithAnimation(newMode, animation);
  };

  useEffect(() => {
    const syncViewFromLocation = () => {
      const hash = window.location.hash.slice(1) as ViewMode;
      if (VALID_VIEW_MODES.includes(hash)) {
        setAnimationClass('animate-fade-in');
        setViewMode(hash);
      } else {
        setAnimationClass('animate-fade-in');
        setViewMode('list');
      }
    };

    window.addEventListener('popstate', syncViewFromLocation);
    return () => window.removeEventListener('popstate', syncViewFromLocation);
  }, []);

  /**
   * 前のビューモードに戻る
   */
  const goBack = useCallback(() => {
    // 保存されたナビゲーションコンテキストがある場合はそれを使用
    if (navigationContext) {
      const context = navigationContext;
      setNavigationContext(null); // コンテキストをクリア

      // コンテキストの状態を復元
      if (context.selectedPhotoForOutfit !== undefined) {
        setSelectedPhotoForOutfit(context.selectedPhotoForOutfit);
      }
      if (context.selectedClothingItem !== undefined) {
        setSelectedClothingItem(context.selectedClothingItem);
      }
      if (context.calendarMonth) {
        setCalendarMonth(new Date(context.calendarMonth));
      }

      // ビューモードを復元
      setAnimationClass('animate-slide-in-left');
      setViewMode(context.viewMode);
      updateLocationForMode(context.viewMode);
      window.scrollTo(0, 0);
      return;
    }

    // 通常の履歴ベースのナビゲーション
    setViewHistory(prev => {
      if (prev.length > 1) {
        const newHistory = prev.slice(0, -1);
        const previousMode = newHistory[newHistory.length - 1];
        setAnimationClass('animate-slide-in-left');
        setViewMode(previousMode);
        updateLocationForMode(previousMode);
        window.scrollTo(0, 0);
        return newHistory;
      }
      return prev;
    });
  }, [
    navigationContext,
    setNavigationContext,
    setSelectedPhotoForOutfit,
    setSelectedClothingItem,
    setAnimationClass,
    setViewMode,
    setViewHistory,
  ]);

  /**
   * 日次ステータスを取得
   */
  const fetchDailyStatus = useCallback(async () => {
    try {
      const data = await apiClient.get<DailyStatus>('/api/v2/daily-status');
      setDailyStatus(data);
    } catch (error) {
      logger.error('Failed to fetch daily status:', error);
    }
  }, []);

  /**
   * コーディネート記録を取得
   * @param dateFilter 日付フィルター
   */
  const fetchRecords = useCallback(async (dateFilter?: string) => {
    try {
      const path = dateFilter
        ? `/api/v2/records?date_filter=${dateFilter}`
        : `/api/v2/records`;
      const data = await apiClient.get<OutfitRecord[] | { records: OutfitRecord[] }>(path);
      // Extract records array from v2 API response
      const recordsArray = Array.isArray(data) ? data : data.records || [];
      setRecords(recordsArray);
    } catch (error) {
      logger.error('Error fetching records:', error);
      setRecords([]); // エラー時も空配列を設定
    }
  }, []);

  useEffect(() => {
    // Parallelize initial API calls for better performance
    // React Compiler ルールに合わせ、初期フェッチは同期フェーズ後にスケジュール
    queueMicrotask(() => {
      void Promise.all([fetchRecords(), fetchDailyStatus()]).catch(() => {
        // Individual functions handle their own errors silently
      });
    });

    // ハッシュ変更の監視
    const handleHashChange = () => {
      const hash = window.location.hash.slice(1);
      const validModes: ViewMode[] = [
        'capture', 'list', 'wardrobe', 'wardrobe-detail', 'wardrobe-register',
        'wardrobe-edit', 'photo-clothing-selection',
        'upload', 'analytics'
      ];
      if (validModes.includes(hash as ViewMode)) {
        setViewMode(hash as ViewMode);
      }
    };

    // ブラウザの戻るボタンハンドリング
    const handlePopState = (event: PopStateEvent) => {
      event.preventDefault();
      handleHashChange(); // ハッシュからviewModeを更新
    };

    window.addEventListener('hashchange', handleHashChange);
    window.addEventListener('popstate', handlePopState);
    return () => {
      window.removeEventListener('hashchange', handleHashChange);
      window.removeEventListener('popstate', handlePopState);
    };
  }, [fetchDailyStatus, fetchRecords]);

  return {
    // View Mode
    viewMode,
    goBack,
    animationClass,
    setViewModeWithAnimation,
    setViewModeWithContext,

    // Data
    records,
    dailyStatus,
    fetchRecords,
    fetchDailyStatus,

    // UI State
    loading,
    message,
    selectedPhoto,
    showDeleteConfirm,
    mobileMenuOpen,

    // Calendar State
    calendarMonth,

    // Wardrobe State
    selectedClothingItem,
    showNewItemDialog,
    showWardrobeAnalytics,
    selectedPhotoForOutfit,
    outfitRefreshTrigger,
    selectedDateForRegistration,
    wardrobeFilters,
    wardrobeShowDisposedItems,
    wardrobeShowListedItems,

    // Toast
    toastMessage,
    showMessage,

    // Setters
    setLoading,
    setMessage,
    setSelectedPhoto,
    setShowDeleteConfirm,
    setMobileMenuOpen,
    setSelectedClothingItem,
    setShowNewItemDialog,
    setShowWardrobeAnalytics,
    setSelectedPhotoForOutfit,
    setOutfitRefreshTrigger,
    setSelectedDateForRegistration,
    setWardrobeFilters,
    setWardrobeShowDisposedItems,
    setWardrobeShowListedItems,
    setCalendarMonth,
  };
};
