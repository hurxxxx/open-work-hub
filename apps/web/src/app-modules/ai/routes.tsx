import { lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { WorkspaceRouteDefinition } from '@/src/app/shell/route-types';
import { aiManifest } from './manifest';

const AIView = lazy(() => import('./views/AIView').then((module) => ({ default: module.AIView })));
const RagSearchView = lazy(() =>
  import('./views/RagSearchView').then((module) => ({ default: module.RagSearchView })),
);

export const ragSearchToolElement = lazyRoute(<RagSearchView />);

export const aiWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'ai',
    path: '/w/:workspaceSlug/ai',
    element: lazyRoute(<AIView toolItems={aiManifest.navItems} />),
  },
];
