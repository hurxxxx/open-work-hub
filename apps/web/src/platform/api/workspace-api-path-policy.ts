import {
  createWorkspaceApiRoutePolicy,
  isPublicWorkspaceApiPath,
  matchesWorkspaceApiPrefix,
  type WorkspaceApiRoutePolicy,
} from './workspace-api-route-policy';

const DEFAULT_WORKSPACE_API_ROUTE_POLICY = createWorkspaceApiRoutePolicy({
  sources: [],
});

let activeWorkspaceApiRoutePolicy: WorkspaceApiRoutePolicy =
  DEFAULT_WORKSPACE_API_ROUTE_POLICY;

export function configureWorkspaceApiRoutePolicy(
  policy: WorkspaceApiRoutePolicy,
): void {
  activeWorkspaceApiRoutePolicy = policy;
}

export function resetWorkspaceApiRoutePolicy(): void {
  activeWorkspaceApiRoutePolicy = DEFAULT_WORKSPACE_API_ROUTE_POLICY;
}

export function getWorkspaceApiRoutePolicy(): WorkspaceApiRoutePolicy {
  return activeWorkspaceApiRoutePolicy;
}

export function getWorkspaceApiPrefixes(): readonly string[] {
  return getWorkspaceApiRoutePolicy().prefixes;
}

function shouldRewriteWorkspaceApiPath(
  rawPath: string,
  policy: WorkspaceApiRoutePolicy,
): boolean {
  const path = rawPath.split(/[?#]/, 1)[0];
  return (
    path.startsWith('/api/v1/') &&
    !path.startsWith('/api/v1/workspaces/') &&
    !isPublicWorkspaceApiPath(rawPath, policy) &&
    matchesWorkspaceApiPrefix(path, policy.prefixes)
  );
}

export function rewriteWorkspaceApiPathForWorkspace(
  rawPath: string,
  workspaceSlug: string | null | undefined,
  policy: WorkspaceApiRoutePolicy = getWorkspaceApiRoutePolicy(),
): string {
  if (!workspaceSlug || !shouldRewriteWorkspaceApiPath(rawPath, policy)) {
    return rawPath;
  }
  return `/api/v1/workspaces/${encodeURIComponent(workspaceSlug)}${rawPath.slice('/api/v1'.length)}`;
}
