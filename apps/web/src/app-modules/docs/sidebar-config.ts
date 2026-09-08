import { FileText } from 'lucide-react';
import { createElement } from 'react';

import type { AppSidebarConfig } from '@/src/app/shell/sidebar-types';
import { DocsSidebarExtras } from './sidebar';

export const docsSidebarConfig: AppSidebarConfig = {
  createActions: () => [
    {
      id: 'docs-create-doc',
      label: 'docs-create-doc',
      labelKey: 'sidebarActions.docs-create-doc',
      icon: FileText,
      run: () => {
        window.dispatchEvent(new CustomEvent('docs:create'));
      },
    },
  ],
  afterCategories: (_context) => createElement(DocsSidebarExtras, {}),
};
