// Lightweight modal for adding attendees to an existing meeting. Available to
// any current participant (organizer or existing attendee), unlike
// MeetingEditModal which is organizer-only and edits everything.
//
// Backed by POST /meeting/meetings/{id}/attendees which is participant-permissioned.
import { useEffect, useMemo, useReducer } from 'react';
import { InlineNotice } from '@open-alm/ui';
import { UserPlus } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { FormDialog, FormFieldRow } from '@/src/components/form/FormDialog';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { UserSearchMultiSelect } from '@/src/platform/users/UserSearchMultiSelect';
import type { UserOptionLike } from '@/src/platform/users/user-option-picker-model';
import {
  addMeetingAttendees,
  type MeetingAttendeeInput,
  type MeetingDetail,
  type MeetingUser,
} from '../../api/meeting-api';
import { useMeetingUserSearch } from './useMeetingUserSearch';

interface AddAttendeesModalProps {
  isOpen: boolean;
  meeting: MeetingDetail;
  workspaceSlug: string;
  onClose: () => void;
  onAdded: (updated: MeetingDetail) => void;
}

interface AddAttendeesModalState {
  pending: MeetingAttendeeInput[];
  pendingMeta: Record<string, MeetingUser>;
  query: string;
  queryFocused: boolean;
  results: MeetingUser[];
  searching: boolean;
  submitting: boolean;
  error: string | null;
}

type AddAttendeesModalAction =
  | { type: 'reset' }
  | { type: 'setQuery'; value: string }
  | { type: 'setQueryFocused'; value: boolean }
  | { type: 'searchIdle' }
  | { type: 'searchStarted' }
  | { type: 'searchLoaded'; results: MeetingUser[] }
  | { type: 'searchFailed' }
  | { type: 'addCandidate'; candidate: MeetingUser }
  | { type: 'removePending'; userId: string }
  | { type: 'saveStarted' }
  | { type: 'saveFailed'; message: string }
  | { type: 'saveFinished' };

const INITIAL_ADD_ATTENDEES_MODAL_STATE: AddAttendeesModalState = {
  pending: [],
  pendingMeta: {},
  query: '',
  queryFocused: false,
  results: [],
  searching: false,
  submitting: false,
  error: null,
};

function addAttendeesModalReducer(
  state: AddAttendeesModalState,
  action: AddAttendeesModalAction,
): AddAttendeesModalState {
  switch (action.type) {
    case 'reset':
      return INITIAL_ADD_ATTENDEES_MODAL_STATE;
    case 'setQuery':
      return { ...state, query: action.value };
    case 'setQueryFocused':
      return { ...state, queryFocused: action.value };
    case 'searchIdle':
      return { ...state, results: [], searching: false };
    case 'searchStarted':
      return { ...state, searching: true };
    case 'searchLoaded':
      return { ...state, results: action.results, searching: false };
    case 'searchFailed':
      return { ...state, results: [], searching: false };
    case 'addCandidate':
      return {
        ...state,
        pending: [
          ...state.pending,
          { user_id: action.candidate.id, role: 'required' },
        ],
        pendingMeta: {
          ...state.pendingMeta,
          [action.candidate.id]: action.candidate,
        },
        query: '',
        results: [],
      };
    case 'removePending':
      return {
        ...state,
        pending: state.pending.filter((item) => item.user_id !== action.userId),
      };
    case 'saveStarted':
      return { ...state, submitting: true, error: null };
    case 'saveFailed':
      return { ...state, submitting: false, error: action.message };
    case 'saveFinished':
      return { ...state, submitting: false };
    default:
      return state;
  }
}

