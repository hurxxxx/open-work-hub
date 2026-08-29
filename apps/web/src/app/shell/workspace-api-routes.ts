import { createWorkspaceApiRoutePolicy } from '@/src/platform/api/workspace-api-route-policy';
import { DEFAULT_PLATFORM_CONTRACT_MANIFESTS } from './app-contract-manifests';

export const APP_WORKSPACE_API_ROUTE_POLICY = createWorkspaceApiRoutePolicy({
  sources: DEFAULT_PLATFORM_CONTRACT_MANIFESTS,
});
