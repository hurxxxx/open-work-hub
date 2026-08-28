import { Calendar, CheckCircle2, Inbox, Layout, User } from 'lucide-react';
import { describe, expect, it } from 'vitest';

import type { NavItem } from '@/src/app/shell/navigation-types';
import { projectPersonalSidebarItems } from './pms-sidebar-config-model';

function item(overrides: Partial<NavItem>): NavItem {
  return {
    id: 'pms-inbox',
    title: 'Inbox',
    icon: Inbox,
    category: 'Personal',
    appId: 'pms',
    ...overrides,
  };
}

describe('PMS sidebar personal projection', () => {
  it('projects the pms-tasks root as one active task group with child tool links', () => {
    const projected = projectPersonalSidebarItems({
      activeNavItemId: 'pms-tasks-today',
      currentWorkspaceSlug: 'hq',
      filteredItems: [
        item({
          id: 'pms-inbox',
          title: 'Inbox',
          icon: Inbox,
        }),
        item({
          id: 'pms-tasks-assigned',
          title: 'Assigned',
          icon: User,
          pathSuffix: '/assigned',
        }),
        item({
          id: 'pms-tasks',
          title: 'My Tasks',
          icon: CheckCircle2,
          pathSuffix: '/assigned',
        }),
        item({
          id: 'pms-tasks-today',
          title: 'Today',
          icon: Calendar,
          pathSuffix: '/today',
        }),
      ],
      user: null,
    });

    expect(projected.map((entry) => [entry.kind, entry.item.id])).toEqual([
      ['link', 'pms-inbox'],
      ['taskGroup', 'pms-tasks'],
    ]);
    expect(projected[1]).toMatchObject({
      kind: 'taskGroup',
      isActive: true,
      children: [
        {
          kind: 'link',
          href: '/apps/pms/workspaces/hq/assigned',
          isActive: false,
          item: { id: 'pms-tasks-assigned' },
        },
        {
          kind: 'link',
          href: '/apps/pms/workspaces/hq/today',
          isActive: true,
          item: { id: 'pms-tasks-today' },
        },
      ],
    });
  });

  it('projects declared personal links with workspace href and exact active state', () => {
    const projected = projectPersonalSidebarItems({
      activeNavItemId: 'pms-inbox',
      currentWorkspaceSlug: 'hq',
      filteredItems: [
        item({
          id: 'pms-inbox',
          title: 'Inbox',
          icon: Layout,
        }),
        item({
          id: 'pms-later',
          title: 'Later',
          icon: Inbox,
          comingSoon: true,
        }),
        item({
          id: 'docs-my',
          title: 'Docs',
          icon: Inbox,
          category: 'Docs',
          appId: 'docs',
        }),
      ],
      user: null,
    });

    expect(projected).toMatchObject([
      {
        kind: 'link',
        href: '/apps/pms/workspaces/hq',
        isActive: true,
        isComingSoon: false,
        item: { id: 'pms-inbox' },
      },
      {
        kind: 'link',
        href: '/apps/pms/workspaces/hq',
        isActive: false,
        isComingSoon: true,
        item: { id: 'pms-later' },
      },
    ]);
  });

  it('projects task child links directly when the pms-tasks root is not present', () => {
    const projected = projectPersonalSidebarItems({
      activeNavItemId: 'pms-tasks-assigned',
      currentWorkspaceSlug: 'hq',
      filteredItems: [
        item({
          id: 'pms-tasks-assigned',
          title: 'Assigned',
          icon: User,
          pathSuffix: '/assigned',
        }),
      ],
      user: null,
    });

    expect(projected).toMatchObject([
      {
        kind: 'link',
        href: '/apps/pms/workspaces/hq/assigned',
        isActive: true,
        item: { id: 'pms-tasks-assigned' },
      },
    ]);
  });
});
