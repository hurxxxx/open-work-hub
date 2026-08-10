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
    path: '/mail',
    element: lazyRoute(createElement(MailView)),
  },
];
