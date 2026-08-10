import { buildWorkspaceAppPath } from '@/src/platform/workspaces/workspace-utils';

export function buildPptAssistantPath(
  appId: string,
  workspaceSlug: string,
  pathSuffix = '',
): string {
  return buildWorkspaceAppPath(workspaceSlug, appId, pathSuffix);
}

export function buildPptAssistantJobPath(
  appId: string,
  workspaceSlug: string,
  jobId: string,
): string {
  return buildPptAssistantPath(
    appId,
    workspaceSlug,
    `/jobs/${encodeURIComponent(jobId)}`,
  );
}
