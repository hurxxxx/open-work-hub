import type { ReactNode } from 'react';

import type { WorkspaceAppId } from '@/src/platform/workspaces/workspace-utils';

export interface WorkspaceRouteDefinition {
  appId: WorkspaceAppId;
  element: ReactNode;
  path: string;
}
