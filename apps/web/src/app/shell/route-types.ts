import type { ReactNode } from 'react';

import type {
  ShellRouteChrome,
  ShellRouteSubSidebar,
} from './navigation-types';
import type { WorkspaceAppId } from '@/src/platform/workspaces/workspace-utils';

export interface WorkspaceRouteDefinition {
  appId: WorkspaceAppId;
  chrome?: ShellRouteChrome;
  element: ReactNode;
  path: string;
  subSidebar?: ShellRouteSubSidebar;
}

/** Tool/parent routes cannot create executable app identities outside the contract. */
export type ToolViewRouteDefinition = never;
export type ToolViewRouteMatch = never;
