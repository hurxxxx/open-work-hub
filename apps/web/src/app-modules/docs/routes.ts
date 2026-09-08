import {
  getAppRouteChrome,
  getAppRoutePattern,
} from '@open-work-hub/contracts/app-routes';
import { createElement, lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { StaticRouteDefinition } from '@/src/app/shell/navigation-types';
import type { AppRouteDefinition } from '@/src/app/shell/route-types';

const DocsView = lazy(() =>
  import('./views/DocsView').then((module) => ({ default: module.DocsView })),
);
const DocsHtmlRenderPage = lazy(() =>
  import('./views/DocsHtmlRenderPage').then((module) => ({
    default: module.DocsHtmlRenderPage,
  })),
);

export const docsToolElement = lazyRoute(createElement(DocsView));
const docsHtmlRenderElement = lazyRoute(createElement(DocsHtmlRenderPage));

export const docsAppRoutes: AppRouteDefinition[] = [
  {
    appId: 'docs',
    chrome: getAppRouteChrome('docs.root'),
    path: getAppRoutePattern('docs.root'),
    element: docsToolElement,
  },
  {
    appId: 'docs',
    chrome: getAppRouteChrome('docs.document'),
    path: getAppRoutePattern('docs.document'),
    element: docsToolElement,
  },
  {
    appId: 'docs',
    chrome: getAppRouteChrome('docs.document-html'),
    path: getAppRoutePattern('docs.document-html'),
    element: docsHtmlRenderElement,
  },
];

export const docsGlobalRoutes: StaticRouteDefinition[] = [
  {
    chrome: getAppRouteChrome('docs.shared'),
    path: getAppRoutePattern('docs.shared'),
    element: docsToolElement,
  },
  {
    chrome: getAppRouteChrome('docs.shared-html'),
    path: getAppRoutePattern('docs.shared-html'),
    element: docsHtmlRenderElement,
  },
];
