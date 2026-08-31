import { createElement, lazy } from 'react';
import { Navigate, useParams } from 'react-router-dom';
import {
  getAppRouteChrome,
  getAppRoutePattern,
} from '@open-work-hub/contracts/app-routes';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { WorkspaceRouteDefinition } from '@/src/app/shell/route-types';
import { buildBentoPresentationPath } from './bento-route-paths';

const BentoView = lazy(() =>
  import('./views/BentoView').then((module) => ({
    default: module.BentoView,
  })),
);

function BentoLegacyPresentationRedirect() {
  const { workspaceSlug, documentId } = useParams();
  const destination =
    workspaceSlug && documentId
      ? buildBentoPresentationPath(workspaceSlug, documentId)
      : '/';
  return createElement(Navigate, { replace: true, to: destination });
}

export const bentoWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'bento',
    chrome: getAppRouteChrome('bento.root'),
    path: getAppRoutePattern('bento.root'),
    element: lazyRoute(createElement(BentoView)),
  },
  {
    appId: 'bento',
    chrome: getAppRouteChrome('bento.presentation'),
    path: getAppRoutePattern('bento.presentation'),
    element: lazyRoute(createElement(BentoView)),
  },
  {
    appId: 'bento',
    chrome: getAppRouteChrome('bento.presentation-legacy'),
    path: getAppRoutePattern('bento.presentation-legacy'),
    element: createElement(BentoLegacyPresentationRedirect),
  },
];
