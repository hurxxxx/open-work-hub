import { describe, expect, it } from 'vitest';
import {
  Activity,
  AppWindow,
  BarChart3,
  BrainCircuit,
  Database,
  FileSearch,
  Home,
  MessagesSquare,
  Search,
  Server,
  Settings,
  ShieldCheck,
  User,
} from 'lucide-react';

import type { NavItem } from '@/src/app/shell/navigation-types';
import type { BootstrapNavItem } from '@/src/platform/apps/apps-api';

import { buildSubSidebarNavigationProjection } from './sub-sidebar-navigation-model';

function t(key: string, options?: Record<string, unknown>): string {
  if (key === 'nav.search') return 'Translated search';
  if (key === 'categories.Tools') return 'Translated tools';
  return String(options?.defaultValue ?? key);
}

const navItems: NavItem[] = [
  {
    id: 'home',
    title: 'Home',
    icon: Home,
    category: 'Core',
    appId: 'home',
  },
  {
    id: 'search',
    title: 'Search',
    icon: Search,
    category: 'Tools',
    appId: 'chatbot',
    pathSuffix: '?default=true',
  },
  {
    id: 'settings-general',
    title: 'settings-general',
    icon: Settings,
    category: 'Platform',
    appId: 'settings',
    absolutePath: '/admin/general',
  },
  {
    id: 'settings-people',
    title: 'settings-people',
    icon: User,
    category: 'Organization',
    appId: 'settings',
    absolutePath: '/admin/people',
  },
  {
    id: 'settings-apps-access',
    title: 'settings-apps-access',
    icon: AppWindow,
    category: 'Platform',
    appId: 'settings',
    absolutePath: '/admin/apps/access',
  },
  {
    id: 'settings-apps-app-bar',
    title: 'settings-apps-app-bar',
    icon: Settings,
    category: 'Platform',
    appId: 'settings',
    absolutePath: '/admin/apps/app-bar',
  },
  {
    id: 'settings-llm',
    title: 'settings-llm',
    icon: BrainCircuit,
    category: 'AIPlatform',
    appId: 'settings',
    absolutePath: '/admin/llm',
  },
  {
    id: 'settings-model-monitoring',
    title: 'settings-model-monitoring',
    icon: Server,
    category: 'Operations',
    appId: 'settings',
    absolutePath: '/admin/model-monitoring',
  },
  {
    id: 'settings-document-processing',
    title: 'settings-document-processing',
    icon: FileSearch,
    category: 'AIPlatform',
    appId: 'settings',
    absolutePath: '/admin/document-processing',
  },
  {
    id: 'settings-ai-security',
    title: 'settings-ai-security',
    icon: ShieldCheck,
    category: 'SecurityAudit',
    appId: 'settings',
    absolutePath: '/admin/ai-security',
  },
  {
    id: 'settings-groups',
    title: 'settings-groups',
    icon: Database,
    category: 'Organization',
    appId: 'settings',
    absolutePath: '/admin/groups',
  },
  {
    id: 'settings-community',
    title: 'settings-community',
    icon: MessagesSquare,
    category: 'Platform',
    appId: 'settings',
    absolutePath: '/admin/community',
  },
  {
    id: 'settings-usage',
    title: 'settings-usage',
    icon: BarChart3,
    category: 'Operations',
    appId: 'settings',
    absolutePath: '/admin/usage',
  },
  {
    id: 'settings-audit',
    title: 'settings-audit',
    icon: Activity,
    category: 'SecurityAudit',
    appId: 'settings',
    absolutePath: '/admin/audit',
  },
  {
    id: 'chatbot',
    title: 'Chatbot',
    icon: Search,
    category: 'Tools',
    appId: 'chatbot',
    comingSoon: true,
  },
  {
    id: 'docs-library',
    title: 'Document library',
    icon: Database,
    category: 'Documents',
    appId: 'docs',
    pathSuffix: '/default',
  },
  {
    id: 'docs-assistant',
    title: 'Document assistant',
    icon: Search,
    category: 'Documents',
    appId: 'docs',
  },
];

