import { createElement, lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { StaticRouteDefinition } from '@/src/app/shell/navigation-types';

const AgentTerminalView = lazy(() =>
  import('./views/AgentTerminalView').then((module) => ({
    default: module.AgentTerminalView,
  })),
);

export const agentTerminalGlobalRoutes: StaticRouteDefinition[] = [
  {
    chrome: 'fullSurface',
    path: '/agent-terminal',
    element: lazyRoute(createElement(AgentTerminalView)),
  },
];
