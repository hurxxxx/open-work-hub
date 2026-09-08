import {
  getAppRouteChrome,
  getAppRoutePattern,
} from '@open-work-hub/contracts/app-routes';
import { createElement, lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { AppRouteDefinition } from '@/src/app/shell/route-types';

const VideoChatView = lazy(() =>
  import('./views/VideoChatView').then((module) => ({
    default: module.VideoChatView,
  })),
);
const VideoChatRoomPage = lazy(() =>
  import('./views/VideoChatRoomPage').then((module) => ({
    default: module.VideoChatRoomPage,
  })),
);

export const videoChatAppRoutes: AppRouteDefinition[] = [
  {
    appId: 'video-chat',
    chrome: getAppRouteChrome('video-chat.root'),
    path: getAppRoutePattern('video-chat.root'),
    element: lazyRoute(createElement(VideoChatView)),
  },
  {
    appId: 'video-chat',
    chrome: getAppRouteChrome('video-chat.session'),
    path: getAppRoutePattern('video-chat.session'),
    element: lazyRoute(createElement(VideoChatRoomPage)),
  },
];
