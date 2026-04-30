import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import '@aidoo/ui/styles.css';
import App from './App';
import './index.css';
import './styles/fullcalendar-theme.css';

const rootElement = document.getElementById('root');
if (!rootElement) {
  throw new Error('Missing root element.');
}

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
