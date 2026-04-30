import { MeetingView } from '@/src/components/views/MeetingView/MeetingView';
import { MeetingWorkspaceView } from '@/src/components/views/MeetingView/MeetingWorkspaceView';
import type { WorkspaceRouteDefinition } from '@/src/app/shell/route-types';

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
