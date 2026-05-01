import { PencilRuler } from 'lucide-react';

import type { AppSidebarConfig } from '@/src/app/shell/sidebar-types';

export const whiteboardSidebarConfig: AppSidebarConfig = {
  createActions: () => [
    {
      id: 'whiteboard-create',
      label: 'Whiteboard',
      icon: PencilRuler,
      run: () => {
        window.dispatchEvent(new CustomEvent('whiteboard:create'));
      },
    },
  ],
};

