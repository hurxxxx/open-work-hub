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
} from 'lucide-react';

import type { NavItem } from '@/src/app/shell/navigation-types';
import type { WorkspaceBootstrapNavItem } from '@/src/platform/workspaces/workspaces-api';

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
    id: 'settings-apps-platform',
    title: 'settings-apps-platform',
    icon: AppWindow,
    category: 'Platform',
    appId: 'settings',
    absolutePath: '/admin/apps/platform',
  },
  {
    id: 'settings-apps-workspace',
    title: 'settings-apps-workspace',
    icon: Database,
    category: 'Platform',
    appId: 'settings',
    absolutePath: '/admin/apps/workspace',
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
    id: 'settings-workspaces',
    title: 'settings-workspaces',
    icon: Database,
    category: 'Workspaces',
    appId: 'settings',
    absolutePath: '/admin/workspaces',
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
    appId: 'business',
    linkAppId: 'docs',
    pathSuffix: '/default',
  },
  {
    id: 'docs-assistant',
    title: 'Document assistant',
    icon: Search,
    category: 'Documents',
    appId: 'business',
    linkAppId: 'docs',
  },
];

describe('sub-sidebar navigation model', () => {
  it('projects workspace bootstrap nav items for the active app only', () => {
    const projection = buildSubSidebarNavigationProjection({
      activeAppId: 'chatbot',
      canReadWorkspace: true,
      navItems,
      systemRoles: [],
      translate: t,
      workspaceNavItems: [
        workspaceNavItem({
          id: 'search',
          app_id: 'chatbot',
          title: 'Search from bootstrap',
          category: 'Tools',
          path_suffix: '?q=1',
          absolute_path: '/tool/search',
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
      absolutePath: '/tool/search',
      linkAppId: 'docs',
      comingSoon: true,
    });
  });

  it('fails fast when bootstrap nav is absent from the web registry', () => {
    expect(() =>
      buildSubSidebarNavigationProjection({
        activeAppId: 'chatbot',
        canReadWorkspace: true,
        navItems,
        systemRoles: [],
        translate: t,
        workspaceNavItems: [
          workspaceNavItem({ id: 'missing', app_id: 'chatbot' }),
        ],
      }),
    ).toThrow(
      'Workspace nav item missing for chatbot is missing from the web app registry',
    );
  });

  it('preserves local nav defaults when bootstrap override fields are absent', () => {
    const projection = buildSubSidebarNavigationProjection({
      activeAppId: 'chatbot',
      canReadWorkspace: true,
      navItems,
      systemRoles: [],
      translate: t,
      workspaceNavItems: [
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
      canReadWorkspace: true,
      navItems,
      systemRoles: [],
      translate: t,
      workspaceNavItems: [
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
        canReadWorkspace: true,
        navItems,
        systemRoles: [],
        translate: t,
        workspaceNavItems: [],
      }).filteredItems,
    ).toEqual([]);
  });

  it('projects leaf app nav items and ignores aggregate owner ids', () => {
    const projection = buildSubSidebarNavigationProjection({
      activeAppId: 'business',
      activeFeatureAppId: 'docs',
      canReadWorkspace: true,
      navItems,
      systemRoles: [],
      translate: t,
      workspaceNavItems: [
        workspaceNavItem({
          id: 'docs-library',
          app_id: 'docs',
          title: 'Document library from bootstrap',
          category: 'docs',
          path_suffix: '/library',
        }),
        workspaceNavItem({
          id: 'docs-assistant',
          app_id: 'business',
          title: 'Aggregate owner item',
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
      appId: 'business',
      linkAppId: 'docs',
      title: 'Document library from bootstrap',
      category: 'docs',
      pathSuffix: '/library',
    });
  });

  it('does not let bootstrap false clear local coming-soon state', () => {
    const projection = buildSubSidebarNavigationProjection({
      activeAppId: 'chatbot',
      canReadWorkspace: true,
      navItems,
      systemRoles: [],
      translate: t,
      workspaceNavItems: [
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
      canReadWorkspace: false,
      navItems,
      systemRoles: ['platform_admin'],
      translate: t,
      workspaceNavItems: [
        workspaceNavItem({ id: 'search', app_id: 'settings' }),
      ],
    });

    expect(projection.filteredItems.map((item) => item.id)).toEqual([
      'settings-general',
      'settings-apps-platform',
      'settings-apps-workspace',
      'settings-apps-app-bar',
      'settings-llm',
      'settings-model-monitoring',
      'settings-document-processing',
      'settings-ai-security',
      'settings-workspaces',
      'settings-community',
      'settings-usage',
      'settings-audit',
    ]);
    expect(projection.categories).toEqual([
      'Platform',
      'AIPlatform',
      'Operations',
      'SecurityAudit',
      'Workspaces',
    ]);
    expect(
      buildSubSidebarNavigationProjection({
        activeAppId: 'settings',
        canReadWorkspace: false,
        navItems,
        systemRoles: [],
        translate: t,
        workspaceNavItems: [],
      }).filteredItems,
    ).toEqual([]);
  });

  it('uses injected settings section access for standalone app policies', () => {
    const projection = buildSubSidebarNavigationProjection({
      activeAppId: 'settings',
      canReadWorkspace: false,
      hasAdminSectionAccess: (_systemRoles, section) =>
        ['apps', 'workspaces', 'usage', 'audit'].includes(section),
      navItems,
      systemRoles: ['platform_admin'],
      translate: t,
      workspaceNavItems: [],
    });

    expect(projection.filteredItems.map((item) => item.id)).toEqual([
      'settings-apps-platform',
      'settings-apps-workspace',
      'settings-apps-app-bar',
      'settings-workspaces',
      'settings-usage',
      'settings-audit',
    ]);
    expect(projection.categories).toEqual([
      'Platform',
      'Workspaces',
      'Operations',
      'SecurityAudit',
    ]);
  });

  it('uses manifest navigation for global apps without workspace bootstrap nav', () => {
    const projection = buildSubSidebarNavigationProjection({
      activeAppId: 'chatbot',
      canReadWorkspace: false,
      globalAppIds: ['chatbot'],
      navItems,
      systemRoles: [],
      translate: t,
      workspaceNavItems: [],
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
      canReadWorkspace: false,
      extendCategories: (categories, context) => [
        ...categories,
        context.canReadWorkspace ? 'Teams' : 'Locked',
      ],
      navItems: localNavItems,
      systemRoles: [],
      translate: t,
      workspaceNavItems: [
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
  overrides: Partial<WorkspaceBootstrapNavItem> = {},
): WorkspaceBootstrapNavItem {
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
