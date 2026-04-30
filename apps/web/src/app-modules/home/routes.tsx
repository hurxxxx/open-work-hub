import { WorkspaceHomeView } from '@/src/components/views/WorkspaceHomeView/WorkspaceHomeView';
import type { WorkspaceRouteDefinition } from '@/src/app/shell/route-types';

export const homeWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'home',
    path: '/w/:workspaceSlug/home',
    element: <WorkspaceHomeView />,
  },
];
