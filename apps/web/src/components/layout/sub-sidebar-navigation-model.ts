import type { NavItem } from '@/src/app/shell/navigation-types';
import type { AppSidebarConfig } from '@/src/app/shell/sidebar-types';
import {
  hasConfiguredAdminSectionAccess,
  type AdminSectionAccessResolver,
} from '@/src/platform/admin/admin-permissions';
import type { BootstrapNavItem } from '@/src/platform/apps/apps-api';

import { buildSidebarCategories } from './sub-sidebar-categories';
export {
  normalizeSubSidebarCategoryExpansionState,
  subSidebarCategoryExpansionKey,
  toggleSubSidebarCategoryExpansion,
  type SubSidebarCategoryExpansionState,
} from './sub-sidebar-categories';

type TranslateSidebarLabel = (
  key: string,
  options?: Record<string, unknown>,
) => string;

export interface SubSidebarNavigationProjection {
  categories: string[];
  filteredItems: NavItem[];
}

export interface BuildSubSidebarNavigationProjectionInput {
  activeAppId: string;
  canReadApp: boolean;
  extendCategories?: AppSidebarConfig['extendCategories'];
  globalAppIds?: readonly string[];
  hasAdminSectionAccess?: AdminSectionAccessResolver;
  navItems: readonly NavItem[];
  systemRoles: readonly string[];
  translate: TranslateSidebarLabel;
  appNavItems: readonly BootstrapNavItem[];
}

const ADMIN_SECTION_ALIASES: Record<string, string> = {
  users: 'people',
};

function translateNavItem(
  item: NavItem,
  translate: TranslateSidebarLabel,
): NavItem {
  return {
    ...item,
    title: translate(`nav.${item.id}`, { defaultValue: item.title }),
    category: translate(`categories.${item.category}`, {
      defaultValue: item.category,
    }),
  };
}

function buildAppNavItems({
  activeAppId,
  navItems,
  translate,
  appNavItems,
}: Pick<
  BuildSubSidebarNavigationProjectionInput,
  'activeAppId' | 'navItems' | 'translate' | 'appNavItems'
>): NavItem[] {
  const navItemRegistry = new Map(navItems.map((item) => [item.id, item]));
  const items: NavItem[] = [];
  for (const item of appNavItems) {
    if (item.app_id !== activeAppId) {
      continue;
    }
    const localItem = navItemRegistry.get(item.id);
    if (!localItem) {
      throw new Error(
        `App nav item ${item.id} for ${item.app_id} is missing from the web app registry`,
      );
    }
    const nextItem: NavItem = {
      ...localItem,
      title: translate(`nav.${item.id}`, { defaultValue: item.title }),
      category: translate(`categories.${item.category}`, {
        defaultValue: item.category,
      }),
    };
    if (item.path_suffix !== undefined && item.path_suffix !== null) {
      nextItem.pathSuffix = item.path_suffix;
    }
    if (item.absolute_path !== undefined && item.absolute_path !== null) {
      nextItem.absolutePath = item.absolute_path;
    }
    if (item.link_app_id !== undefined && item.link_app_id !== null) {
      nextItem.linkAppId = item.link_app_id as NavItem['linkAppId'];
    }
    if (item.coming_soon) {
      nextItem.comingSoon = true;
    }
    items.push(nextItem);
  }
  return items;
}

function buildSettingsNavItems({
  activeAppId,
  hasAdminSectionAccess,
  navItems,
  systemRoles,
  translate,
}: Pick<
  BuildSubSidebarNavigationProjectionInput,
  | 'activeAppId'
  | 'hasAdminSectionAccess'
  | 'navItems'
  | 'systemRoles'
  | 'translate'
>): NavItem[] {
  const canReadAdminSection =
    hasAdminSectionAccess ?? hasConfiguredAdminSectionAccess;
  return navItems
    .filter((item) => item.appId === activeAppId)
    .map((item) => translateNavItem(item, translate))
    .filter((item) => {
      const section = resolveSettingsSectionId(item);
      return section ? canReadAdminSection(systemRoles, section) : false;
    });
}

function resolveSettingsSectionId(item: NavItem): string | null {
  const pathSection = item.absolutePath?.match(/^\/admin\/([^/?#]+)/)?.[1];
  const section =
    pathSection ?? (item.id.startsWith('settings-') ? item.id.slice(9) : null);
  if (!section) {
    return null;
  }
  return ADMIN_SECTION_ALIASES[section] ?? section;
}

export function buildSubSidebarNavigationProjection({
  activeAppId,
  canReadApp,
  extendCategories,
  globalAppIds = [],
  hasAdminSectionAccess,
  navItems,
  systemRoles,
  translate,
  appNavItems,
}: BuildSubSidebarNavigationProjectionInput): SubSidebarNavigationProjection {
  const filteredItems =
    activeAppId === 'settings'
      ? buildSettingsNavItems({
          activeAppId,
          hasAdminSectionAccess,
          navItems,
          systemRoles,
          translate,
        })
      : globalAppIds.includes(activeAppId)
        ? navItems
            .filter((item) => item.appId === activeAppId)
            .map((item) => translateNavItem(item, translate))
        : buildAppNavItems({
            activeAppId,
            navItems,
            translate,
            appNavItems,
          });
  const baseCategories = buildSidebarCategories(
    filteredItems.map((item) => item.category),
  );
  const categories =
    extendCategories?.(baseCategories, {
      canReadApp,
    }) ?? baseCategories;
  return { categories, filteredItems };
}
