import { lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { WorkspaceRouteDefinition } from '@/src/app/shell/route-types';

const DocsView = lazy(() => import('./views/DocsView').then((module) => ({ default: module.DocsView })));

export const docsToolElement = lazyRoute(<DocsView />);

export const docsWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'docs',
    path: '/w/:workspaceSlug/docs',
    element: docsToolElement,
  },
  {
    appId: 'docs',
    path: '/w/:workspaceSlug/docs/:docId',
    element: docsToolElement,
  },
];

export const docsGlobalRoutes = [
  {
    path: '/docs/shared/:shareToken',
    element: docsToolElement,
  },
];
