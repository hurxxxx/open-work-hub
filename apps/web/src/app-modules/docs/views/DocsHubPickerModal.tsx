import { useAppAdmission } from '@/src/platform/apps/app-bootstrap-context';
import type { ReactNode } from 'react';
import { useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { NoAccessNotice } from '@/src/components/common/NoAccessNotice';
import { ResourcePickerDialog } from '@/src/components/picker/ResourcePickerDialog';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  useResourcePickerLoad,
  useResourcePickerSession,
} from '@/src/platform/pickers/resource-picker-session';
import { listDocsHub, type DocsHubItem } from '../api/docs-api';
import {
  EMPTY_EXCLUDED_DOC_IDS,
  INITIAL_DOCS_HUB_PICKER_STATE,
  buildDocsHubPickerParams,
  buildDocsHubPickerSelection,
  docsHubPickerReducer,
  getDocsHubPickerDelayMs,
  projectDocsHubPickerItems,
  type DocsHubPickerAction,
  type DocsHubPickerItemIdGetter,
  type DocsHubPickerParams,
  type DocsHubPickerSearchMode,
  type DocsHubPickerSelection,
} from '../api/docs-hub-picker-model';

export interface DocsHubPickerCopy {
  title: string;
  description: string;
  searchPlaceholder: string;
  empty: string;
  loadFailed: string;
  attachFailed: string;
  noAccessAppLabel?: string;
  noAccessAction?: string;
  untitled?: string;
}

export interface DocsHubPickerAdapter {
  searchMode: DocsHubPickerSearchMode;
  access: 'app-admission' | 'token-only';
  copy: DocsHubPickerCopy;
  getDocId?: DocsHubPickerItemIdGetter;
  renderMeta: (item: DocsHubItem) => ReactNode;
  filterLoadedItems?: (items: DocsHubItem[]) => DocsHubItem[];
  renderLeadingIcon?: (item: DocsHubItem) => ReactNode;
  listParams?: Partial<DocsHubPickerParams>;
  getLoadFailedMessage?: (error: unknown) => string;
  getAttachFailedMessage?: (error: unknown) => string;
  layer?: 'default' | 'elevated';
  listMaxHeightClassName?: string;
  pageSize?: number;
}

export interface DocsHubPickerModalProps {
  isOpen: boolean;
  onClose: () => void;

  excludeDocIds?: readonly string[];
  onPick: (selection: DocsHubPickerSelection) => Promise<void> | void;
  adapter: DocsHubPickerAdapter;
}

export function DocsHubPickerModal({
  isOpen,
  onClose,
  excludeDocIds = EMPTY_EXCLUDED_DOC_IDS,
  onPick,
  adapter,
}: DocsHubPickerModalProps) {
  const { t } = useTranslation('apps');
  const { token } = useAuth();
  const canAccess = useAppAdmission('docs');
  const getDocId = adapter.getDocId;
  const {
    dispatch,
    handleClose,
    handlePick,
    setQuery,
    state: { error, items, loading, query, submittingId },
  } = useResourcePickerSession<DocsHubItem, DocsHubPickerAction>({
    actions: {
      query: (value) => ({ type: 'query', value }),
      reset: () => ({ type: 'reset' }),
      submit: (item) => ({
        type: 'submit',
        docId: buildDocsHubPickerSelection(item, getDocId).docId,
      }),
      submitFailed: (message) => ({ type: 'submit-failed', message }),
      submitFinished: () => ({ type: 'submit-finished' }),
    },
    getPickFailedMessage: (err) =>
      adapter.getAttachFailedMessage
        ? adapter.getAttachFailedMessage(err)
        : err instanceof Error
          ? err.message
          : adapter.copy.attachFailed,
    initialState: INITIAL_DOCS_HUB_PICKER_STATE,
    onClose,
    onPick: (doc) => onPick(buildDocsHubPickerSelection(doc, getDocId)),
    reducer: docsHubPickerReducer,
  });
  const requestQuery = adapter.searchMode === 'remote' ? query : '';

  const loadDocs = useCallback(async () => {
    if (!token) return [];
    const response = await listDocsHub(token, {
      ...buildDocsHubPickerParams({
        query: requestQuery,
        searchMode: adapter.searchMode,
        pageSize: adapter.pageSize,
      }),
      ...adapter.listParams,
    });
    return adapter.filterLoadedItems
      ? adapter.filterLoadedItems(response.items)
      : response.items;
  }, [adapter, requestQuery, token]);

  useResourcePickerLoad<DocsHubItem, DocsHubPickerAction>({
    actions: {
      failed: (message) => ({ type: 'failed', message }),
      load: () => ({
        type: 'load',
        resetQuery: adapter.searchMode === 'local',
      }),
      loaded: (loadedItems) => ({ type: 'loaded', items: loadedItems }),
    },
    deferLoad: true,
    delayMs: getDocsHubPickerDelayMs({
      query: requestQuery,
      searchMode: adapter.searchMode,
    }),
    dispatch,
    enabled: isOpen && Boolean(token) && canAccess,
    getLoadFailedMessage: (err) =>
      adapter.getLoadFailedMessage
        ? adapter.getLoadFailedMessage(err)
        : err instanceof Error && err.message
          ? err.message
          : adapter.copy.loadFailed,
    loadItems: loadDocs,
  });

  const visibleItems = useMemo(
    () =>
      projectDocsHubPickerItems({
        items,
        query,
        excludeDocIds: [...excludeDocIds],
        searchMode: adapter.searchMode,
        getDocId,
      }),
    [adapter.searchMode, excludeDocIds, getDocId, items, query],
  );

  return (
    <ResourcePickerDialog
      accessNotice={
        <NoAccessNotice
          appLabel={adapter.copy.noAccessAppLabel ?? adapter.copy.title}
          action={adapter.copy.noAccessAction ?? adapter.copy.title}
        />
      }
      canAccess={canAccess}
      closeLabel={t('common:actions.close')}
      description={adapter.copy.description}
      emptyLabel={adapter.copy.empty}
      error={error}
      getItemId={(item) => buildDocsHubPickerSelection(item, getDocId).docId}
      isOpen={isOpen}
      items={visibleItems}
      layer={adapter.layer}
      listMaxHeightClassName={adapter.listMaxHeightClassName}
      loading={loading}
      onClose={handleClose}
      onPick={(item) => void handlePick(item)}
      renderItem={(item) => (
        <>
          {adapter.renderLeadingIcon?.(item)}
          <div className="min-w-0 flex-1">
            <p className="app-text-body line-clamp-1 text-app-ink">
              {item.title || adapter.copy.untitled || item.id}
            </p>
            <p className="app-text-caption text-app-ink/40">
              {adapter.renderMeta(item)}
            </p>
          </div>
        </>
      )}
      search={{
        label: t('common:actions.search'),
        onChange: setQuery,
        placeholder: adapter.copy.searchPlaceholder,
        value: query,
      }}
      submittingId={submittingId}
      title={adapter.copy.title}
    />
  );
}
