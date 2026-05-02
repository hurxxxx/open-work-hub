import { Calendar, User, Users, Video } from 'lucide-react';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const meetingManifest: AppModuleManifest = {
  appBarItem: { id: 'meeting', title: 'meeting', icon: Users },
  defaultActiveNavItemId: 'meeting-upcoming',
  navItems: [
    { id: 'meeting-upcoming', title: 'meeting-upcoming', icon: Calendar, category: 'Meetings', appId: 'meeting' },
    { id: 'meeting-mine', title: 'meeting-mine', icon: User, category: 'Meetings', appId: 'meeting', pathSuffix: '?scope=mine' },
    { id: 'meeting-recordings', title: 'meeting-recordings', icon: Video, category: 'Meetings', appId: 'meeting', pathSuffix: '?tab=recordings' },
  ],
  workspaceRoutePaths: ['/w/:workspaceSlug/meeting', '/w/:workspaceSlug/meeting/:meetingId'],
};
