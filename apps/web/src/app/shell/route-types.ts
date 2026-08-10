import type { ReactNode } from 'react';

import type {
  NavItem,
  ShellRouteChrome,
  ShellRouteSubSidebar,
} from './navigation-types';
import type { WorkspaceAppId } from '@/src/platform/workspaces/workspace-utils';

export interface WorkspaceRouteDefinition {
  appId: WorkspaceAppId;
  /** Bootstrap entitlement used when a shell parent owns a leaf app route. */
  bootstrapAppId?: WorkspaceAppId;
  chrome?: ShellRouteChrome;
  element: ReactNode;
  path: string;
  subSidebar?: ShellRouteSubSidebar;
}

export type ToolViewRouteMatchContext = {
  item: NavItem | null;
  toolId: string;
};

export type ToolViewAccessDeniedReason =
  | 'tool_workspace_denied'
  | 'app_disabled'
  | 'workspace_search_disabled'
  | 'image_wizard_disabled';

export type ToolViewRouteGate =
  | {
      /**
       * Shell-wide search availability comes from enabled search-source apps,
       * not from the route owner's app entitlement. Workspace context checks
       * still run before this gate is evaluated.
       */
      deniedReason?: ToolViewAccessDeniedReason;
      type: 'workspace_search';
    }
  | {
      deniedReason: ToolViewAccessDeniedReason;
      navItemId: string;
      type: 'bootstrap_nav_item';
    };

export type ToolViewRouteDefinition =
  | {
      appId: WorkspaceAppId;
      /** Bootstrap entitlement used when a shell parent owns a leaf tool route. */
      bootstrapAppId?: WorkspaceAppId;
      element: ReactNode;
      gates?: readonly ToolViewRouteGate[];
      id: string;
      match: (context: ToolViewRouteMatchContext) => boolean;
      /**
       * Concrete tool ids this route owns. The app registry validates these ids
       * against every route matcher so broad dynamic matchers cannot shadow them.
       */
      toolIds?: readonly string[];
      type: 'element';
    }
  | {
      appId: WorkspaceAppId;
      /** Bootstrap entitlement used when a shell parent owns a leaf tool route. */
      bootstrapAppId?: WorkspaceAppId;
      id: string;
      match: (context: ToolViewRouteMatchContext) => boolean;
      toolIds?: readonly string[];
      type: 'redirect_app_root';
    };

export type ToolViewRouteMatch =
  | Omit<
      Extract<ToolViewRouteDefinition, { type: 'element' }>,
      'element' | 'match'
    >
  | Omit<
      Extract<ToolViewRouteDefinition, { type: 'redirect_app_root' }>,
      'match'
    >;
