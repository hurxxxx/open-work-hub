import type { WorkspaceRouteDefinition } from '@/src/app/shell/route-types';
import { WorkspaceHomeView } from './views/WorkspaceHomeView/WorkspaceHomeView';

export const homeWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'home',
    path: '/w/:workspaceSlug/home',
    element: <WorkspaceHomeView />,
  },
];
