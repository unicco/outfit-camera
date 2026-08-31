import { useState, useEffect } from 'react';
import { Settings, Clock, ToggleLeft, ToggleRight } from 'lucide-react';

interface CountdownSettingsProps {
  onSettingsChange: (settings: {
    enabled: boolean;
    duration: number;
    devMode?: boolean;
  }) => void;
}

const CountdownSettings: React.FC<CountdownSettingsProps> = ({
  onSettingsChange,
}) => {
  const [enabled, setEnabled] = useState(true);
  const [duration, setDuration] = useState(5);
  const [devMode, setDevMode] = useState(false);
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    // Load settings from localStorage
    const savedSettings = localStorage.getItem('countdownSettings');
    if (savedSettings) {
      const {
        enabled: savedEnabled,
        duration: savedDuration,
        devMode: savedDevMode = false,
      } = JSON.parse(savedSettings);
      // eslint-disable-next-line react-hooks/set-state-in-effect -- localStorage からの初期復元
      setEnabled(savedEnabled);
      setDuration(savedDuration);
      setDevMode(savedDevMode);
      onSettingsChange({
        enabled: savedEnabled,
        duration: savedDuration,
        devMode: savedDevMode,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleEnabledChange = () => {
    const newEnabled = !enabled;
    setEnabled(newEnabled);
    const settings = { enabled: newEnabled, duration, devMode };
    localStorage.setItem('countdownSettings', JSON.stringify(settings));
    onSettingsChange(settings);
  };

  const handleDurationChange = (newDuration: number) => {
    setDuration(newDuration);
    const settings = { enabled, duration: newDuration, devMode };
    localStorage.setItem('countdownSettings', JSON.stringify(settings));
    onSettingsChange(settings);
  };

  const handleDevModeChange = () => {
    const newDevMode = !devMode;
    setDevMode(newDevMode);
    const settings = { enabled, duration, devMode: newDevMode };
    localStorage.setItem('countdownSettings', JSON.stringify(settings));
    onSettingsChange(settings);
  };

  return (
    <>
      {/* Settings Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="absolute top-4 left-4 p-2 bg-white/10 backdrop-blur-sm rounded-lg hover:bg-white/20 transition-colors z-40"
        aria-label="カウントダウン設定"
      >
        <Settings className="h-5 w-5 text-white" />
      </button>

      {/* Settings Panel */}
      {isOpen && (
        <div className="absolute top-16 left-4 bg-white rounded-lg shadow-lg p-4 z-40 w-80">
          <h3 className="text-lg font-semibold mb-4 flex items-center">
            <Clock className="h-5 w-5 mr-2" />
            カウントダウン設定
          </h3>

          {/* Enable/Disable Toggle */}
          <div className="mb-4">
            <label className="flex items-center justify-between cursor-pointer">
              <span className="text-sm font-medium">
                カウントダウンを有効にする
              </span>
              <button
                onClick={handleEnabledChange}
                className={`p-1 transition-colors ${enabled ? 'text-blue-600' : 'text-gray-400'}`}
              >
                {enabled ? (
                  <ToggleRight className="h-8 w-8" />
                ) : (
                  <ToggleLeft className="h-8 w-8" />
                )}
              </button>
            </label>
          </div>

          {/* Duration Slider */}
          <div
            className={`${enabled ? 'opacity-100' : 'opacity-50'} transition-opacity`}
          >
            <label className="block text-sm font-medium mb-2">
              カウントダウン時間: {duration}秒
            </label>
            <input
              type="range"
              min="3"
              max="10"
              value={duration}
              onChange={e => handleDurationChange(Number(e.target.value))}
              disabled={!enabled}
              className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer disabled:cursor-not-allowed"
            />
            <div className="flex justify-between text-xs text-gray-500 mt-1">
              <span>3秒</span>
              <span>10秒</span>
            </div>
          </div>

          {/* Dev Mode Toggle */}
          <div className="mt-4 pt-4 border-t border-gray-200">
            <label className="flex items-center justify-between cursor-pointer">
              <span className="text-sm font-medium text-gray-700">
                開発モード
              </span>
              <button
                onClick={handleDevModeChange}
                className={`p-1 transition-colors ${devMode ? 'text-orange-600' : 'text-gray-400'}`}
              >
                {devMode ? (
                  <ToggleRight className="h-8 w-8" />
                ) : (
                  <ToggleLeft className="h-8 w-8" />
                )}
              </button>
            </label>
            <p className="text-xs text-gray-500 mt-1">
              ディスプレイタイムアウトを無効化
            </p>
          </div>

          {/* Close button */}
          <button
            onClick={() => setIsOpen(false)}
            className="mt-4 w-full py-2 bg-gray-100 hover:bg-gray-200 rounded-md text-sm font-medium transition-colors"
          >
            閉じる
          </button>
        </div>
      )}
    </>
  );
};

export default CountdownSettings;
