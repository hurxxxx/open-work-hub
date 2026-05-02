import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import '@aidoo/ui/styles.css';
import { i18n } from '@/src/platform/i18n';
import App from './App';
import './index.css';
import './styles/fullcalendar-theme.css';

const rootElement = document.getElementById('root');
if (!rootElement) {
  throw new Error(i18n.t('common:feedback.missingRootElement'));
}

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
