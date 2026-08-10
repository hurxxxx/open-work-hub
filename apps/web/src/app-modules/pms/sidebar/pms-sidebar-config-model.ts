import type { NavItem } from '@/src/app/shell/navigation-types';
import type { AuthUser } from '@/src/platform/auth/auth-api';
import { resolveNavItemHref } from '@/src/platform/workspaces/workspace-utils';

const PERSONAL_CATEGORY = 'Personal';
const PMS_TASKS_ROOT_ID = 'pms-tasks';
const PMS_TASKS_CHILD_PREFIX = 'pms-tasks-';

export type ProjectedPersonalSidebarTaskGroup = {
  kind: 'taskGroup';
  item: NavItem;
  isActive: boolean;
  children: ProjectedPersonalSidebarLink[];
};

export type ProjectedPersonalSidebarLink = {
  kind: 'link';
  item: NavItem;
  href: string;
  isActive: boolean;
  isComingSoon: boolean;
};

export type ProjectedPersonalSidebarItem =
  | ProjectedPersonalSidebarTaskGroup
  | ProjectedPersonalSidebarLink;

export function projectPersonalSidebarItems({
  activeNavItemId,
  currentWorkspaceSlug,
  filteredItems,
  user,
}: {
  activeNavItemId: string;
  currentWorkspaceSlug: string | null;
  filteredItems: readonly NavItem[];
  user: AuthUser | null;
}): ProjectedPersonalSidebarItem[] {
  const personalItems = filteredItems.filter(
    (item) => item.category === PERSONAL_CATEGORY,
  );
  const taskChildren = personalItems.filter(isPmsTasksChild);
  const hasPmsTasksRoot = personalItems.some(
    (item) => item.id === PMS_TASKS_ROOT_ID,
  );
  const isPmsTasksActive =
    activeNavItemId === PMS_TASKS_ROOT_ID ||
    activeNavItemId.startsWith(PMS_TASKS_CHILD_PREFIX);

  return personalItems.flatMap((item): ProjectedPersonalSidebarItem[] => {
    if (item.id === PMS_TASKS_ROOT_ID) {
      return [
        {
          kind: 'taskGroup',
          item,
          isActive: isPmsTasksActive,
          children: taskChildren.map((child) =>
            projectPmsTasksChild({
              activeNavItemId,
              currentWorkspaceSlug,
              item: child,
              user,
            }),
          ),
        },
      ];
    }

    if (hasPmsTasksRoot && isPmsTasksChild(item)) {
      return [];
    }

    return [
      {
        kind: 'link',
        item,
        href: resolveNavItemHref(item, currentWorkspaceSlug, user),
        isActive: activeNavItemId === item.id,
        isComingSoon: Boolean(item.comingSoon),
      },
    ];
  });
}

function isPmsTasksChild(item: NavItem): boolean {
  return item.id.startsWith(PMS_TASKS_CHILD_PREFIX);
}

function projectPmsTasksChild({
  activeNavItemId,
  currentWorkspaceSlug,
  item,
  user,
}: {
  activeNavItemId: string;
  currentWorkspaceSlug: string | null;
  item: NavItem;
  user: AuthUser | null;
}): ProjectedPersonalSidebarLink {
  return {
    kind: 'link',
    item,
    href: resolveNavItemHref(item, currentWorkspaceSlug, user),
    isActive: activeNavItemId === item.id,
    isComingSoon: Boolean(item.comingSoon),
  };
}
