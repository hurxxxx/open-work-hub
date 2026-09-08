import type { AppShellNavResolver } from '@/src/app/shell/navigation-types';

const ADMIN_SECTION_ALIASES: Record<string, string> = {
  apps: 'apps/access',
};

export const settingsShellNavResolver: AppShellNavResolver = ({
  manifest,
  navItems,
  pathname,
}) => {
  if (pathname === '/admin' || pathname === '/admin/') {
    return manifest.defaultActiveNavItemId;
  }

  const exactItem = navItems.find((item) => item.absolutePath === pathname);
  if (exactItem) {
    return exactItem.id;
  }

  const section = pathname.split('/')[2] ?? '';
  const canonicalSection = ADMIN_SECTION_ALIASES[section] ?? section;
  const absolutePath = `/admin/${canonicalSection}`;
  return (
    navItems.find((item) => item.absolutePath === absolutePath)?.id ??
    manifest.defaultActiveNavItemId
  );
};
