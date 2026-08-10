import { createElement } from 'react';

import type { AppSidebarConfig } from '@/src/app/shell/sidebar-types';
import { LearningSidebarTree } from './sidebar';

export const learningSidebarConfig: AppSidebarConfig = {
  afterCategories: ({ currentPathname }) =>
    createElement(LearningSidebarTree, { currentPathname }),
};
