import type { WorkspaceRouteDefinition } from '@/src/app/shell/route-types';
import { MeetingView } from './views/MeetingView/MeetingView';
import { MeetingWorkspaceView } from './views/MeetingView/MeetingWorkspaceView';

export const meetingWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'meeting',
    path: '/w/:workspaceSlug/meeting',
    element: <MeetingView />,
  },
  {
    appId: 'meeting',
    path: '/w/:workspaceSlug/meeting/:meetingId',
    element: <MeetingWorkspaceView />,
  },
];
