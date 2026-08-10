import { createElement, lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { WorkspaceRouteDefinition } from '@/src/app/shell/route-types';

const ChatbotView = lazy(() =>
  import('./views/ChatbotView').then((module) => ({
    default: module.ChatbotView,
  })),
);

export const chatbotWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'chatbot',
    chrome: 'fullSurface',
    path: '/w/:workspaceSlug/chatbot',
    subSidebar: 'hidden',
    element: lazyRoute(createElement(ChatbotView)),
  },
];
