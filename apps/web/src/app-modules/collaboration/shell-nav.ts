import type { AppShellNavResolver } from '@/src/app/shell/navigation-types';
import { pmsShellNavResolver } from '@/src/app-modules/pms';
import { recordingShellNavResolver } from '@/src/app-modules/recording';

export const collaborationShellNavResolver: AppShellNavResolver = (context) => {
  const featureMatch = /^\/w\/[^/]+\/([^/?#]+)/.exec(context.pathname);
  const featureAppId = featureMatch?.[1] ?? null;

  if (featureAppId === 'pms') {
    const pmsNavItemId = pmsShellNavResolver({
      ...context,
      appId: 'pms',
    });
    if (pmsNavItemId !== null && pmsNavItemId !== undefined) {
      return pmsNavItemId;
    }
  }

  if (featureAppId === 'recording') {
    return recordingShellNavResolver({
      ...context,
      appId: 'recording',
    });
  }

  return null;
};
