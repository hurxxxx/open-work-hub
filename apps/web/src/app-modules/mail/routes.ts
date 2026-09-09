import {
  getAppRouteChrome,
  getAppRoutePattern,
} from '@open-work-hub/contracts/app-routes';
import { createElement, lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { StaticRouteDefinition } from '@/src/app/shell/navigation-types';

const MailView = lazy(() =>
  import('./views/MailView').then((module) => ({
    default: module.MailView,
  })),
);

export const mailGlobalRoutes: StaticRouteDefinition[] = [
  {
    chrome: getAppRouteChrome('mail.root'),
    path: getAppRoutePattern('mail.root'),
    element: lazyRoute(createElement(MailView)),
  },
];
