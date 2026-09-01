import { createElement, lazy } from 'react';
import {
  getAppRouteChrome,
  getAppRoutePattern,
} from '@open-work-hub/contracts/app-routes';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { WorkspaceRouteDefinition } from '@/src/app/shell/route-types';

const HermesTerminalView = lazy(() =>
  import('./views/HermesTerminalView').then((module) => ({
    default: module.HermesTerminalView,
  })),
);

export const hermesTerminalWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'hermes-terminal',
    chrome: getAppRouteChrome('hermes-terminal.root'),
    path: getAppRoutePattern('hermes-terminal.root'),
    element: lazyRoute(createElement(HermesTerminalView)),
  },
];
