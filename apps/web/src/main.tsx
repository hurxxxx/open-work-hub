import {StrictMode, useEffect} from 'react';
import {createRoot} from 'react-dom/client';
import '@open-alm/ui/styles.css';
import { i18n } from '@/src/platform/i18n';
import { installMatomoTracking } from '@/src/platform/analytics/matomo';
import { installClientBuildGuards } from '@/src/platform/deployment/client-build-guard';
import {
  clearStaleAssetReloadMarker,
  installStaleAssetReloadHandler,
} from '@/src/platform/deployment/stale-asset-reload';
import App from './App';
import './index.css';
import './styles/fullcalendar-theme.css';

installStaleAssetReloadHandler();
installClientBuildGuards();
installMatomoTracking();

function StaleAssetReloadMarkerCleanup() {
  useEffect(() => {
    clearStaleAssetReloadMarker();
  }, []);
  return null;
}

const rootElement = document.getElementById('root');
if (!rootElement) {
  throw new Error(i18n.t('common:feedback.missingRootElement'));
}

createRoot(rootElement).render(
  <StrictMode>
    <App />
    <StaleAssetReloadMarkerCleanup />
  </StrictMode>,
);
