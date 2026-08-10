import { Link } from 'react-router-dom';
import { Folder } from 'lucide-react';

import { cn } from '@/src/lib/utils';
import { buildWorkspaceAppPath } from '@/src/platform/workspaces/workspace-utils';
import type { FolderNode } from './folder-tree-model';

export function FolderTreeRow({
  activeFolderId,
  folder,
  level,
  workspaceSlug,
}: {
  activeFolderId: string | null;
  folder: FolderNode;
  level: number;
  workspaceSlug: string;
}) {
  const path = `${buildWorkspaceAppPath(workspaceSlug, 'files')}?folder=${encodeURIComponent(folder.id)}`;
  return (
    <>
      <Link
        to={path}
        className={cn(
          'sidebar-submenu-item ml-1',
          activeFolderId === folder.id && 'sidebar-submenu-item-active',
        )}
        style={{ paddingLeft: `${12 + level * 12}px` }}
      >
        <Folder size={14} className="text-app-ink/55" />
        <span className="sidebar-submenu-label truncate">{folder.name}</span>
      </Link>
      {folder.children.map((child) => (
        <FolderTreeRow
          key={child.id}
          activeFolderId={activeFolderId}
          folder={child}
          level={level + 1}
          workspaceSlug={workspaceSlug}
        />
      ))}
    </>
  );
}
