import type { ReactNode } from 'react';

import type { ShellAppId } from '@/src/platform/apps/app-links';
import type {
  ShellRouteChrome,
  ShellRouteSubSidebar,
} from './navigation-types';

export interface AppRouteDefinition {
  appId: ShellAppId;
  chrome?: ShellRouteChrome;
  element: ReactNode;
  path: string;
  subSidebar?: ShellRouteSubSidebar;
}

/** Tool/parent routes cannot create executable app identities outside the contract. */
export type ToolViewRouteDefinition = never;
export type ToolViewRouteMatch = never;
