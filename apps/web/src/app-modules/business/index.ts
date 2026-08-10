import { businessManifest } from './manifest';
import { businessToolViewRoutes, businessWorkspaceRoutes } from './routes';
import { businessShellNavResolver } from './shell-nav';
import { businessSidebarConfig } from './sidebar';
import {
  businessFeatureModuleRegistry,
  businessFeatureModules,
  businessFeatureShellRegistrations,
} from './feature-modules';

export {
  businessManifest,
  businessFeatureModuleRegistry,
  businessFeatureModules,
  businessFeatureShellRegistrations,
  businessShellNavResolver,
  businessSidebarConfig,
  businessToolViewRoutes,
  businessWorkspaceRoutes,
};

export const businessModule = {
  manifest: businessManifest,
  shellNavResolver: businessShellNavResolver,
  sidebarConfig: businessSidebarConfig,
  toolViewRoutes: businessToolViewRoutes,
  workspaceRoutes: businessWorkspaceRoutes,
} as const;
