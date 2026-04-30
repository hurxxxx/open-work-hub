import { Link } from 'react-router-dom';
import { CheckSquare, Layout } from 'lucide-react';

import type {
  AppSidebarConfig,
  AppSidebarRenderContext,
} from '@/src/app/shell/sidebar-types';
import { resolveNavItemHref } from '@/src/platform/workspaces/workspace-utils';
import { cn } from '@/src/lib/utils';
import { PmsSidebarSpaces } from './PmsSidebarSpaces';

function renderPersonalCategory({
  activeNavItemId,
  currentWorkspaceSlug,
  filteredItems,
  user,
}: AppSidebarRenderContext) {
  const personalItems = filteredItems.filter((item) => item.category === 'Personal');

  return (
    <>
      {personalItems.map((item) => {
        if (item.id === 'pms-tasks') {
          const subTasks = personalItems.filter((entry) =>
            entry.id.startsWith('pms-tasks-'),
          );
          const isMyTasksActive =
            activeNavItemId === 'pms-tasks' ||
            activeNavItemId.startsWith('pms-tasks-');
          return (
            <div key={item.id} className="space-y-1">
              <div
                className={cn(
                  'sidebar-submenu-group ml-1 cursor-default',
                  isMyTasksActive && 'sidebar-submenu-item-active',
                )}
              >
                <item.icon
                  size={16}
                  className={cn(
                    'text-gray-500 dark:text-gray-400',
                    isMyTasksActive && 'text-app-accent',
                  )}
                />
                <span className="sidebar-submenu-label">{item.title}</span>
              </div>
              <div className="ml-6 space-y-1 border-l border-app-border pl-2">
                {subTasks.map((sub) => (
                  <Link
                    key={sub.id}
                    to={`/tool/${sub.id}`}
                    className={cn(
                      'sidebar-submenu-item',
                      activeNavItemId === sub.id &&
                        'sidebar-submenu-item-active',
                    )}
                  >
                    <sub.icon
                      size={14}
                      className="text-gray-500 dark:text-gray-400"
                    />
                    <span className="sidebar-submenu-label">{sub.title}</span>
                  </Link>
                ))}
              </div>
            </div>
          );
        }

        if (item.id.startsWith('pms-tasks-')) {
          return null;
        }

        return (
          <Link
            key={item.id}
            to={resolveNavItemHref(item, currentWorkspaceSlug, user)}
            className={cn(
              'sidebar-submenu-item ml-1',
              activeNavItemId === item.id && 'sidebar-submenu-item-active',
              item.comingSoon && 'opacity-60',
            )}
          >
            <item.icon size={16} className="text-gray-500 dark:text-gray-400" />
            <span className="sidebar-submenu-label">{item.title}</span>
          </Link>
        );
      })}
    </>
  );
}

export const pmsSidebarConfig: AppSidebarConfig = {
  createActions: () => [
    {
      id: 'pms-create-task',
      label: 'Task',
      icon: CheckSquare,
      run: () => {
        window.dispatchEvent(new CustomEvent('pms:create-task'));
      },
    },
    {
      id: 'pms-create-space',
      label: 'Space',
      icon: Layout,
      run: () => {
        window.dispatchEvent(new CustomEvent('pms:create-space'));
      },
    },
  ],
  extendCategories: (categories, { canReadWorkspace }) => {
    if (!canReadWorkspace) {
      return categories;
    }

    return ['Spaces', ...categories.filter((category) => category !== 'Spaces')];
  },
  renderCategory: (category, context) => {
    if (category === 'Spaces') {
      return (
        <PmsSidebarSpaces
          activeNavItemId={context.activeNavItemId}
          currentWorkspaceSlug={context.currentWorkspaceSlug}
          isExpanded={context.isCategoryExpanded('Spaces')}
          onToggle={() => context.toggleCategory('Spaces')}
        />
      );
    }

    if (category === 'Personal') {
      return renderPersonalCategory(context);
    }

    return undefined;
  },
};
