import { FileTree, useFileTree } from '@pierre/trees/react';
import { FolderOpen } from 'lucide-react';
import type { CSSProperties } from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useLocation, useNavigate } from 'react-router-dom';

import { cn } from '@/src/lib/utils';
import { buildAppPath } from '@/src/platform/apps/app-links';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { browseFiles, type FileFolderItem } from './api/files-api';
import { FILES_CHANGED_EVENT } from './file-upload-session';
import {
  buildFolderTreeModel,
  type FolderTreeModel,
} from './folder-tree-model';
import { FolderTreeRow } from './folder-tree-row';

const FILE_TREE_ROW_HEIGHT = 28;
const FILE_TREE_MAX_HEIGHT = 320;

type FileTreeStyle = CSSProperties & Record<`--${string}`, string | number>;

const filesSidebarTreeStyle: FileTreeStyle = {
  '--trees-accent-override': 'var(--color-app-accent)',
  '--trees-bg-muted-override': 'var(--color-app-surface-hover)',
  '--trees-bg-override': 'transparent',
  '--trees-border-color-override': 'transparent',
  '--trees-border-radius-override': '6px',
  '--trees-fg-muted-override':
    'color-mix(in srgb, var(--color-app-ink) 55%, transparent)',
  '--trees-fg-override':
    'color-mix(in srgb, var(--color-app-ink) 72%, transparent)',
  '--trees-file-icon-color':
    'color-mix(in srgb, var(--color-app-ink) 50%, transparent)',
  '--trees-focus-ring-color-override':
    'color-mix(in srgb, var(--color-app-accent) 35%, transparent)',
  '--trees-font-family-override': 'var(--font-sans)',
  '--trees-font-size-override': '12px',
  '--trees-item-margin-x-override': '4px',
  '--trees-item-padding-x-override': '8px',
  '--trees-level-gap-override': '8px',
  '--trees-padding-inline-override': '0px',
  '--trees-selected-bg-override': 'var(--color-app-surface-hover)',
  '--trees-selected-fg-override': 'var(--color-app-ink)',
};

function currentFolderFromSearch(search: string): string | null {
  return new URLSearchParams(search).get('folder');
}

export function FilesSidebarFolders(_context: Record<string, never>) {
  const { t } = useTranslation('apps');
  const { token } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [folders, setFolders] = useState<FileFolderItem[]>([]);
  const activeFolderId = currentFolderFromSearch(location.search);

  const load = useCallback(async () => {
    if (!token) {
      setFolders([]);
      return;
    }
    try {
      const response = await browseFiles(token, null);
      setFolders(response.all_folders);
    } catch {
      setFolders([]);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const handler = () => {
      void load();
    };
    window.addEventListener(FILES_CHANGED_EVENT, handler);
    return () => window.removeEventListener(FILES_CHANGED_EVENT, handler);
  }, [load]);

  const folderTreeModel = useMemo(
    () => buildFolderTreeModel(folders),
    [folders],
  );

  const rootPath = buildAppPath('files');
  const rootActive = location.pathname === rootPath && activeFolderId === null;

  return (
    <div className="space-y-1 pt-2 border-t border-app-border mt-2">
      <span className="sidebar-section-label block px-3 py-1 text-app-ink/55">
        {t('files.sidebar.folders')}
      </span>
      <Link
        to={rootPath}
        className={cn(
          'sidebar-submenu-item ml-1',
          rootActive && 'sidebar-submenu-item-active',
        )}
      >
        <FolderOpen size={14} className="text-app-ink/55" />
        <span className="sidebar-submenu-label truncate">
          {t('files.sidebar.root')}
        </span>
      </Link>
      {folderTreeModel.tree.length > 0 ? (
        folderTreeModel.supportsPathRendering ? (
          <FilesSidebarPierreTree
            activeFolderId={activeFolderId}
            model={folderTreeModel}
            navigate={navigate}
            rootPath={rootPath}
          />
        ) : (
          <div className="space-y-0.5">
            {folderTreeModel.tree.map((folder) => (
              <FolderTreeRow
                key={folder.id}
                activeFolderId={activeFolderId}
                folder={folder}
                level={0}
              />
            ))}
          </div>
        )
      ) : (
        <div className="px-3 py-2 text-center">
          <span className="app-text-micro text-app-ink/70">
            {t('files.sidebar.empty')}
          </span>
        </div>
      )}
    </div>
  );
}

function FilesSidebarPierreTree({
  activeFolderId,
  model: folderTreeModel,
  navigate,
  rootPath,
}: {
  activeFolderId: string | null;
  model: FolderTreeModel;
  navigate: (to: string) => void;
  rootPath: string;
}) {
  const activePath = activeFolderId
    ? (folderTreeModel.pathByFolderId.get(activeFolderId) ?? null)
    : null;
  const navigationRef = useRef({
    activeFolderId,
    folderIdByPath: folderTreeModel.folderIdByPath,
    navigate,
    rootPath,
  });

  navigationRef.current = {
    activeFolderId,
    folderIdByPath: folderTreeModel.folderIdByPath,
    navigate,
    rootPath,
  };

  const { model } = useFileTree({
    density: 'compact',
    icons: { colored: false, set: 'minimal' },
    initialExpansion: 'open',
    initialSelectedPaths: activePath ? [activePath] : [],
    itemHeight: FILE_TREE_ROW_HEIGHT,
    onSelectionChange: (selectedPaths) => {
      const selectedPath = selectedPaths.at(-1);
      if (!selectedPath) return;
      const state = navigationRef.current;
      const folderId = state.folderIdByPath.get(selectedPath);
      if (!folderId || folderId === state.activeFolderId) return;
      state.navigate(
        `${state.rootPath}?folder=${encodeURIComponent(folderId)}`,
      );
    },
    paths: folderTreeModel.paths,
  });

  useEffect(() => {
    model.resetPaths(folderTreeModel.paths);
  }, [folderTreeModel.paths, model]);

  useEffect(() => {
    if (activePath) {
      model.getItem(activePath)?.select();
      model.scrollToPath(activePath, { focus: false, offset: 'nearest' });
      return;
    }
    for (const selectedPath of model.getSelectedPaths()) {
      model.getItem(selectedPath)?.deselect();
    }
  }, [activePath, folderTreeModel.paths, model]);

  const height = Math.min(
    Math.max(
      folderTreeModel.paths.length * FILE_TREE_ROW_HEIGHT,
      FILE_TREE_ROW_HEIGHT,
    ),
    FILE_TREE_MAX_HEIGHT,
  );

  return (
    <div className="py-0.5">
      <FileTree
        model={model}
        style={{
          ...filesSidebarTreeStyle,
          height,
        }}
      />
    </div>
  );
}
