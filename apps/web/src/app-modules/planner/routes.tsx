import type { WorkspaceRouteDefinition } from '@/src/app/shell/route-types';
import { PlannerView } from './views/PlannerView';

export const plannerWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'planner',
    path: '/w/:workspaceSlug/planner',
    element: <PlannerView />,
  },
];
