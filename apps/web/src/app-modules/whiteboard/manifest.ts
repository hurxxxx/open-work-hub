import { History, PencilRuler, Star, User } from 'lucide-react';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const whiteboardManifest: AppModuleManifest = {
  appBarItem: { id: 'whiteboard', title: 'WHITEBOARD', icon: PencilRuler },
  defaultActiveNavItemId: 'whiteboard-all',
  navItems: [
    { id: 'whiteboard-all', title: 'All Whiteboards', icon: PencilRuler, category: 'Library', appId: 'whiteboard' },
    { id: 'whiteboard-my', title: 'My Whiteboards', icon: User, category: 'Library', appId: 'whiteboard', pathSuffix: '?view=mine' },
    { id: 'whiteboard-recent', title: 'Recent', icon: History, category: 'Library', appId: 'whiteboard', pathSuffix: '?view=recent' },
    { id: 'whiteboard-favorites', title: 'Favorites', icon: Star, category: 'Library', appId: 'whiteboard', pathSuffix: '?view=favorites' },
    { id: 'whiteboard-archived', title: 'Archived', icon: History, category: 'Library', appId: 'whiteboard', pathSuffix: '?view=archived' },
  ],
  workspaceRoutePaths: ['/w/:workspaceSlug/whiteboard', '/w/:workspaceSlug/whiteboard/:whiteboardId'],
  globalRoutePaths: ['/whiteboard/shared/:shareToken'],
};
