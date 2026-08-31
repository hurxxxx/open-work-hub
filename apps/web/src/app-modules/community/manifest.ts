import { MessagesSquare } from 'lucide-react';
import { getAppRoutePattern } from '@open-work-hub/contracts/app-routes';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const communityManifest: AppModuleManifest = {
  appBarItem: { id: 'community', title: 'community', icon: MessagesSquare },
  contract: {
    owner: 'community-platform',
    permissions: [],
    apiDomain: 'community',
    aiCapabilities: [],
    writeAuditActions: [
      'community.channel.create',
      'community.channel.update',
      'community.channel.delete',
      'community.post.create',
      'community.post.update',
      'community.post.delete',
      'community.comment.create',
      'community.comment.update',
      'community.comment.delete',
    ],
    appLocalTests: [
      'apps/web/src/app-modules/community/manifest.spec.ts',
      'apps/api/tests/test_community.py',
    ],
  },
  defaultActiveNavItemId: '',
  navItems: [
    {
      id: 'community',
      title: 'community',
      icon: MessagesSquare,
      category: 'community',
      appId: 'community',
    },
  ],
  workspaceRoutePaths: [],
  globalRoutePaths: [
    getAppRoutePattern('community.root'),
    getAppRoutePattern('community.post'),
  ],
};
