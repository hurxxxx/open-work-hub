import { describe, expect, it } from 'vitest';

import type { FileFolderItem } from './api/files-api';
import { buildFolderTreeModel } from './folder-tree-model';

function folder(
  input: Partial<FileFolderItem> & { id: string; name: string },
): FileFolderItem {
  return {
    can_manage: true,
    created_at: '2026-06-05T00:00:00Z',
    owner_id: 'owner',
    owner_name: 'Owner',
    parent_id: null,
    updated_at: '2026-06-05T00:00:00Z',
    visibility: 'company',
    ...input,
  };
}

describe('folder tree model', () => {
  it('builds sorted folder nodes and path indexes', () => {
    const model = buildFolderTreeModel([
      folder({ id: 'child-b', name: 'Beta', parent_id: 'root' }),
      folder({ id: 'root', name: 'Projects' }),
      folder({ id: 'child-a', name: 'Alpha', parent_id: 'root' }),
      folder({ id: 'other-root', name: 'Archive' }),
    ]);

    expect(model.tree.map((node) => node.id)).toEqual(['other-root', 'root']);
    expect(model.tree[1]?.children.map((node) => node.id)).toEqual([
      'child-a',
      'child-b',
    ]);
    expect(model.paths).toEqual([
      'Archive/',
      'Projects/',
      'Projects/Alpha/',
      'Projects/Beta/',
    ]);
    expect(model.pathByFolderId.get('child-b')).toBe('Projects/Beta/');
    expect(model.folderIdByPath.get('Projects/Alpha/')).toBe('child-a');
    expect(model.supportsPathRendering).toBe(true);
  });

  it('disables path rendering when display paths collide', () => {
    const model = buildFolderTreeModel([
      folder({ id: 'first', name: 'Projects' }),
      folder({ id: 'second', name: 'Projects' }),
    ]);

    expect(model.supportsPathRendering).toBe(false);
  });

  it('disables path rendering when a folder name contains path separators', () => {
    const model = buildFolderTreeModel([
      folder({ id: 'folder', name: 'Design/Research' }),
    ]);

    expect(model.supportsPathRendering).toBe(false);
  });
});
