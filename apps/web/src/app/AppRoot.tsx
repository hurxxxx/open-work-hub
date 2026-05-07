import { BrowserRouter as Router } from 'react-router-dom';
import {
  ToastProvider,
  ToastViewport,
} from '@ai-do/ui/providers/toast-provider';

import { AppContent } from './shell/AppContent';

export default function AppRoot() {
  return (
    <ToastProvider>
      <Router>
        <AppContent />
      </Router>
      <ToastViewport />
    </ToastProvider>
  );
}
