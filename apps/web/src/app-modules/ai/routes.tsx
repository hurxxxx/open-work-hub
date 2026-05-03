import { lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { WorkspaceRouteDefinition } from '@/src/app/shell/route-types';
import { aiManifest } from './manifest';

const AIView = lazy(() => import('./views/AIView').then((module) => ({ default: module.AIView })));
const RagSearchView = lazy(() =>
  import('./views/RagSearchView').then((module) => ({ default: module.RagSearchView })),
);
const ImageWizardToolView = lazy(() =>
  import('./views/ImageWizard/ImageWizardToolView').then((module) => ({
    default: module.ImageWizardToolView,
  })),
);

export const ragSearchToolElement = lazyRoute(<RagSearchView />);
export const imageWizardToolElement = lazyRoute(<ImageWizardToolView />);

export const aiWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'ai',
    path: '/w/:workspaceSlug/ai',
    element: lazyRoute(<AIView toolItems={aiManifest.navItems} />),
  },
];
