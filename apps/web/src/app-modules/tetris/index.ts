import {
  getAppRouteChrome,
  getAppRoutePattern,
} from '@open-work-hub/contracts/app-routes';
import { createElement, lazy } from 'react';
import { lazyRoute } from '@/src/app/shell/lazy-route';
import { tetrisManifest } from './manifest';
const TetrisView = lazy(() =>
  import('./TetrisView').then((module) => ({ default: module.TetrisView })),
);
export const tetrisModule = {
  manifest: tetrisManifest,
  globalRoutes: [
    {
      path: getAppRoutePattern('tetris.root'),
      chrome: getAppRouteChrome('tetris.root'),
      element: lazyRoute(createElement(TetrisView)),
    },
  ],
};
