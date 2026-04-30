import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { FileText } from 'lucide-react';

import type { AppSidebarConfig } from '@/src/app/shell/sidebar-types';
import { useAuth } from '@/src/domains/auth/auth-provider';
import {
  listFavoriteDocs,
  listRecentPages,
  type FavoriteDocItem,
  type RecentPageItem,
} from '@/src/domains/docs/docs-api';
import {
  buildWorkspaceAppPath,
  resolveDefaultWorkspaceAppPath,
} from '@/src/domains/workspaces/workspace-utils';
import { cn } from '@/src/lib/utils';

interface DocsSidebarExtrasProps {
  currentWorkspaceSlug: string | null;
}

export function DocsSidebarExtras({ currentWorkspaceSlug }: DocsSidebarExtrasProps) {
  const { token, user } = useAuth();
  const location = useLocation();
  const [favorites, setFavorites] = useState<FavoriteDocItem[]>([]);
  const [recentPages, setRecentPages] = useState<RecentPageItem[]>([]);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    listFavoriteDocs(token)
      .then((items) => {
        if (!cancelled) setFavorites(items);
      })
      .catch(() => {
        if (!cancelled) setFavorites([]);
      });
    listRecentPages(token, 5)
      .then((items) => {
        if (!cancelled) setRecentPages(items);
      })
      .catch(() => {
        if (!cancelled) setRecentPages([]);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  return (
    <>
      <div className="space-y-1 pt-2 border-t border-app-border mt-2">
        <span className="sidebar-section-label block px-3 py-1 text-gray-500">Favorites</span>
        {favorites.length > 0 ? (
          favorites.map((favorite) => {
            const docPath = currentWorkspaceSlug
              ? buildWorkspaceAppPath(currentWorkspaceSlug, 'docs', `/${favorite.id}`)
              : resolveDefaultWorkspaceAppPath(user, 'docs', `/${favorite.id}`);
            return (
              <Link
                key={favorite.id}
                to={docPath}
                className={cn(
                  'sidebar-submenu-item ml-1',
                  location.pathname === docPath && 'sidebar-submenu-item-active',
                )}
              >
                <FileText size={14} className="text-yellow-500" />
                <span className="sidebar-submenu-label truncate">{favorite.title}</span>
              </Link>
            );
          })
        ) : (
          <div className="px-3 py-2 text-center">
            <span className="app-text-micro text-gray-600">Star a Doc to see it here</span>
          </div>
        )}
      </div>

      <div className="space-y-1 pt-2 border-t border-app-border mt-2">
        <span className="sidebar-section-label block px-3 py-1 text-gray-500">Recent Pages</span>
        {recentPages.length > 0 ? (
          recentPages.map((recentPage) => {
            const docPath = currentWorkspaceSlug
              ? buildWorkspaceAppPath(currentWorkspaceSlug, 'docs', `/${recentPage.doc_id}`)
              : resolveDefaultWorkspaceAppPath(user, 'docs', `/${recentPage.doc_id}`);
            return (
              <Link
                key={recentPage.page_id}
                to={docPath}
                className="sidebar-submenu-item ml-1"
              >
                <FileText size={14} className="text-gray-500" />
                <span className="sidebar-submenu-label truncate">
                  {recentPage.page_title}
                </span>
              </Link>
            );
          })
        ) : (
          <div className="px-3 py-2 text-center">
            <span className="app-text-micro text-gray-600">No recent pages</span>
          </div>
        )}
      </div>
    </>
  );
}

export const docsSidebarConfig: AppSidebarConfig = {
  createActions: () => [
    {
      id: 'docs-create-doc',
      label: 'Doc',
      icon: FileText,
      run: () => {
        window.dispatchEvent(new CustomEvent('docs:create'));
      },
    },
  ],
  afterCategories: ({ currentWorkspaceSlug }) => (
    <DocsSidebarExtras currentWorkspaceSlug={currentWorkspaceSlug} />
  ),
};
