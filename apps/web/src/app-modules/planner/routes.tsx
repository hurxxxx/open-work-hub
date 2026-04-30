import { PlannerView } from '@/src/components/views/PlannerView';
import type { WorkspaceRouteDefinition } from '@/src/app/shell/route-types';

export const plannerWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'planner',
    path: '/w/:workspaceSlug/planner',
    element: <PlannerView />,
  },
];
