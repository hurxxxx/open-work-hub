import type { NavItem } from '@/src/app/shell/navigation-types';

const REGEXP_META_CHARACTERS = /[.*+?^${}()|[\]\\]/g;

function escapeRegExp(value: string): string {
  return value.replace(REGEXP_META_CHARACTERS, '\\$&');
}

function resolveOwnedFeatureAppId(
  candidateId: string | null | undefined,
  activeAppId: string,
  navItems: readonly Pick<NavItem, 'appId' | 'id' | 'linkAppId'>[],
): string | null {
  if (!candidateId) return null;

  const ownedItems = navItems.filter(
    (item) => item.appId === activeAppId && item.linkAppId,
  );
  const exactItem = ownedItems.find((item) => item.id === candidateId);
  if (exactItem?.linkAppId && exactItem.linkAppId !== activeAppId) {
    return exactItem.linkAppId;
  }

  const linkedAppId = ownedItems.find(
    (item) =>
      item.linkAppId !== activeAppId &&
      (candidateId === item.linkAppId ||
        candidateId.startsWith(`${item.linkAppId}-`)),
  )?.linkAppId;
  return linkedAppId ?? null;
}

export function resolveActiveFeatureAppId({
  activeAppId,
  activeNavItemId,
  navItems,
  pathname,
}: {
  activeAppId: string;
  activeNavItemId: string;
  navItems: readonly Pick<NavItem, 'appId' | 'id' | 'linkAppId'>[];
  pathname: string;
}): string | null {
  const directFeatureMatch = /^\/w\/[^/]+\/([^/?#]+)/.exec(pathname);
  const directFeatureAppId = resolveOwnedFeatureAppId(
    directFeatureMatch?.[1],
    activeAppId,
    navItems,
  );
  if (directFeatureAppId) {
    return directFeatureAppId;
  }

  const workspaceFeatureMatch = new RegExp(
    `^/w/[^/]+/${escapeRegExp(activeAppId)}/([^/?#]+)`,
  ).exec(pathname);
  const nestedFeatureAppId = resolveOwnedFeatureAppId(
    workspaceFeatureMatch?.[1],
    activeAppId,
    navItems,
  );
  if (nestedFeatureAppId) {
    return nestedFeatureAppId;
  }

  const toolRouteAppId = resolveOwnedFeatureAppId(
    /^\/tool\/([^/?#]+)/.exec(pathname)?.[1],
    activeAppId,
    navItems,
  );
  return (
    toolRouteAppId ??
    resolveOwnedFeatureAppId(activeNavItemId, activeAppId, navItems)
  );
}
