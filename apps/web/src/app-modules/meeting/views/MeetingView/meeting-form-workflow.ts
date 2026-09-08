import { useEffect, useMemo, useReducer } from 'react';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  createMeeting,
  listMeetingUsers,
  updateMeeting,
  uploadMeetingFile,
  type MeetingDetail,
  type MeetingUser,
} from '../../api/meeting-api';
import {
  addCreateAttendeeToForm,
  addEditAttendeeToForm,
  createInitialMeetingEditState,
  createInitialMeetingState,
  meetingCreateReducer,
  meetingEditReducer,
  projectMeetingCreateForm,
  projectMeetingEditForm,
  removeAttendeeFromForm,
  removePickedFileAtIndex,
  removePickedItem,
  type MeetingCreateState,
  type MeetingEditState,
  type MeetingInitialRange,
  type PickedDoc,
  type PickedTask,
} from './meeting-form-model';
import {
  submitMeetingCreateForm,
  submitMeetingEditForm,
  type MeetingFormSubmissionMessages,
} from './meeting-form-submission';
import { useMeetingUserSearch } from './useMeetingUserSearch';

export interface MeetingFormApiAdapter {
  createMeeting: typeof createMeeting;
  updateMeeting: typeof updateMeeting;
  uploadMeetingFile: typeof uploadMeetingFile;
  listMeetingUsers: typeof listMeetingUsers;
}

export interface MeetingCreateFormWorkflowOptions {
  isOpen: boolean;
  onCreated: (meetingId: string) => void;

  initialRange?: MeetingInitialRange | null;
  api?: MeetingFormApiAdapter;
}

export interface MeetingEditFormWorkflowOptions {
  isOpen: boolean;
  meeting: MeetingDetail;
  onSaved: (updated: MeetingDetail) => void;

  api?: MeetingFormApiAdapter;
}

export const meetingFormApiAdapter: MeetingFormApiAdapter = {
  createMeeting,
  updateMeeting,
  uploadMeetingFile,
  listMeetingUsers,
};

function createSubmissionMessages(
  t: ReturnType<typeof useTranslation>['t'],
): MeetingFormSubmissionMessages {
  return {
    endAfterStart: t('meeting.form.endAfterStart'),
    createFailed: t('meeting.create.failed'),
    editFailed: t('meeting.editMeeting.failed'),
    partialUploadFailed: t('meeting.create.partialFailed'),
    fileFailureDefault: t('meeting.create.fileFailureDefault'),
    fileFailure: ({ name, message }) =>
      t('meeting.create.fileFailure', { name, message }),
  };
}

