import { Button } from '@/components/ui/button';
import { useEffect } from 'react';
import {
  Sheet,
  SheetContent,
  SheetTrigger,
  SheetDescription,
} from '@/components/ui/sheet';
import * as VisuallyHidden from '@radix-ui/react-visually-hidden';
import { Menu } from 'lucide-react';
import { useAppState } from '@/hooks/useAppState';
import {
  OutfitHistoryView,
  WardrobeView,
  WardrobeDetailView,
  PhotoGalleryView,
} from '@/components/views';
import { WardrobeAnalytics } from '@/components/wardrobe/WardrobeAnalytics';
import RentalDashboardPage from '@/pages/RentalDashboard';
import { API_URL } from '@/config/urls';
import type { OutfitRecord } from '@/types/outfit';
import type { ViewMode } from '@/types/app';
import { apiClient, setReadOnlyMode } from '@/services/apiClient';
import { logger } from '@/utils/logger';

interface AppProps {
  initialViewMode?: ViewMode;
}

function App({ initialViewMode }: AppProps) {
  const appState = useAppState(initialViewMode);
  useEffect(() => {
    let mounted = true;

    const loadSessionAccess = async () => {
      try {
        const session = await apiClient.get<{
          readOnly?: boolean;
          authenticatedEmail?: string | null;
        }>('/api/v2/auth/session');
        const enabled = Boolean(session.readOnly);
        const email = session.authenticatedEmail;
        const message = email
          ? `このアカウント (${email}) は閲覧専用モードです。データの更新はできません。`
          : 'このアカウントは閲覧専用モードです。データの更新はできません。';

        setReadOnlyMode(enabled, message);
      } catch (error) {
        logger.error('Failed to fetch session access:', error);
        if (!mounted) return;
        setReadOnlyMode(false);
      }
    };

    loadSessionAccess();

    return () => {
      mounted = false;
    };
  }, []);


  /**
   * コーディネート登録用の写真を選択
   * @param photo 選択する写真記録
   */
  const selectPhotoForOutfit = (photo: OutfitRecord) => {
    appState.setSelectedPhotoForOutfit(photo);
    appState.setViewModeWithContext(
      'photo-clothing-selection',
      'animate-slide-in-right',
      {
        viewMode: 'list' as const,
        calendarMonth: appState.calendarMonth?.toISOString() ?? null,
      }
    );
  };

  /**
   * ビューモードに応じたメインコンテンツを描画
   * @returns メインコンテンツのJSX要素
   */
  const renderMainContent = () => {
    switch (appState.viewMode) {

      case 'list':
        return (
          <OutfitHistoryView
            apiUrl={API_URL}
            animationClass={appState.animationClass}
            onPhotoSelect={selectPhotoForOutfit}
            onRegisterFullBody={date => {
              appState.setSelectedDateForRegistration(date);
              appState.setViewModeWithAnimation(
                'upload',
                'animate-slide-in-right'
              );
            }}
            onOutfitSaved={() => {
              appState.setOutfitRefreshTrigger(prev => (prev || 0) + 1);
              // recordedDateは既にOutfitCalendarのhandleOutfitSavedで処理される
            }}
            outfitRefreshTrigger={appState.outfitRefreshTrigger}
            goBack={appState.goBack}
            initialMonth={appState.calendarMonth}
            onMonthChange={appState.setCalendarMonth}
          />
        );

      case 'wardrobe':
        return (
          <WardrobeView
            apiUrl={API_URL}
            animationClass={appState.animationClass}
            viewMode={appState.viewMode}
            showWardrobeAnalytics={appState.showWardrobeAnalytics}
            showNewItemDialog={appState.showNewItemDialog}
            setShowWardrobeAnalytics={appState.setShowWardrobeAnalytics}
            setShowNewItemDialog={appState.setShowNewItemDialog}
            setSelectedClothingItem={appState.setSelectedClothingItem}
            setViewMode={appState.setViewModeWithAnimation}
            filters={appState.wardrobeFilters}
            setFilters={appState.setWardrobeFilters}
            showDisposedItems={appState.wardrobeShowDisposedItems}
            setShowDisposedItems={appState.setWardrobeShowDisposedItems}
            showListedItems={appState.wardrobeShowListedItems}
            setShowListedItems={appState.setWardrobeShowListedItems}
          />
        );

      case 'wardrobe-detail':
      case 'wardrobe-edit':
        return appState.selectedClothingItem ? (
          <WardrobeDetailView
            viewMode={appState.viewMode}
            selectedClothingItem={appState.selectedClothingItem}
            apiUrl={API_URL}
            showMessage={appState.showMessage}
            setSelectedClothingItem={appState.setSelectedClothingItem}
            setViewModeWithAnimation={appState.setViewModeWithAnimation}
          />
        ) : null;

      case 'wardrobe-register':
      case 'photo-clothing-selection':
      case 'upload':
        return (
          <PhotoGalleryView
            viewMode={appState.viewMode}
            animationClass={appState.animationClass}
            apiUrl={API_URL}
            selectedPhotoForOutfit={appState.selectedPhotoForOutfit}
            selectedDateForRegistration={appState.selectedDateForRegistration}
            showMessage={appState.showMessage}
            setViewModeWithAnimation={appState.setViewModeWithAnimation}
            setViewModeWithContext={appState.setViewModeWithContext}
            setSelectedPhotoForOutfit={appState.setSelectedPhotoForOutfit}
            setAnimationClass={() => {}} // Will be handled by useAppState
            setOutfitRefreshTrigger={appState.setOutfitRefreshTrigger}
            fetchRecords={appState.fetchRecords}
            onOutfitSaved={() => {
              // OutfitHistoryView経由でOutfitCalendarに日付を通知
              const outfitHistoryView = document.querySelector('[data-view="list"]');
              if (outfitHistoryView) {
                appState.setOutfitRefreshTrigger(prev => (prev || 0) + 1);
              }
            }}
          />
        );

      case 'analytics':
        return (
          <WardrobeAnalytics
            apiUrl={API_URL}
          />
        );

      case 'rental':
        return (
          <RentalDashboardPage
            showMessage={appState.showMessage}
          />
        );

      default:
        // management や capture などの古いビューモードは list にリダイレクト
        appState.setViewModeWithAnimation('list');
        return (
          <OutfitHistoryView
            apiUrl={API_URL}
            animationClass={appState.animationClass}
            onPhotoSelect={selectPhotoForOutfit}
            onRegisterFullBody={date => {
              appState.setSelectedDateForRegistration(date);
              appState.setViewModeWithAnimation(
                'upload',
                'animate-slide-in-right'
              );
            }}
            onOutfitSaved={() => {
              appState.setOutfitRefreshTrigger(prev => (prev || 0) + 1);
            }}
            outfitRefreshTrigger={appState.outfitRefreshTrigger}
            goBack={appState.goBack}
          />
        );
    }
  };

  return (
    <div className="min-h-screen bg-white text-gray-900">
      <header className="bg-white border-b border-gray-200 px-4 py-2 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto flex items-center justify-end">
          <Sheet
            open={appState.mobileMenuOpen}
            onOpenChange={appState.setMobileMenuOpen}
          >
            <SheetTrigger asChild>
              <Button variant="ghost" size="sm" className="relative">
                <Menu className="h-5 w-5" />
              </Button>
            </SheetTrigger>
            <SheetContent side="right" className="w-80 sm:w-96">
              <VisuallyHidden.Root>
                <SheetDescription>ナビゲーションメニュー</SheetDescription>
              </VisuallyHidden.Root>
              <nav className="mt-6 space-y-0">
                <button
                  onClick={() => {
                    appState.setViewModeWithAnimation('calendar');
                    appState.setMobileMenuOpen(false);
                  }}
                  className={`w-full text-xl font-medium text-left transition-colors px-6 py-5 border-b border-gray-200 ${
                    appState.viewMode === 'calendar'
                      ? 'text-black'
                      : 'text-gray-700 hover:text-black'
                  }`}
                >
                  カレンダー
                </button>
                <button
                  onClick={() => {
                    appState.setViewModeWithAnimation('wardrobe');
                    appState.setMobileMenuOpen(false);
                  }}
                  className={`w-full text-xl font-medium text-left transition-colors px-6 py-5 border-b border-gray-200 ${
                    appState.viewMode === 'wardrobe'
                      ? 'text-black'
                      : 'text-gray-700 hover:text-black'
                  }`}
                >
                  ワードローブ
                </button>
                <button
                  onClick={() => {
                    appState.setViewModeWithAnimation('rental');
                    appState.setMobileMenuOpen(false);
                  }}
                  className={`w-full text-xl font-medium text-left transition-colors px-6 py-5 border-b border-gray-200 ${
                    appState.viewMode === 'rental'
                      ? 'text-black'
                      : 'text-gray-700 hover:text-black'
                  }`}
                >
                  レンタル
                </button>
                <button
                  onClick={() => {
                    appState.setViewModeWithAnimation('analytics');
                    appState.setMobileMenuOpen(false);
                  }}
                  className={`w-full text-xl font-medium text-left transition-colors px-6 py-5 border-b border-gray-200 ${
                    appState.viewMode === 'analytics'
                      ? 'text-black'
                      : 'text-gray-700 hover:text-black'
                  }`}
                >
                  分析
                </button>
              </nav>
            </SheetContent>
          </Sheet>
        </div>
      </header>
      {/* Read-only banner hidden — API-side restrictions remain enforced */}

      {/* Main Content */}
      {renderMainContent()}

      {/* Toast Notification */}
      {appState.toastMessage && (
        <div className="fixed bottom-4 right-4 z-50">
          <div
            className={`px-4 py-2 rounded-md shadow-md ${
              appState.toastMessage.type === 'error'
                ? 'bg-red-100 text-red-800 border border-red-200'
                : 'bg-green-100 text-green-800 border border-green-200'
            }`}
          >
            {appState.toastMessage.text}
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
