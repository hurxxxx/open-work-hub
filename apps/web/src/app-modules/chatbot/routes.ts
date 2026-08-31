import { createElement, lazy } from 'react';
import {
  getAppRouteChrome,
  getAppRoutePattern,
} from '@open-work-hub/contracts/app-routes';

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
    chrome: getAppRouteChrome('chatbot.root'),
    path: getAppRoutePattern('chatbot.root'),
    element: lazyRoute(createElement(ChatbotView)),
  },
];
