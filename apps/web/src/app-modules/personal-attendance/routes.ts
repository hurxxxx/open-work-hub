import { createElement, lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { StaticRouteDefinition } from '@/src/app/shell/navigation-types';

const PersonalAttendanceView = lazy(() =>
  import('./views/PersonalAttendanceView').then((module) => ({
    default: module.PersonalAttendanceView,
  })),
);

export const personalAttendanceGlobalRoutes: StaticRouteDefinition[] = [
  {
    appId: 'personal-attendance',
    chrome: 'standard',
    path: '/personal-attendance',
    element: lazyRoute(createElement(PersonalAttendanceView)),
  },
];
