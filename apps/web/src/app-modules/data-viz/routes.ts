import { createElement, lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type {
  ToolViewRouteDefinition,
  WorkspaceRouteDefinition,
} from '@/src/app/shell/route-types';

const DataVizView = lazy(() =>
  import('./views/DataVizView').then((module) => ({
    default: module.DataVizView,
  })),
);

const dataVizElement = lazyRoute(createElement(DataVizView));

export const dataVizToolViewRoutes: ToolViewRouteDefinition[] = [
  {
    appId: 'data-viz',
    element: dataVizElement,
    id: 'data-viz.main',
    match: ({ toolId }) => toolId === 'data-viz',
    toolIds: ['data-viz'],
    type: 'element',
  },
];

export const dataVizWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'data-viz',
    path: '/w/:workspaceSlug/data-viz',
    element: dataVizElement,
  },
];
