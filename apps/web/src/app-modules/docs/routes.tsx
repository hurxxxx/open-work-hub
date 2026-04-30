import { DocsView } from '@/src/components/views/DocsView';
import type { WorkspaceRouteDefinition } from '@/src/app/shell/route-types';

export const docsWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'docs',
    path: '/w/:workspaceSlug/docs',
    element: <DocsView />,
  },
  {
    appId: 'docs',
    path: '/w/:workspaceSlug/docs/:docId',
    element: <DocsView />,
  },
];

export const docsGlobalRoutes = [
  {
    path: '/docs/shared/:shareToken',
    element: <DocsView />,
  },
];
