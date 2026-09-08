import { getAppRoutePattern } from '@open-work-hub/contracts/app-routes';
import { Files, History, Lock, Mic, Share2, User } from 'lucide-react';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const docsManifest: AppModuleManifest = {
  appBarItem: { id: 'docs', title: 'docs', icon: Files },
  contract: {
    owner: 'docs-platform',
    permissions: [],
    apiDomain: 'docs',
    aiCapabilities: [
      'docs.list_hub',
      'docs.get_item',
      'docs.list_pages',
      'docs.read_page',
    ],
    writeAuditActions: [],
    appLocalTests: [
      'apps/web/src/app-modules/docs/views/docs-view-model.spec.ts',
      'apps/api/tests/test_docs_hub.py',
    ],
  },
  defaultActiveNavItemId: 'docs-all',
  navItems: [
    {
      id: 'docs-all',
      title: 'docs-all',
      icon: Files,
      category: 'Library',
      appId: 'docs',
    },
    {
      id: 'docs-my',
      title: 'docs-my',
      icon: User,
      category: 'Library',
      appId: 'docs',
      pathSuffix: '?view=mine',
    },
    {
      id: 'docs-shared',
      title: 'docs-shared',
      icon: Share2,
      category: 'Library',
      appId: 'docs',
      pathSuffix: '?view=shared',
    },
    {
      id: 'docs-private',
      title: 'docs-private',
      icon: Lock,
      category: 'Library',
      appId: 'docs',
      pathSuffix: '?view=private',
    },
    {
      id: 'docs-notes',
      title: 'docs-notes',
      icon: Mic,
      category: 'Library',
      appId: 'docs',
      pathSuffix: '?view=meeting_notes',
    },
    {
      id: 'docs-recent',
      title: 'docs-recent',
      icon: History,
      category: 'Library',
      appId: 'docs',
      pathSuffix: '?view=recent',
    },
    {
      id: 'docs-archived',
      title: 'docs-archived',
      icon: History,
      category: 'Library',
      appId: 'docs',
      pathSuffix: '?view=archived',
    },
  ],
  appRoutePaths: [
    getAppRoutePattern('docs.root'),
    getAppRoutePattern('docs.document'),
    getAppRoutePattern('docs.document-html'),
  ],
  globalRoutePaths: [
    getAppRoutePattern('docs.shared'),
    getAppRoutePattern('docs.shared-html'),
  ],
};
