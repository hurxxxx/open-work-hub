import { PencilRuler } from 'lucide-react';
import { useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { ResourcePickerDialog } from '@/src/components/picker/ResourcePickerDialog';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  useResourcePickerLoad,
  useResourcePickerSession,
} from '@/src/platform/pickers/resource-picker-session';
import {
  formatDateTime,
  normalizeTimeZone,
} from '@/src/platform/time/time-utils';
import {
  listWhiteboardHub,
  type WhiteboardHubItem,
} from '../api/whiteboard-api';
import {
  INITIAL_WHITEBOARD_PICKER_STATE,
  filterWhiteboardsForPicker,
  whiteboardPickerReducer,
  type WhiteboardPickerAction,
} from './whiteboard-picker-model';

export interface WhiteboardPickerModalProps {
  isOpen: boolean;

  excludeWhiteboardIds?: string[];
  onClose: () => void;
  onPick: (item: WhiteboardHubItem) => Promise<void | boolean> | void | boolean;
}

const EMPTY_EXCLUDED_WHITEBOARD_IDS: string[] = [];

export function WhiteboardPickerModal(props: WhiteboardPickerModalProps) {
  const { token } = useAuth();
  return props.isOpen ? (
    <WhiteboardPickerSession key={token} {...props} />
  ) : null;
}

function WhiteboardPickerSession({
  isOpen,
  excludeWhiteboardIds = EMPTY_EXCLUDED_WHITEBOARD_IDS,
  onClose,
  onPick,
}: WhiteboardPickerModalProps) {
  const { t, i18n } = useTranslation(['apps', 'common']);
  const { token, user } = useAuth();
  const timeZone = normalizeTimeZone(user?.time_zone);
  const {
    dispatch,
    handleClose,
    handlePick,
    setQuery,
    state: { error, items, loading, query, submittingId },
  } = useResourcePickerSession<WhiteboardHubItem, WhiteboardPickerAction>({
    actions: {
      query: (value) => ({ type: 'query', value }),
      submit: (item) => ({ type: 'submit', itemId: item.id }),
      submitFailed: (message) => ({ type: 'submit-failed', message }),
      submitFinished: () => ({ type: 'submit-finished' }),
    },
    getPickFailedMessage: (err) =>
      err instanceof Error ? err.message : t('apps:whiteboard.connectFailed'),
    initialState: INITIAL_WHITEBOARD_PICKER_STATE,
    onClose,
    onPick,
    reducer: whiteboardPickerReducer,
  });

  const loadWhiteboards = useCallback(async () => {
    if (!token) return [];
    const response = await listWhiteboardHub(token, {
      view: 'all',
      sort_by: 'updated_at',
      sort_dir: 'desc',
      page_size: 100,
    });
    return response.items;
  }, [token]);

  useResourcePickerLoad<WhiteboardHubItem, WhiteboardPickerAction>({
    actions: {
      failed: (message) => ({ type: 'failed', message }),
      load: () => ({ type: 'load' }),
      loaded: (loadedItems) => ({ type: 'loaded', items: loadedItems }),
    },
    dispatch,
    enabled: isOpen && Boolean(token),
    getLoadFailedMessage: (err) =>
      err instanceof Error && err.message
        ? err.message
        : t('apps:whiteboard.loadFailed'),
    loadItems: loadWhiteboards,
  });

  const filteredItems = useMemo(
    () =>
      filterWhiteboardsForPicker(items, {
        excludeWhiteboardIds,
        query,
      }),
    [excludeWhiteboardIds, items, query],
  );

  return (
    <ResourcePickerDialog
      closeLabel={t('common:actions.close')}
      description={t('apps:whiteboard.pickerDescription')}
      emptyLabel={t('apps:whiteboard.pickerEmpty')}
      error={error}
      getItemId={(item) => item.id}
      isOpen={isOpen}
      items={filteredItems}
      listMaxHeightClassName="max-h-80"
      loading={loading}
      onClose={handleClose}
      onPick={(item) => void handlePick(item)}
      renderItem={(item) => (
        <>
          <PencilRuler size={16} className="shrink-0 text-app-accent" />
          <div className="min-w-0">
            <p className="app-text-body line-clamp-1 text-app-ink">
              {item.title}
            </p>
            <p className="app-text-caption text-app-ink/45">
              {item.location_label} ·{' '}
              {formatDateTime(item.updated_at, {
                day: 'numeric',
                locale: i18n.language,
                month: 'short',
                timeZone,
              })}
            </p>
          </div>
        </>
      )}
      search={{
        label: t('common:actions.search'),
        onChange: setQuery,
        placeholder: t('apps:whiteboard.searchByTitle'),
        value: query,
      }}
      submittingId={submittingId}
      title={t('apps:whiteboard.pickerTitle')}
    />
  );
}
