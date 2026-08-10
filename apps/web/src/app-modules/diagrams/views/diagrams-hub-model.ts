import {
  buildWorkspaceAppPath,
  resolveDefaultWorkspaceAppPath,
} from '@/src/platform/workspaces/workspace-utils';
import type { DiagramHubView, DiagramItem } from '../api/diagrams-api';

export type DiagramLayoutMode = 'grid' | 'list';
type LayoutModeStorage = Pick<Storage, 'getItem' | 'setItem'>;
type DiagramHubPathUser = Parameters<typeof resolveDefaultWorkspaceAppPath>[0];

export interface DiagramsHubState {
  items: DiagramItem[];
  loading: boolean;
  error: string | null;
}

export type DiagramsHubAction =
  | { type: 'started' }
  | { type: 'loaded'; items: DiagramItem[] }
  | { type: 'failed'; error: string }
  | { type: 'setError'; error: string | null }
  | { type: 'upsert'; item: DiagramItem }
  | { type: 'remove'; id: string };

export const DIAGRAM_HUB_PAGE_SIZE = 200;
export const DIAGRAM_VIEW_MODE_STORAGE_KEY = 'open-alm:diagrams:view-mode';

export const VIEW_LABEL_KEYS: Record<DiagramHubView, string> = {
  all: 'shell:nav.diagrams-all',
  mine: 'shell:nav.diagrams-mine',
  archived: 'shell:nav.diagrams-archived',
};

export const INITIAL_HUB_STATE: DiagramsHubState = {
  items: [],
  loading: false,
  error: null,
};

export function diagramsHubReducer(
  state: DiagramsHubState,
  action: DiagramsHubAction,
): DiagramsHubState {
  switch (action.type) {
    case 'started':
      return { ...state, loading: true, error: null };
    case 'loaded':
      return { ...state, loading: false, items: action.items };
    case 'failed':
      return { ...state, loading: false, items: [], error: action.error };
    case 'setError':
      return { ...state, error: action.error };
    case 'upsert':
      return {
        ...state,
        items: state.items.some((item) => item.id === action.item.id)
          ? state.items.map((item) =>
              item.id === action.item.id ? action.item : item,
            )
          : [action.item, ...state.items],
      };
    case 'remove':
      return {
        ...state,
        items: state.items.filter((item) => item.id !== action.id),
      };
    default:
      return state;
  }
}

export function viewFromSearch(value: string | null): DiagramHubView {
  if (value === 'mine' || value === 'archived') return value;
  return 'all';
}

export function itemPath({
  itemId,
  user,
  workspaceSlug,
}: {
  itemId: string;
  user: DiagramHubPathUser;
  workspaceSlug?: string | null;
}): string {
  const suffix = `/${encodeURIComponent(itemId)}`;
  return workspaceSlug
    ? buildWorkspaceAppPath(workspaceSlug, 'diagrams', suffix)
    : resolveDefaultWorkspaceAppPath(user, 'diagrams', suffix);
}

export function rootPath(
  workspaceSlug: string | undefined | null,
  user: DiagramHubPathUser,
  searchParams: URLSearchParams,
): string {
  const basePath = workspaceSlug
    ? buildWorkspaceAppPath(workspaceSlug, 'diagrams')
    : resolveDefaultWorkspaceAppPath(user, 'diagrams');
  const query = searchParams.toString();
  return query ? `${basePath}?${query}` : basePath;
}

function getBrowserLayoutStorage(): LayoutModeStorage | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function readStoredDiagramLayoutMode(
  storage: LayoutModeStorage | null = getBrowserLayoutStorage(),
): DiagramLayoutMode {
  if (!storage) return 'grid';
  return storage.getItem(DIAGRAM_VIEW_MODE_STORAGE_KEY) === 'list'
    ? 'list'
    : 'grid';
}

export function writeStoredDiagramLayoutMode(
  layoutMode: DiagramLayoutMode,
  storage: LayoutModeStorage | null = getBrowserLayoutStorage(),
): void {
  if (!storage) return;
  storage.setItem(DIAGRAM_VIEW_MODE_STORAGE_KEY, layoutMode);
}
