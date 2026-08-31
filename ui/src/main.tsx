import { createRoot } from 'react-dom/client';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import './index.css';
import App from './App.tsx';
import { TouchscreenPage } from './pages/TouchscreenPage.tsx';
import { MorningBriefDetailPage } from './pages/MorningBriefDetailPage.tsx';
import { GooglePhotosCallback } from './pages/GooglePhotosCallback.tsx';
import GooglePhotosBatchUploadPage from './pages/GooglePhotosBatchUploadPage.tsx';

createRoot(document.getElementById('root')!).render(
  <BrowserRouter>
    <Routes>
      <Route path="/" element={<App />} />
      <Route path="/rental" element={<App initialViewMode="rental" />} />
      <Route path="/touchscreen" element={<TouchscreenPage />} />
      <Route path="/today" element={<MorningBriefDetailPage />} />
      <Route
        path="/google-photos/batch-upload"
        element={<GooglePhotosBatchUploadPage />}
      />
      <Route path="/google-photos/oauth2callback" element={<GooglePhotosCallback />} />
    </Routes>
  </BrowserRouter>
);
