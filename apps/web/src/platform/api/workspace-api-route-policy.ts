export type WorkspaceApiPublicQueryBypass = {
  pathPrefixes: readonly string[];
  queryParam: string;
};

export type WorkspaceApiRoutePolicy = {
  prefixes: readonly string[];
  publicPrefixes: readonly string[];
  publicQueryBypasses: readonly WorkspaceApiPublicQueryBypass[];
};

export type WorkspaceApiRoutePolicySource = {
  contract?: {
    workspaceApiPrefixes?: readonly string[];
    workspaceApiPublicPrefixes?: readonly string[];
    workspaceApiPublicQueryBypasses?: readonly WorkspaceApiPublicQueryBypass[];
  };
};

export const PLATFORM_WORKSPACE_API_PREFIXES = [
  '/api/v1/connectors',
  '/api/v1/drafts',
  '/api/v1/rag',
  '/api/v1/search',
  '/api/v1/wiki',
] as const;

export function createWorkspaceApiRoutePolicy({
  platformPrefixes = PLATFORM_WORKSPACE_API_PREFIXES,
  sources,
}: {
  platformPrefixes?: readonly string[];
  sources: readonly WorkspaceApiRoutePolicySource[];
}): WorkspaceApiRoutePolicy {
  const prefixes = uniqueApiPathPrefixes([
    ...platformPrefixes,
    ...sources.flatMap((source) => source.contract?.workspaceApiPrefixes ?? []),
  ]);
  const publicPrefixes = uniqueApiPathPrefixes(
    sources.flatMap(
      (source) => source.contract?.workspaceApiPublicPrefixes ?? [],
    ),
  );
  const publicQueryBypasses = sources.flatMap((source) =>
    (source.contract?.workspaceApiPublicQueryBypasses ?? []).map((bypass) => ({
      pathPrefixes: uniqueApiPathPrefixes(bypass.pathPrefixes),
      queryParam: bypass.queryParam,
    })),
  );
  return { prefixes, publicPrefixes, publicQueryBypasses };
}

export function matchesWorkspaceApiPrefix(
  rawPath: string,
  prefixes: readonly string[],
): boolean {
  return prefixes.some((prefix) => pathMatchesApiPrefix(rawPath, prefix));
}

export function isPublicWorkspaceApiPath(
  rawPath: string,
  policy: WorkspaceApiRoutePolicy,
): boolean {
  const path = rawPath.split(/[?#]/, 1)[0];
  if (
    policy.publicPrefixes.some((prefix) => pathMatchesApiPrefix(path, prefix))
  ) {
    return true;
  }
  return policy.publicQueryBypasses.some(
    (bypass) =>
      hasQueryParam(rawPath, bypass.queryParam) &&
      bypass.pathPrefixes.some((prefix) => pathMatchesApiPrefix(path, prefix)),
  );
}

function pathMatchesApiPrefix(path: string, prefix: string): boolean {
  return path === prefix || path.startsWith(`${prefix}/`);
}

function uniqueApiPathPrefixes(prefixes: readonly string[]): string[] {
  return [...new Set(prefixes.map(normalizeApiPathPrefix))].sort();
}

function normalizeApiPathPrefix(prefix: string): string {
  const normalized = prefix.trim().replace(/\/+$/, '');
  if (!normalized.startsWith('/api/v1/')) {
    throw new Error(`Workspace API prefix must start with /api/v1/: ${prefix}`);
  }
  return normalized;
}

function hasQueryParam(rawPath: string, queryParam: string): boolean {
  const queryStart = rawPath.indexOf('?');
  if (queryStart < 0) {
    return false;
  }
  const hashStart = rawPath.indexOf('#', queryStart);
  const query = rawPath.slice(
    queryStart + 1,
    hashStart >= 0 ? hashStart : undefined,
  );
  return new URLSearchParams(query).has(queryParam);
}
