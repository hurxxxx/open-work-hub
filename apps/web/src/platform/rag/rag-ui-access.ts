import type { BootstrapNavItem } from '@/src/platform/apps/apps-api';

export { getEnabledAppIds, isAppEnabled } from '@/src/platform/apps/app-access';

export function isNavItemEnabled(
  nav: readonly Pick<BootstrapNavItem, 'id'>[] | null | undefined,
  itemId: string,
): boolean {
  return (nav ?? []).some((item) => item.id === itemId);
}