export function useMeetingCreateFormWorkflow({
  isOpen,
  onCreated,
  initialRange,
  api = meetingFormApiAdapter,
}: MeetingCreateFormWorkflowOptions) {
  const { t } = useTranslation('apps');
  const { token, user } = useAuth();
  const [state, dispatch] = useReducer(
    meetingCreateReducer,
    { initialRange, currentUserId: user?.id },
    ({ initialRange, currentUserId }) =>
      createInitialMeetingState(initialRange, currentUserId),
  );

  useEffect(() => {
    if (!isOpen) return;
    dispatch({ type: 'reset', initialRange, currentUserId: user?.id });
  }, [isOpen, initialRange, user?.id]);

  useMeetingUserSearch({
    focused: state.userQueryFocused,
    isOpen,
    query: state.userQuery,
    token,
    searchUsers: api.listMeetingUsers,
    onIdle: () =>
      dispatch({ type: 'patch', patch: { users: [], usersLoading: false } }),
    onStarted: () => dispatch({ type: 'patch', patch: { usersLoading: true } }),
    onLoaded: (users) =>
      dispatch({ type: 'patch', patch: { users, usersLoading: false } }),
    onFailed: () =>
      dispatch({ type: 'patch', patch: { users: [], usersLoading: false } }),
  });

  const projection = useMemo(
    () => projectMeetingCreateForm(state, user?.id),
    [state, user?.id],
  );

  function patch(patchValue: Partial<MeetingCreateState>) {
    dispatch({ type: 'patch', patch: patchValue });
  }

  function addAttendee(attendee: MeetingUser) {
    patch(
      addCreateAttendeeToForm(
        {
          attendees: state.attendees,
          pickedAttendeeUsers: state.pickedAttendeeUsers,
        },
        attendee,
      ),
    );
  }

  function removeAttendee(userId: string) {
    patch({
      attendees: removeAttendeeFromForm(
        state.attendees,
        userId,
        new Set(user?.id ? [user.id] : []),
      ),
    });
  }

  function addFiles(files: File[]) {
    if (files.length === 0) return;
    patch({ pickedFiles: [...state.pickedFiles, ...files] });
  }

  async function submit() {
    if (!token || !state.title.trim()) return;
    patch({ error: null, partialFailures: [], submitting: true });
    try {
      const result = await submitMeetingCreateForm({
        token,
        state,
        ports: api,
        messages: createSubmissionMessages(t),
      });

      switch (result.status) {
        case 'validation_failed':
        case 'failed':
          patch({ error: result.error });
          return;
        case 'partial_upload_failed':
          patch({
            createdMeetingId: result.createdMeetingId,
            error: result.error,
            partialFailures: result.failures,
            pickedFiles: result.remainingFiles,
          });
          return;
        case 'created':
          onCreated(result.meeting.id);
      }
    } finally {
      patch({ submitting: false });
    }
  }

  return {
    state,
    projection,
    t,
    user,
    actions: {
      patch,
      addAttendee,
      removeAttendee,
      addFiles,
      removePickedFile: (index: number) =>
        patch({
          pickedFiles: removePickedFileAtIndex(state.pickedFiles, index),
        }),
      removePickedTask: (taskId: string) =>
        patch({ pickedTasks: removePickedItem(state.pickedTasks, taskId) }),
      removePickedDoc: (docId: string) =>
        patch({ pickedDocs: removePickedItem(state.pickedDocs, docId) }),
      pickTask: (task: PickedTask) =>
        patch({ pickedTasks: [...state.pickedTasks, task] }),
      pickDoc: (doc: PickedDoc) =>
        patch({ pickedDocs: [...state.pickedDocs, doc] }),
      submit,
      openCreatedMeeting: () => {
        if (state.createdMeetingId) onCreated(state.createdMeetingId);
      },
    },
  } as const;
}

export function useMeetingEditFormWorkflow({
  isOpen,
  meeting,
  onSaved,
  api = meetingFormApiAdapter,
}: MeetingEditFormWorkflowOptions) {
  const { t } = useTranslation('apps');
  const { token, user } = useAuth();
  const [state, dispatch] = useReducer(
    meetingEditReducer,
    meeting,
    createInitialMeetingEditState,
  );

  useEffect(() => {
    if (!isOpen) return;
    dispatch({ type: 'reset', meeting });
  }, [isOpen, meeting]);

  useMeetingUserSearch({
    focused: state.userQueryFocused,
    isOpen,
    query: state.userQuery,
    token,
    searchUsers: api.listMeetingUsers,
    onIdle: () =>
      dispatch({ type: 'patch', patch: { users: [], usersLoading: false } }),
    onStarted: () => dispatch({ type: 'patch', patch: { usersLoading: true } }),
    onLoaded: (users) =>
      dispatch({ type: 'patch', patch: { users, usersLoading: false } }),
    onFailed: () =>
      dispatch({ type: 'patch', patch: { users: [], usersLoading: false } }),
  });

  const projection = useMemo(
    () => projectMeetingEditForm(state, meeting.organizer_id, user?.id),
    [meeting.organizer_id, state, user?.id],
  );

  function patch(patchValue: Partial<MeetingEditState>) {
    dispatch({ type: 'patch', patch: patchValue });
  }

  function addAttendee(attendee: MeetingUser) {
    patch(
      addEditAttendeeToForm(
        { attendees: state.attendees, knownUsers: state.knownUsers },
        attendee,
      ),
    );
  }

  function removeAttendee(userId: string) {
    patch({
      attendees: removeAttendeeFromForm(
        state.attendees,
        userId,
        new Set([meeting.organizer_id]),
      ),
    });
  }

  async function submit() {
    if (!token || !state.title.trim()) return;
    patch({ error: null, submitting: true });
    try {
      const result = await submitMeetingEditForm({
        token,
        meetingId: meeting.id,
        state,
        ports: api,
        messages: createSubmissionMessages(t),
      });

      switch (result.status) {
        case 'validation_failed':
        case 'failed':
          patch({ error: result.error });
          return;
        case 'saved':
          onSaved(result.meeting);
      }
    } finally {
      patch({ submitting: false });
    }
  }

  return {
    state,
    projection,
    t,
    user,
    actions: {
      patch,
      addAttendee,
      removeAttendee,
      submit,
    },
  } as const;
}
