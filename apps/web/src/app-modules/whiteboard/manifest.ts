import { History, PencilRuler, Star, User } from 'lucide-react';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const whiteboardManifest: AppModuleManifest = {
  appBarItem: { id: 'whiteboard', title: 'whiteboard', icon: PencilRuler },
  defaultActiveNavItemId: 'whiteboard-all',
  navItems: [
    { id: 'whiteboard-all', title: 'whiteboard-all', icon: PencilRuler, category: 'Library', appId: 'whiteboard' },
    { id: 'whiteboard-my', title: 'whiteboard-my', icon: User, category: 'Library', appId: 'whiteboard', pathSuffix: '?view=mine' },
    { id: 'whiteboard-recent', title: 'whiteboard-recent', icon: History, category: 'Library', appId: 'whiteboard', pathSuffix: '?view=recent' },
    { id: 'whiteboard-favorites', title: 'whiteboard-favorites', icon: Star, category: 'Library', appId: 'whiteboard', pathSuffix: '?view=favorites' },
    { id: 'whiteboard-archived', title: 'whiteboard-archived', icon: History, category: 'Library', appId: 'whiteboard', pathSuffix: '?view=archived' },
  ],
  workspaceRoutePaths: ['/w/:workspaceSlug/whiteboard', '/w/:workspaceSlug/whiteboard/:whiteboardId'],
  globalRoutePaths: ['/whiteboard/shared/:shareToken'],
};
