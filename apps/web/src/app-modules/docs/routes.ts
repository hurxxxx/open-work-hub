import { createElement, lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { StaticRouteDefinition } from '@/src/app/shell/navigation-types';
import type {
  ToolViewRouteDefinition,
  WorkspaceRouteDefinition,
} from '@/src/app/shell/route-types';

const DocsView = lazy(() => import('./views/DocsView').then((module) => ({ default: module.DocsView })));
const DocsHtmlRenderPage = lazy(() => import('./views/DocsHtmlRenderPage').then((module) => ({ default: module.DocsHtmlRenderPage })));

export const docsToolElement = lazyRoute(createElement(DocsView));
const docsHtmlRenderElement = lazyRoute(createElement(DocsHtmlRenderPage));

export const docsToolViewRoutes: ToolViewRouteDefinition[] = [
  {
    appId: 'docs',
    element: docsToolElement,
    id: 'docs.main',
    match: ({ item }) => item?.appId === 'docs',
    type: 'element',
  },
];

export const docsWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'docs',
    path: '/w/:workspaceSlug/docs',
    element: docsToolElement,
  },
  {
    appId: 'docs',
    path: '/w/:workspaceSlug/docs/:docId',
    element: docsToolElement,
  },
  {
    appId: 'docs',
    chrome: 'fullSurface',
    path: '/w/:workspaceSlug/docs/:docId/html/:pageId',
    element: docsHtmlRenderElement,
  },
];

export const docsGlobalRoutes: StaticRouteDefinition[] = [
  {
    path: '/docs/shared/:shareToken',
    element: docsToolElement,
  },
  {
    chrome: 'fullSurface',
    path: '/docs/shared/:shareToken/html/:pageId',
    element: docsHtmlRenderElement,
  },
];
