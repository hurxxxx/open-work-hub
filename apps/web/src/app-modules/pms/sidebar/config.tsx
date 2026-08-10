import { Link } from 'react-router-dom';

import type {
  AppSidebarConfig,
  AppSidebarRenderContext,
} from '@/src/app/shell/sidebar-types';
import { cn } from '@/src/lib/utils';
import { projectPersonalSidebarItems } from './pms-sidebar-config-model';
import { PmsSidebarSpaces } from './PmsSidebarSpaces';

function renderPersonalCategory({
  activeNavItemId,
  currentWorkspaceSlug,
  filteredItems,
  user,
}: AppSidebarRenderContext) {
  const personalItems = projectPersonalSidebarItems({
    activeNavItemId,
    currentWorkspaceSlug,
    filteredItems,
    user,
  });

  return (
    <>
      {personalItems.map((item) => {
        const Icon = item.item.icon;

        if (item.kind === 'taskGroup') {
          return (
            <div key={item.item.id} className="space-y-1">
              <div
                className={cn(
                  'sidebar-submenu-group ml-1 cursor-default',
                  item.isActive && 'sidebar-submenu-item-active',
                )}
              >
                <Icon
                  size={16}
                  className={cn(
                    'text-app-ink/55 dark:text-app-ink/65',
                    item.isActive && 'text-app-accent',
                  )}
                />
                <span className="sidebar-submenu-label">{item.item.title}</span>
              </div>
              <div className="ml-6 space-y-1 border-l border-app-border pl-2">
                {item.children.map((child) => {
                  const ChildIcon = child.item.icon;

                  return (
                    <Link
                      key={child.item.id}
                      to={child.href}
                      className={cn(
                        'sidebar-submenu-item',
                        child.isActive && 'sidebar-submenu-item-active',
                      )}
                    >
                      <ChildIcon
                        size={14}
                        className="text-app-ink/55 dark:text-app-ink/65"
                      />
                      <span className="sidebar-submenu-label">
                        {child.item.title}
                      </span>
                    </Link>
                  );
                })}
              </div>
            </div>
          );
        }

        return (
          <Link
            key={item.item.id}
            to={item.href}
            className={cn(
              'sidebar-submenu-item ml-1',
              item.isActive && 'sidebar-submenu-item-active',
              item.isComingSoon && 'opacity-60',
            )}
          >
            <Icon size={16} className="text-app-ink/55 dark:text-app-ink/65" />
            <span className="sidebar-submenu-label">{item.item.title}</span>
          </Link>
        );
      })}
    </>
  );
}

export const pmsSidebarConfig: AppSidebarConfig = {
  extendCategories: (categories, { canReadWorkspace }) => {
    if (!canReadWorkspace) {
      return categories;
    }

    return [
      'Spaces',
      ...categories.filter((category) => category !== 'Spaces'),
    ];
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
