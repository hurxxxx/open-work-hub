import { useAppAdmission } from '@/src/platform/apps/app-bootstrap-context';
import { useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { NoAccessNotice } from '@/src/components/common/NoAccessNotice';
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
import { listMeetings, type MeetingListItem } from '../api/meeting-api';
import {
  INITIAL_MEETING_PICKER_STATE,
  filterMeetingsForPicker,
  meetingPickerReducer,
  sortMeetingsForPicker,
  type MeetingPickerAction,
} from './meeting-picker-model';

// listMeetings has no `q` parameter, so search remains client-side over the
// returned workspace list until the Meeting API grows a server-side search.
export interface MeetingPickerModalProps {
  isOpen: boolean;
  onClose: () => void;
  onPick: (meeting: MeetingListItem) => Promise<void> | void;
  excludeMeetingIds?: string[];
}

const EMPTY_EXCLUDED_MEETING_IDS: string[] = [];

export function MeetingPickerModal({
  isOpen,
  onClose,
  onPick,
  excludeMeetingIds = EMPTY_EXCLUDED_MEETING_IDS,
}: MeetingPickerModalProps) {
  const { t, i18n } = useTranslation('apps');
  const { token, user } = useAuth();
  const canAccess = useAppAdmission('meeting');
  const timeZone = normalizeTimeZone(user?.time_zone);
  const {
    dispatch,
    handleClose,
    handlePick,
    setQuery,
    state: { error, items, loading, query, submittingId },
  } = useResourcePickerSession<MeetingListItem, MeetingPickerAction>({
    actions: {
      query: (value) => ({ type: 'query', value }),
      reset: () => ({ type: 'reset' }),
      submit: (meeting) => ({ type: 'submit', meetingId: meeting.id }),
      submitFailed: (message) => ({ type: 'submit-failed', message }),
      submitFinished: () => ({ type: 'submit-finished' }),
    },
    getPickFailedMessage: (err) =>
      err instanceof Error ? err.message : t('recording.errors.attachFailed'),
    initialState: INITIAL_MEETING_PICKER_STATE,
    onClose,
    onPick,
    reducer: meetingPickerReducer,
  });

  const loadMeetings = useCallback(async () => {
    if (!token) return [];
    const response = await listMeetings(token, { scope: 'all' });
    return sortMeetingsForPicker(response.items);
  }, [token]);

  useResourcePickerLoad<MeetingListItem, MeetingPickerAction>({
    actions: {
      failed: (message) => ({ type: 'failed', message }),
      load: () => ({ type: 'load' }),
      loaded: (loadedItems) => ({ type: 'loaded', items: loadedItems }),
    },
    dispatch,
    enabled: isOpen && Boolean(token) && canAccess,
    getLoadFailedMessage: (err) =>
      err instanceof Error && err.message
        ? err.message
        : t('recording.detail.meetingPicker.loadFailed'),
    loadItems: loadMeetings,
  });

  const filteredItems = useMemo(
    () =>
      filterMeetingsForPicker(items, {
        excludeMeetingIds,
        query,
      }),
    [excludeMeetingIds, items, query],
  );

  return (
    <ResourcePickerDialog
      accessNotice={
        <NoAccessNotice
          appLabel={t('recording.title')}
          action={t('recording.detail.addMeeting')}
        />
      }
      canAccess={canAccess}
      closeLabel={t('common:actions.close')}
      description={t('recording.detail.meetingPicker.description')}
      emptyLabel={t('recording.detail.meetingPicker.empty')}
      error={error}
      getItemId={(item) => item.id}
      isOpen={isOpen}
      items={filteredItems}
      loading={loading}
      onClose={handleClose}
      onPick={(item) => void handlePick(item)}
      renderItem={(item) => (
        <div className="min-w-0">
          <p className="app-text-body line-clamp-1 text-app-ink">
            {item.title || t('recording.untitled')}
          </p>
          <p className="app-text-caption text-app-ink/40">
            {formatDateTime(item.start_at, {
              day: 'numeric',
              hour: '2-digit',
              locale: i18n.language,
              minute: '2-digit',
              month: 'short',
              timeZone,
            })}
            {item.organizer_name ? ` · ${item.organizer_name}` : ''}
          </p>
        </div>
      )}
      search={{
        label: t('common:actions.search'),
        onChange: setQuery,
        placeholder: t('recording.detail.meetingPicker.searchPlaceholder'),
        value: query,
      }}
      submittingId={submittingId}
      title={t('recording.detail.meetingPicker.title')}
    />
  );
}
