import { AIView } from '@/src/components/views/AIView';
import type { WorkspaceRouteDefinition } from '@/src/app/shell/route-types';

export const aiWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'ai',
    path: '/w/:workspaceSlug/ai',
    element: <AIView />,
  },
];
