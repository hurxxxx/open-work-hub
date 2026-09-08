import {
  getAppRouteChrome,
  getAppRoutePattern,
} from '@open-work-hub/contracts/app-routes';
import { createElement, lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { AppRouteDefinition } from '@/src/app/shell/route-types';

const ChatbotView = lazy(() =>
  import('./views/ChatbotView').then((module) => ({
    default: module.ChatbotView,
  })),
);

export const chatbotAppRoutes: AppRouteDefinition[] = [
  {
    appId: 'chatbot',
    chrome: getAppRouteChrome('chatbot.root'),
    path: getAppRoutePattern('chatbot.root'),
    element: lazyRoute(createElement(ChatbotView)),
  },
];
