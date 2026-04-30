import type { WorkspaceRouteDefinition } from '@/src/app/shell/route-types';
import { aiManifest } from './manifest';
import { AIView } from './views/AIView';

export const aiWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'ai',
    path: '/w/:workspaceSlug/ai',
    element: <AIView toolItems={aiManifest.navItems} />,
  },
];
