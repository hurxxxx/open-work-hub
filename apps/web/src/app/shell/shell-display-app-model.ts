import { getAppIdFromPath } from '@/src/platform/apps/app-links';

export function resolveShellDisplayAppId({
  activeAppId,
  pathname,
}: {
  activeAppId: string;
  pathname: string;
}): string {
  return getAppIdFromPath(pathname) ?? activeAppId;
}
