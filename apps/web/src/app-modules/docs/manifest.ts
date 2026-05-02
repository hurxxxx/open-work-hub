import { Files, History, Lock, Mic, Share2, User } from 'lucide-react';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const docsManifest: AppModuleManifest = {
  appBarItem: { id: 'docs', title: 'docs', icon: Files },
  defaultActiveNavItemId: 'docs-all',
  navItems: [
    { id: 'docs-all', title: 'docs-all', icon: Files, category: 'Library', appId: 'docs' },
    { id: 'docs-my', title: 'docs-my', icon: User, category: 'Library', appId: 'docs' },
    { id: 'docs-shared', title: 'docs-shared', icon: Share2, category: 'Library', appId: 'docs' },
    { id: 'docs-private', title: 'docs-private', icon: Lock, category: 'Library', appId: 'docs' },
    { id: 'docs-notes', title: 'docs-notes', icon: Mic, category: 'Library', appId: 'docs' },
    { id: 'docs-recent', title: 'docs-recent', icon: History, category: 'Library', appId: 'docs' },
    { id: 'docs-archived', title: 'docs-archived', icon: History, category: 'Library', appId: 'docs' },
  ],
  workspaceRoutePaths: ['/w/:workspaceSlug/docs', '/w/:workspaceSlug/docs/:docId'],
  globalRoutePaths: ['/docs/shared/:shareToken'],
};
