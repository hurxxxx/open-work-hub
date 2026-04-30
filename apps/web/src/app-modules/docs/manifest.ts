import { Files, History, Lock, Mic, Share2, User } from 'lucide-react';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const docsManifest: AppModuleManifest = {
  appBarItem: { id: 'docs', title: 'DOCS', icon: Files },
  defaultActiveNavItemId: 'docs-all',
  navItems: [
    { id: 'docs-all', title: 'All Docs', icon: Files, category: 'Library', appId: 'docs' },
    { id: 'docs-my', title: 'My Docs', icon: User, category: 'Library', appId: 'docs' },
    { id: 'docs-shared', title: 'Shared with me', icon: Share2, category: 'Library', appId: 'docs' },
    { id: 'docs-private', title: 'Private', icon: Lock, category: 'Library', appId: 'docs' },
    { id: 'docs-notes', title: 'Meeting Notes', icon: Mic, category: 'Library', appId: 'docs' },
    { id: 'docs-recent', title: 'Recent Pages', icon: History, category: 'Library', appId: 'docs' },
    { id: 'docs-archived', title: 'Archived', icon: History, category: 'Library', appId: 'docs' },
  ],
  workspaceRoutePaths: ['/w/:workspaceSlug/docs', '/w/:workspaceSlug/docs/:docId'],
  globalRoutePaths: ['/docs/shared/:shareToken'],
};
