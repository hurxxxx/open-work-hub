import { createElement, lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type {
  ToolViewRouteDefinition,
  WorkspaceRouteDefinition,
} from '@/src/app/shell/route-types';

const DiagramsView = lazy(() =>
  import('./views/DiagramsView').then((module) => ({
    default: module.DiagramsView,
  })),
);

export const diagramsToolElement = lazyRoute(createElement(DiagramsView));

export const diagramsToolViewRoutes: ToolViewRouteDefinition[] = [
  {
    appId: 'diagrams',
    element: diagramsToolElement,
    id: 'diagrams.main',
    match: ({ item }) => item?.appId === 'diagrams',
    type: 'element',
  },
];

export const diagramsWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'diagrams',
    path: '/w/:workspaceSlug/diagrams',
    element: diagramsToolElement,
  },
  {
    appId: 'diagrams',
    chrome: 'fullSurface',
    path: '/w/:workspaceSlug/diagrams/:diagramId',
    element: diagramsToolElement,
  },
];
