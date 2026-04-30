import { BrowserRouter as Router } from 'react-router-dom';
import { MantineProvider } from '@mantine/core';
import '@mantine/core/styles.css';
import { ToastProvider, ToastViewport } from '@aidoo/ui';

import { AppContent } from './shell/AppContent';

export default function AppRoot() {
  return (
    <MantineProvider defaultColorScheme="auto">
      <ToastProvider>
        <Router>
          <AppContent />
        </Router>
        <ToastViewport />
      </ToastProvider>
    </MantineProvider>
  );
}
