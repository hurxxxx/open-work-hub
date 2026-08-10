import {
  createInitialPickerState,
  pickerReducer,
  projectPickerItems,
  type PickerState,
} from '@/src/platform/pickers/picker-model';
import type { DocsHubItem } from './docs-api';

export type DocsHubPickerSearchMode = 'local' | 'remote';
export type DocsHubPickerItemIdGetter = (item: DocsHubItem) => string;

export interface DocsHubPickerSelection {
  docId: string;
  item: DocsHubItem;
  title: string;
}

export type DocsHubPickerState = PickerState<DocsHubItem>;

export type DocsHubPickerAction =
  | { type: 'reset' }
  | { type: 'load'; resetQuery?: boolean }
  | { type: 'loaded'; items: DocsHubItem[] }
  | { type: 'failed'; message: string }
  | { type: 'query'; value: string }
  | { type: 'submit'; docId: string }
  | { type: 'submit-failed'; message: string }
  | { type: 'submit-finished' };

export type DocsHubPickerParams = {
  page_size: number;
  q?: string;
  sort_by?: string;
  sort_dir?: string;
};

export const DOCS_HUB_PICKER_RESULT_LIMIT = 50;
export const DOCS_HUB_PICKER_PAGE_SIZE = 100;
export const DOCS_HUB_PICKER_REMOTE_SEARCH_DELAY_MS = 200;
export const EMPTY_EXCLUDED_DOC_IDS: string[] = [];

export const INITIAL_DOCS_HUB_PICKER_STATE =
  createInitialPickerState<DocsHubItem>();

export function docsHubPickerReducer(
  state: DocsHubPickerState,
  action: DocsHubPickerAction,
): DocsHubPickerState {
  switch (action.type) {
    case 'load':
      return pickerReducer(state, action, INITIAL_DOCS_HUB_PICKER_STATE);
    case 'submit':
      return pickerReducer(
        state,
        { type: 'submit', itemId: action.docId },
        INITIAL_DOCS_HUB_PICKER_STATE,
      );
    case 'submit-failed':
      return pickerReducer(state, action, INITIAL_DOCS_HUB_PICKER_STATE);
    default:
      return pickerReducer(state, action, INITIAL_DOCS_HUB_PICKER_STATE);
  }
}

export function projectDocsHubPickerItems(args: {
  items: DocsHubItem[];
  query: string;
  excludeDocIds: string[];
  searchMode: DocsHubPickerSearchMode;
  limit?: number;
  getDocId?: DocsHubPickerItemIdGetter;
}): DocsHubItem[] {
  const limit = args.limit ?? DOCS_HUB_PICKER_RESULT_LIMIT;
  const getDocId = args.getDocId ?? getDefaultDocsHubPickerDocId;
  return projectPickerItems({
    items: args.items,
    excludeIds: args.excludeDocIds,
    getItemId: getDocId,
    limit,
    matchesQuery:
      args.searchMode === 'local'
        ? (item, query) => item.title.toLowerCase().includes(query)
        : undefined,
    query: args.query,
  });
}

export function getDefaultDocsHubPickerDocId(item: DocsHubItem): string {
  return item.id;
}

export function buildDocsHubPickerSelection(
  item: DocsHubItem,
  getDocId: DocsHubPickerItemIdGetter = getDefaultDocsHubPickerDocId,
): DocsHubPickerSelection {
  return {
    docId: getDocId(item),
    item,
    title: item.title,
  };
}

export function buildDocsHubPickerParams(args: {
  query: string;
  searchMode: DocsHubPickerSearchMode;
  pageSize?: number;
}): DocsHubPickerParams {
  const params: DocsHubPickerParams = {
    page_size: args.pageSize ?? DOCS_HUB_PICKER_PAGE_SIZE,
  };
  if (args.searchMode === 'remote') {
    const query = normalizeDocsHubPickerQuery(args.query);
    if (query) {
      params.q = query;
    }
    params.sort_by = 'updated_at';
    params.sort_dir = 'desc';
  }
  return params;
}

export function getDocsHubPickerDelayMs(args: {
  query: string;
  searchMode: DocsHubPickerSearchMode;
}): number {
  return args.searchMode === 'remote' && normalizeDocsHubPickerQuery(args.query)
    ? DOCS_HUB_PICKER_REMOTE_SEARCH_DELAY_MS
    : 0;
}

function normalizeDocsHubPickerQuery(query: string): string {
  return query.trim();
}
