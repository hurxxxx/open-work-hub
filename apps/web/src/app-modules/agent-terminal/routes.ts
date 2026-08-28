import { createElement, lazy } from 'react';
import {
  getAppRouteChrome,
  getAppRoutePattern,
} from '@open-work-hub/contracts/app-routes';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { StaticRouteDefinition } from '@/src/app/shell/navigation-types';

const AgentTerminalView = lazy(() =>
  import('./views/AgentTerminalView').then((module) => ({
    default: module.AgentTerminalView,
  })),
);

export const agentTerminalGlobalRoutes: StaticRouteDefinition[] = [
  {
    chrome: getAppRouteChrome('agent-terminal.root'),
    path: getAppRoutePattern('agent-terminal.root'),
    element: lazyRoute(createElement(AgentTerminalView)),
  },
];
