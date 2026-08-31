import { OutfitHistory } from '@/components/home/OutfitHistory';
import type { OutfitRecord } from '@/types/outfit';

interface OutfitHistoryViewProps {
  apiUrl: string;
  animationClass: string;
  onPhotoSelect: (photo: OutfitRecord) => void;
  onRegisterFullBody: (date: Date) => void;
  onOutfitSaved: (recordedDate?: string) => void;
  outfitRefreshTrigger: number;
  goBack: () => void;
  initialMonth?: Date | null;
  onMonthChange?: (month: Date) => void;
}

export const OutfitHistoryView = ({
  apiUrl,
  animationClass,
  onPhotoSelect,
  onRegisterFullBody,
  onOutfitSaved,
  outfitRefreshTrigger,
  goBack,
  initialMonth,
  onMonthChange,
}: OutfitHistoryViewProps) => {
  return (
    <main
      className={`p-0 md:p-8 transition-all duration-500 ease-in-out ${animationClass}`}
    >
      <div className="max-w-7xl mx-auto">
        <OutfitHistory
          apiUrl={apiUrl}
          onPhotoSelect={onPhotoSelect}
          onRegisterFullBody={onRegisterFullBody}
          onOutfitSaved={onOutfitSaved}
          outfitRefreshTrigger={outfitRefreshTrigger}
          goBack={goBack}
          initialMonth={initialMonth}
          onMonthChange={onMonthChange}
        />
      </div>
    </main>
  );
};