export function AddAttendeesModal({
  isOpen,
  meeting,
  workspaceSlug,
  onClose,
  onAdded,
}: AddAttendeesModalProps) {
  const { t } = useTranslation('apps');
  const { token } = useAuth();
  const [
    {
      pending,
      pendingMeta,
      query,
      queryFocused,
      results,
      searching,
      submitting,
      error,
    },
    dispatch,
  ] = useReducer(addAttendeesModalReducer, INITIAL_ADD_ATTENDEES_MODAL_STATE);

  // Reset state whenever the modal opens (so a new meeting context starts fresh).
  useEffect(() => {
    if (!isOpen) return;
    dispatch({ type: 'reset' });
  }, [isOpen, meeting.id]);

  useMeetingUserSearch({
    focused: queryFocused,
    isOpen,
    query,
    token,
    workspaceSlug,
    onIdle: () => dispatch({ type: 'searchIdle' }),
    onStarted: () => dispatch({ type: 'searchStarted' }),
    onLoaded: (results) => dispatch({ type: 'searchLoaded', results }),
    onFailed: () => dispatch({ type: 'searchFailed' }),
  });

  // Hide users who are already meeting attendees + already in the pending bucket.
  const existingIds = useMemo(() => {
    const ids = new Set<string>();
    ids.add(meeting.organizer_id);
    for (const attendee of meeting.attendees) {
      ids.add(attendee.user_id);
    }
    return ids;
  }, [meeting.attendees, meeting.organizer_id]);

  const candidates = useMemo(() => {
    const pendingIds = new Set(pending.map((item) => item.user_id));
    return results
      .filter(
        (candidate) =>
          !existingIds.has(candidate.id) && !pendingIds.has(candidate.id),
      )
      .slice(0, 8);
  }, [results, existingIds, pending]);

  const selectedUsers = useMemo(
    () =>
      pending.map((item): UserOptionLike => {
        const meta = pendingMeta[item.user_id];
        return {
          id: item.user_id,
          email: meta?.email ?? '',
          full_name: meta?.full_name ?? item.user_id,
          primary_org_unit_name: meta?.primary_org_unit_name ?? null,
        };
      }),
    [pending, pendingMeta],
  );

  function addCandidate(candidate: MeetingUser) {
    dispatch({ type: 'addCandidate', candidate });
  }

  function removePending(userId: string) {
    dispatch({ type: 'removePending', userId });
  }

  async function handleSave() {
    if (!token || pending.length === 0) return;
    dispatch({ type: 'saveStarted' });
    try {
      const updated = await addMeetingAttendees(
        token,
        workspaceSlug,
        meeting.id,
        pending,
      );
      onAdded(updated);
    } catch (err) {
      dispatch({
        type: 'saveFailed',
        message:
          err instanceof Error ? err.message : t('meeting.addAttendees.failed'),
      });
    } finally {
      dispatch({ type: 'saveFinished' });
    }
  }

  return (
    <FormDialog
      cancelLabel={t('common:actions.cancel')}
      closeLabel={t('common:actions.close')}
      open={isOpen}
      onCancel={onClose}
      onPrimary={() => void handleSave()}
      title={t('meeting.addAttendees.title')}
      description={t('meeting.addAttendees.description')}
      maxWidth="max-w-md"
      dismissOnInteractOutside={false}
      primaryDisabled={pending.length === 0}
      primaryLabel={t('meeting.addAttendees.addCount', {
        count: pending.length,
      })}
      primaryPendingLabel={t('meeting.addAttendees.adding')}
      submitting={submitting}
    >
      <div className="space-y-4 text-app-ink">
        {error ? (
          <InlineNotice role="alert" tone="danger">
            {error}
          </InlineNotice>
        ) : null}

        <FormFieldRow
          htmlFor="add-attendee-search"
          label={t('meeting.addAttendees.searchLabel')}
        >
          <div className="app-text-overline text-app-ink/60">
            {t('meeting.addAttendees.pendingCount', { count: pending.length })}
          </div>
          <UserSearchMultiSelect
            autoFocus
            candidates={candidates}
            inputId="add-attendee-search"
            labels={{
              noUserMatch: t('common:empty.noResults'),
              removeItem: (name) =>
                `${t('meeting.addAttendees.remove')} ${name}`,
              searchPlaceholder: t('meeting.addAttendees.searchPlaceholder'),
              searchPrompt: t('meeting.form.searchUsersPrompt'),
              searching: t('meeting.addAttendees.searching'),
            }}
            loading={searching}
            onAddUser={addCandidate}
            onQueryChange={(value) => dispatch({ type: 'setQuery', value })}
            onQueryFocusChange={(value) =>
              dispatch({ type: 'setQueryFocused', value })
            }
            onRemoveUser={removePending}
            query={query}
            queryFocused={queryFocused}
            renderCandidateTrailing={() => (
              <UserPlus size={14} className="shrink-0 text-app-accent" />
            )}
            selectedUsers={selectedUsers}
          />
          {pending.length === 0 ? (
            <div className="app-text-caption rounded-md border border-dashed border-app-border p-3 text-center text-app-ink/40">
              {t('meeting.addAttendees.noneSelected')}
            </div>
          ) : null}
        </FormFieldRow>
      </div>
    </FormDialog>
  );
}
