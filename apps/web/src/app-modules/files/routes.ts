import { createElement, lazy } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  getAppRouteChrome,
  getAppRoutePattern,
} from '@open-work-hub/contracts/app-routes';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { WorkspaceRouteDefinition } from '@/src/app/shell/route-types';

const FileManagerView = lazy(() =>
  import('./views/FileManagerView').then((module) => ({
    default: module.FileManagerView,
  })),
);

const FileSearchView = lazy(() =>
  import('./views/FileSearchView').then((module) => ({
    default: module.FileSearchView,
  })),
);

const FilesChatView = lazy(() =>
  import('./views/FilesChatView').then((module) => ({
    default: module.FilesChatView,
  })),
);

function FilesWorkspaceView() {
  const [searchParams] = useSearchParams();
  const searchSelected = searchParams.get('view') === 'search';
  return lazyRoute(
    createElement(searchSelected ? FileSearchView : FileManagerView, {
      key: searchSelected ? 'search' : 'manager',
    }),
  );
}

export const filesWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'files',
    chrome: getAppRouteChrome('files.chat'),
    path: getAppRoutePattern('files.chat'),
    element: lazyRoute(createElement(FilesChatView)),
  },
  {
    appId: 'files',
    chrome: getAppRouteChrome('files.root'),
    path: getAppRoutePattern('files.root'),
    element: createElement(FilesWorkspaceView),
  },
];
