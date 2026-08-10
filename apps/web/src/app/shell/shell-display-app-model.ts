import { getWorkspaceAppIdFromPath } from '@/src/platform/workspaces/workspace-utils';

export function resolveShellDisplayAppId({
  activeAppId,
  pathname,
}: {
  activeAppId: string;
  pathname: string;
}): string {
  return getWorkspaceAppIdFromPath(pathname) ?? activeAppId;
}
