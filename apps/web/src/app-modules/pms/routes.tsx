import type { WorkspaceRouteDefinition } from '@/src/app/shell/route-types';
import { AssignedToMeView } from './views/AssignedToMeView';
import { PersonalListView } from './views/PersonalListView';
import { PMSView } from './views/PMSView';
import { TodayOverdueView } from './views/TodayOverdueView';

export const pmsWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'pms',
    path: '/w/:workspaceSlug/pms',
    element: <PMSView />,
  },
  {
    appId: 'pms',
    path: '/w/:workspaceSlug/pms/assigned',
    element: <AssignedToMeView />,
  },
  {
    appId: 'pms',
    path: '/w/:workspaceSlug/pms/today',
    element: <TodayOverdueView />,
  },
  {
    appId: 'pms',
    path: '/w/:workspaceSlug/pms/personal',
    element: <PersonalListView />,
  },
];
