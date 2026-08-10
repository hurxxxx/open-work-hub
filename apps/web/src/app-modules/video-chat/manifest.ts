import { Video } from 'lucide-react';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const videoChatManifest: AppModuleManifest = {
  appBarItem: { id: 'video-chat', title: 'video-chat', icon: Video },
  contract: {
    owner: 'video-chat-platform',
    permissions: [],
    apiDomain: 'video_chat',
    workspaceApiPrefixes: ['/api/v1/video-chat'],
    aiCapabilities: [],
    writeAuditActions: [],
    appLocalTests: [
      'apps/api/tests/test_video_chat.py',
      'apps/web/src/app-modules/video-chat/views/VideoChatView.tsx',
    ],
  },
  defaultActiveNavItemId: 'video-chat-room',
  navItems: [
    {
      id: 'video-chat-room',
      title: 'video-chat-room',
      icon: Video,
      category: 'Meetings',
      appId: 'video-chat',
    },
  ],
  workspaceRoutePaths: [
    '/w/:workspaceSlug/video-chat',
    '/w/:workspaceSlug/video-chat/:sessionId',
  ],
};

