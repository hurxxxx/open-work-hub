import { Calendar, User, Users, Video } from 'lucide-react';
import { getAppRoutePattern } from '@open-work-hub/contracts/app-routes';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const meetingManifest: AppModuleManifest = {
  appBarItem: { id: 'meeting', title: 'meeting', icon: Users },
  contract: {
    owner: 'meeting-platform',
    permissions: [],
    apiDomain: 'meeting',
    workspaceApiPrefixes: ['/api/v1/meeting'],
    aiCapabilities: [
      'meeting.list_meetings',
      'meeting.get_meeting',
      'meeting.find_availability',
      'meeting.extract_actions',
      'meeting.extract_decisions',
      'meeting.draft_followup_schedule',
      'meeting.create_meeting',
    ],
    writeAuditActions: ['ai_meeting_insight_created', 'meeting.create_meeting'],
    appLocalTests: [
      'apps/web/src/app-modules/meeting/views/MeetingView/meeting-insight-chat-handoff.spec.ts',
      'apps/api/tests/test_meeting.py',
    ],
  },
  defaultActiveNavItemId: 'meeting-upcoming',
  navItems: [
    {
      id: 'meeting-upcoming',
      title: 'meeting-upcoming',
      icon: Calendar,
      category: 'Meetings',
      appId: 'meeting',
    },
    {
      id: 'meeting-mine',
      title: 'meeting-mine',
      icon: User,
      category: 'Meetings',
      appId: 'meeting',
      pathSuffix: '?scope=mine',
    },
    {
      id: 'meeting-recordings',
      title: 'meeting-recordings',
      icon: Video,
      category: 'Meetings',
      appId: 'meeting',
      pathSuffix: '?tab=recordings',
    },
  ],
  workspaceRoutePaths: [
    getAppRoutePattern('meeting.root'),
    getAppRoutePattern('meeting.detail'),
  ],
};
