import { Bot, FileUp, Folder } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { buildAppHref } from '@open-work-hub/contracts/app-routes';

import type { AppSidebarConfig } from '@/src/app/shell/sidebar-types';
import { cn } from '@/src/lib/utils';
import { FilesSidebarFolders } from './sidebar-folders';

export const filesSidebarConfig: AppSidebarConfig = {
  createActions: () => [
    {
      id: 'files-upload',
      label: 'files-upload',
      labelKey: 'sidebarActions.files-upload',
      icon: FileUp,
      run: () => {
        window.dispatchEvent(new CustomEvent('files:upload'));
      },
    },
    {
      id: 'files-create-folder',
      label: 'files-create-folder',
      labelKey: 'sidebarActions.files-create-folder',
      icon: Folder,
      run: () => {
        window.dispatchEvent(new CustomEvent('files:create-folder'));
      },
    },
  ],
  afterCategories: ({ currentWorkspaceSlug, filteredItems, onNavigate }) => (
    <div>
      <FilesChatSidebarLink
        currentWorkspaceSlug={currentWorkspaceSlug}
        hasBootstrapItem={filteredItems.some(
          (item) => item.id === 'files-chat',
        )}
        onNavigate={onNavigate}
      />
      <FilesSidebarFolders currentWorkspaceSlug={currentWorkspaceSlug} />
    </div>
  ),
};

export function FilesChatSidebarLink({
  currentWorkspaceSlug,
  hasBootstrapItem,
  onNavigate,
}: {
  currentWorkspaceSlug: string | null;
  hasBootstrapItem: boolean;
  onNavigate?: () => void;
}) {
  const { t } = useTranslation('shell');
  const location = useLocation();
  if (!currentWorkspaceSlug || hasBootstrapItem) {
    return null;
  }
  const chatPath = buildAppHref({
    routeId: 'files.chat',
    workspaceSlug: currentWorkspaceSlug,
  });
  return (
    <Link
      to={chatPath}
      onClick={onNavigate}
      className={cn(
        'sidebar-submenu-item ml-1',
        location.pathname === chatPath && 'sidebar-submenu-item-active',
      )}
    >
      <Bot aria-hidden="true" size={14} className="text-app-ink/55" />
      <span className="sidebar-submenu-label truncate">
        {t('nav.files-chat')}
      </span>
    </Link>
  );
}
