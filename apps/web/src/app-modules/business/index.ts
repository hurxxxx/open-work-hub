import { businessManifest } from './manifest';
import { businessToolViewRoutes, businessWorkspaceRoutes } from './routes';
import { businessShellNavResolver } from './shell-nav';
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
  businessToolViewRoutes,
  businessWorkspaceRoutes,
};

export const businessModule = {
  manifest: businessManifest,
  shellNavResolver: businessShellNavResolver,
  toolViewRoutes: businessToolViewRoutes,
  workspaceRoutes: businessWorkspaceRoutes,
} as const;
