import { createElement, lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { WorkspaceRouteDefinition } from '@/src/app/shell/route-types';

const VideoChatView = lazy(() =>
  import('./views/VideoChatView').then((module) => ({ default: module.VideoChatView })),
);
const VideoChatRoomPage = lazy(() =>
  import('./views/VideoChatRoomPage').then((module) => ({ default: module.VideoChatRoomPage })),
);

export const videoChatWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'video-chat',
    path: '/w/:workspaceSlug/video-chat',
    element: lazyRoute(createElement(VideoChatView)),
  },
  {
    appId: 'video-chat',
    chrome: 'fullSurface',
    path: '/w/:workspaceSlug/video-chat/:sessionId',
    element: lazyRoute(createElement(VideoChatRoomPage)),
  },
];

