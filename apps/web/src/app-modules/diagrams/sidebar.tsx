import { Workflow } from 'lucide-react';

import type { AppSidebarConfig } from '@/src/app/shell/sidebar-types';

export const diagramsSidebarConfig: AppSidebarConfig = {
  createActions: () => [
    {
      id: 'diagrams-create',
      label: 'diagrams-create',
      labelKey: 'sidebarActions.diagrams-create',
      icon: Workflow,
      run: () => {
        window.dispatchEvent(new CustomEvent('diagrams:create'));
      },
    },
  ],
};
