import { Calendar, User, Users, Video } from 'lucide-react';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const meetingManifest: AppModuleManifest = {
  appBarItem: { id: 'meeting', title: 'MEETING', icon: Users },
  defaultActiveNavItemId: 'meeting-upcoming',
  navItems: [
    { id: 'meeting-upcoming', title: 'Upcoming', icon: Calendar, category: 'Meetings', appId: 'meeting' },
    { id: 'meeting-mine', title: 'My Meetings', icon: User, category: 'Meetings', appId: 'meeting', pathSuffix: '?scope=mine' },
    { id: 'meeting-recordings', title: 'Recordings', icon: Video, category: 'Meetings', appId: 'meeting', pathSuffix: '?tab=recordings' },
  ],
  workspaceRoutePaths: ['/w/:workspaceSlug/meeting', '/w/:workspaceSlug/meeting/:meetingId'],
};
