import { getAppRelativePath } from '@/src/app-shell-navigation-model';
import type { AppShellNavResolver } from '@/src/app/shell/navigation-types';

function decodePathSegment(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

export const pmsShellNavResolver: AppShellNavResolver = ({ pathname }) => {
  const relativePath = getAppRelativePath(pathname, 'pms');
  if (relativePath === '/assigned' || relativePath?.startsWith('/assigned/')) {
    return 'pms-tasks-assigned';
  }
  if (relativePath === '/today' || relativePath?.startsWith('/today/')) {
    return 'pms-tasks-today';
  }
  const listMatch = relativePath?.match(/^\/lists\/([^/]+)/);
  if (listMatch?.[1]) {
    return `pms-list-${decodePathSegment(listMatch[1])}`;
  }
  const spaceMatch = relativePath?.match(
    /^\/spaces\/([^/]+)(?:\/(docs|whiteboards)(?:\/([^/]+))?)?/,
  );
  if (spaceMatch?.[1]) {
    const spaceId = decodePathSegment(spaceMatch[1]);
    const section = spaceMatch[2];
    const resourceId = spaceMatch[3] ? decodePathSegment(spaceMatch[3]) : null;
    if (section === 'docs') {
      return resourceId
        ? `pms-space-${spaceId}-docs-${resourceId}`
        : `pms-space-${spaceId}-docs`;
    }
    if (section === 'whiteboards') {
      return resourceId
        ? `pms-space-${spaceId}-whiteboards-${resourceId}`
        : `pms-space-${spaceId}-whiteboards`;
    }
    return `pms-space-${spaceId}`;
  }
  return null;
};