describe('sub-sidebar navigation model', () => {
  it('projects workspace bootstrap nav items for the active app only', () => {
    const projection = buildSubSidebarNavigationProjection({
      activeAppId: 'chatbot',
      canReadApp: true,
      navItems,
      systemRoles: [],
      translate: t,
      appNavItems: [
        workspaceNavItem({
          id: 'search',
          app_id: 'chatbot',
          title: 'Search from bootstrap',
          category: 'Tools',
          path_suffix: '?q=1',
          absolute_path: '/apps/retrieval-search',
          link_app_id: 'docs',
          coming_soon: true,
        }),
        workspaceNavItem({ id: 'home', app_id: 'home' }),
      ],
    });

    expect(projection.categories).toEqual(['Translated tools']);
    expect(projection.filteredItems).toHaveLength(1);
    expect(projection.filteredItems[0]).toMatchObject({
      id: 'search',
      appId: 'chatbot',
      title: 'Translated search',
      category: 'Translated tools',
      pathSuffix: '?q=1',
      absolutePath: '/apps/retrieval-search',
      linkAppId: 'docs',
      comingSoon: true,
    });
  });

  it('fails fast when bootstrap nav is absent from the web registry', () => {
    expect(() =>
      buildSubSidebarNavigationProjection({
        activeAppId: 'chatbot',
        canReadApp: true,
        navItems,
        systemRoles: [],
        translate: t,
        appNavItems: [workspaceNavItem({ id: 'missing', app_id: 'chatbot' })],
      }),
    ).toThrow(
      'App nav item missing for chatbot is missing from the web app registry',
    );
  });

  it('preserves local nav defaults when bootstrap override fields are absent', () => {
    const projection = buildSubSidebarNavigationProjection({
      activeAppId: 'chatbot',
      canReadApp: true,
      navItems,
      systemRoles: [],
      translate: t,
      appNavItems: [
        workspaceNavItem({
          id: 'search',
          app_id: 'chatbot',
          path_suffix: null,
        }),
      ],
    });

    expect(projection.filteredItems[0].pathSuffix).toBe('?default=true');
    expect(projection.filteredItems[0].absolutePath).toBeUndefined();
    expect(projection.filteredItems[0].comingSoon).toBeUndefined();
  });

  it('uses bootstrap order and hides local-only workspace nav items', () => {
    const projection = buildSubSidebarNavigationProjection({
      activeAppId: 'chatbot',
      canReadApp: true,
      navItems,
      systemRoles: [],
      translate: t,
      appNavItems: [
        workspaceNavItem({ id: 'chatbot', app_id: 'chatbot' }),
        workspaceNavItem({ id: 'search', app_id: 'chatbot' }),
      ],
    });

    expect(projection.filteredItems.map((item) => item.id)).toEqual([
      'chatbot',
      'search',
    ]);
    expect(
      buildSubSidebarNavigationProjection({
        activeAppId: 'chatbot',
        canReadApp: true,
        navItems,
        systemRoles: [],
        translate: t,
        appNavItems: [],
      }).filteredItems,
    ).toEqual([]);
  });

  it('projects only nav items owned by the active leaf app', () => {
    const projection = buildSubSidebarNavigationProjection({
      activeAppId: 'docs',
      canReadApp: true,
      navItems,
      systemRoles: [],
      translate: t,
      appNavItems: [
        workspaceNavItem({
          id: 'docs-library',
          app_id: 'docs',
          title: 'Document library from bootstrap',
          category: 'docs',
          path_suffix: '/library',
        }),
        workspaceNavItem({
          id: 'docs-assistant',
          app_id: 'chatbot',
          title: 'Other app item',
          category: 'docs',
        }),
        workspaceNavItem({
          id: 'search',
          app_id: 'chatbot',
        }),
      ],
    });

    expect(projection.filteredItems).toHaveLength(1);
    expect(projection.filteredItems[0]).toMatchObject({
      id: 'docs-library',
      appId: 'docs',
      title: 'Document library from bootstrap',
      category: 'docs',
      pathSuffix: '/library',
    });
  });

  it('does not let bootstrap false clear local coming-soon state', () => {
    const projection = buildSubSidebarNavigationProjection({
      activeAppId: 'chatbot',
      canReadApp: true,
      navItems,
      systemRoles: [],
      translate: t,
      appNavItems: [
        workspaceNavItem({
          id: 'chatbot',
          app_id: 'chatbot',
          coming_soon: false,
        }),
      ],
    });

    expect(projection.filteredItems[0].comingSoon).toBe(true);
  });

  it('uses static settings nav items filtered by admin section access', () => {
    const projection = buildSubSidebarNavigationProjection({
      activeAppId: 'settings',
      canReadApp: false,
      navItems,
      systemRoles: ['platform_admin'],
      translate: t,
      appNavItems: [workspaceNavItem({ id: 'search', app_id: 'settings' })],
    });

    expect(projection.filteredItems.map((item) => item.id)).toEqual([
      'settings-general',
      'settings-people',
      'settings-apps-access',
      'settings-apps-app-bar',
      'settings-llm',
      'settings-model-monitoring',
      'settings-document-processing',
      'settings-ai-security',
      'settings-groups',
      'settings-community',
      'settings-usage',
      'settings-audit',
    ]);
    expect(projection.categories).toEqual([
      'Platform',
      'Organization',
      'AIPlatform',
      'Operations',
      'SecurityAudit',
    ]);
    expect(
      buildSubSidebarNavigationProjection({
        activeAppId: 'settings',
        canReadApp: false,
        navItems,
        systemRoles: [],
        translate: t,
        appNavItems: [],
      }).filteredItems,
    ).toEqual([]);
  });

  it('uses injected settings section access for standalone app policies', () => {
    const projection = buildSubSidebarNavigationProjection({
      activeAppId: 'settings',
      canReadApp: false,
      hasAdminSectionAccess: (_systemRoles, section) =>
        ['apps', 'groups', 'usage', 'audit'].includes(section),
      navItems,
      systemRoles: ['platform_admin'],
      translate: t,
      appNavItems: [],
    });

    expect(projection.filteredItems.map((item) => item.id)).toEqual([
      'settings-apps-access',
      'settings-apps-app-bar',
      'settings-groups',
      'settings-usage',
      'settings-audit',
    ]);
    expect(projection.categories).toEqual([
      'Platform',
      'Organization',
      'Operations',
      'SecurityAudit',
    ]);
  });

  it('uses manifest navigation for global apps without workspace bootstrap nav', () => {
    const projection = buildSubSidebarNavigationProjection({
      activeAppId: 'chatbot',
      canReadApp: false,
      globalAppIds: ['chatbot'],
      navItems,
      systemRoles: [],
      translate: t,
      appNavItems: [],
    });

    expect(projection.filteredItems.map((item) => item.id)).toEqual([
      'search',
      'chatbot',
    ]);
    expect(projection.filteredItems[0]?.title).toBe('Translated search');
    expect(projection.categories).toEqual(['Translated tools']);
  });

  it('extends unique categories with workspace read context without mutating inputs', () => {
    const localNavItems = navItems.map((item) => ({ ...item }));
    const projection = buildSubSidebarNavigationProjection({
      activeAppId: 'chatbot',
      canReadApp: false,
      extendCategories: (categories, context) => [
        ...categories,
        context.canReadApp ? 'Teams' : 'Locked',
      ],
      navItems: localNavItems,
      systemRoles: [],
      translate: t,
      appNavItems: [
        workspaceNavItem({
          id: 'search',
          app_id: 'chatbot',
          category: 'Tools',
        }),
        workspaceNavItem({
          id: 'search',
          app_id: 'chatbot',
          category: 'Tools',
        }),
      ],
    });

    expect(projection.categories).toEqual(['Translated tools', 'Locked']);
    expect(localNavItems).toEqual(navItems);
  });
});

function workspaceNavItem(
  overrides: Partial<BootstrapNavItem> = {},
): BootstrapNavItem {
  return {
    id: 'search',
    app_id: 'chatbot',
    title: 'Search',
    category: 'Tools',
    icon_key: 'search',
    link_app_id: null,
    path_suffix: undefined,
    absolute_path: undefined,
    coming_soon: false,
    ...overrides,
  };
}
