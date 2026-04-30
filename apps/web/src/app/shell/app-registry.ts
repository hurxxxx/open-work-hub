import { aiManifest } from '@/src/app-modules/ai';
import { docsManifest } from '@/src/app-modules/docs';
import { homeManifest } from '@/src/app-modules/home';
import { learningManifest } from '@/src/app-modules/learning';
import { meetingManifest } from '@/src/app-modules/meeting';
import { plannerManifest } from '@/src/app-modules/planner';
import { pmsManifest } from '@/src/app-modules/pms';
import { settingsManifest } from '@/src/app-modules/settings';
import type {
  AppBarItem,
  AppModuleId,
  AppModuleManifest,
  NavItem,
} from './navigation-types';

const DEFAULT_MANIFESTS: AppModuleManifest[] = [
  homeManifest,
  aiManifest,
  pmsManifest,
  docsManifest,
  plannerManifest,
  meetingManifest,
  learningManifest,
  settingsManifest,
];

export function createAppModuleRegistry(manifests: AppModuleManifest[]) {
  const manifestByAppId = new Map<AppModuleId, AppModuleManifest>();
  const navItemById = new Map<string, NavItem>();

  for (const manifest of manifests) {
    const appId = manifest.appBarItem.id;
    if (manifestByAppId.has(appId)) {
      throw new Error(`Duplicate app module id: ${appId}`);
    }
    manifestByAppId.set(appId, manifest);

    for (const navItem of manifest.navItems) {
      if (navItemById.has(navItem.id)) {
        throw new Error(`Duplicate nav item id: ${navItem.id}`);
      }
      navItemById.set(navItem.id, navItem);
    }
  }

  const appBarItems = manifests.map((manifest) => manifest.appBarItem);
  const navItems = manifests.flatMap((manifest) => manifest.navItems);

  return {
    appBarItems,
    manifestByAppId,
    manifests,
    navItemById,
    navItems,
  };
}

export const APP_MODULE_REGISTRY = createAppModuleRegistry(DEFAULT_MANIFESTS);

export const APP_MODULE_MANIFESTS: readonly AppModuleManifest[] = APP_MODULE_REGISTRY.manifests;
export const APP_BAR_ITEMS: readonly AppBarItem[] = APP_MODULE_REGISTRY.appBarItems;
export const NAV_ITEMS: readonly NavItem[] = APP_MODULE_REGISTRY.navItems;

export function getAppModuleManifest(appId: AppModuleId): AppModuleManifest | null {
  return APP_MODULE_REGISTRY.manifestByAppId.get(appId) ?? null;
}

export function getNavItem(itemId: string): NavItem | null {
  return APP_MODULE_REGISTRY.navItemById.get(itemId) ?? null;
}
