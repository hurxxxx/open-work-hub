import type { FileFolderItem } from './api/files-api';

export interface FolderNode extends FileFolderItem {
  children: FolderNode[];
}

export interface FolderTreeModel {
  folderIdByPath: Map<string, string>;
  pathByFolderId: Map<string, string>;
  paths: string[];
  supportsPathRendering: boolean;
  tree: FolderNode[];
}

export function buildFolderTree(folders: FileFolderItem[]): FolderNode[] {
  const nodeById = new Map<string, FolderNode>(
    folders.map((folder) => [folder.id, { ...folder, children: [] }]),
  );
  const roots: FolderNode[] = [];
  for (const node of nodeById.values()) {
    if (node.parent_id && nodeById.has(node.parent_id)) {
      nodeById.get(node.parent_id)?.children.push(node);
    } else {
      roots.push(node);
    }
  }
  const sortNodes = (nodes: FolderNode[]) => {
    nodes.sort((left, right) => left.name.localeCompare(right.name));
    nodes.forEach((node) => sortNodes(node.children));
  };
  sortNodes(roots);
  return roots;
}

export function buildFolderTreeModel(
  folders: FileFolderItem[],
): FolderTreeModel {
  const tree = buildFolderTree(folders);
  const folderIdByPath = new Map<string, string>();
  const pathByFolderId = new Map<string, string>();
  const paths: string[] = [];
  let supportsPathRendering = true;

  function visit(nodes: FolderNode[], parentPath: string) {
    for (const node of nodes) {
      if (node.name.includes('/')) {
        supportsPathRendering = false;
      }
      const path = `${parentPath}${node.name}/`;
      if (folderIdByPath.has(path)) {
        supportsPathRendering = false;
      }
      folderIdByPath.set(path, node.id);
      pathByFolderId.set(node.id, path);
      paths.push(path);
      visit(node.children, path);
    }
  }

  visit(tree, '');

  return {
    folderIdByPath,
    pathByFolderId,
    paths,
    supportsPathRendering,
    tree,
  };
}
