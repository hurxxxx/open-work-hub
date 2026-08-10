import { createElement, lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { WorkspaceRouteDefinition } from '@/src/app/shell/route-types';

const LearningCourseView = lazy(() =>
  import('./views/LearningCourseView').then((module) => ({ default: module.LearningCourseView })),
);
const LearningView = lazy(() =>
  import('./views/LearningView').then((module) => ({ default: module.LearningView })),
);

export const learningWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'learning',
    path: '/w/:workspaceSlug/learning',
    element: lazyRoute(createElement(LearningView)),
  },
  {
    appId: 'learning',
    path: '/w/:workspaceSlug/learning/:courseSlug',
    element: lazyRoute(createElement(LearningCourseView)),
  },
  {
    appId: 'learning',
    path: '/w/:workspaceSlug/learning/:courseSlug/:lessonSlug',
    element: lazyRoute(createElement(LearningCourseView)),
  },
];
