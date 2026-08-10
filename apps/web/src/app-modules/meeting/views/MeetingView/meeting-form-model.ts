import {
  parseServerDateTime,
  type MeetingAttendeeInput,
  type MeetingCreateInput,
  type MeetingDetail,
  type MeetingUpdateInput,
  type MeetingUser,
} from '../../api/meeting-api';
import {
  formatNativeDateTimeInputValue,
  nativeDateTimeInputValueToIso,
} from '@/src/platform/time/native-date-input';

export interface PickedTask {
  id: string;
  title: string;
  reference: string;
}

export interface PickedDoc {
  id: string;
  title: string;
}

export type MeetingInitialRange = {
  start: Date;
  end: Date;
  allDay: boolean;
};

export interface MeetingCreateState {
  title: string;
  agenda: string;
  startAt: string;
  endAt: string;
  attendees: MeetingAttendeeInput[];
  pickedAttendeeUsers: MeetingUser[];
  users: MeetingUser[];
  userQuery: string;
  userQueryFocused: boolean;
  usersLoading: boolean;
  pickedTasks: PickedTask[];
  pickedDocs: PickedDoc[];
  pickedFiles: File[];
  taskPickerOpen: boolean;
  docPickerOpen: boolean;
  submitting: boolean;
  error: string | null;
  createdMeetingId: string | null;
  partialFailures: string[];
}

export type MeetingCreateAction =
  | {
      type: 'reset';
      initialRange: MeetingInitialRange | null | undefined;
      currentUserId: string | undefined;
    }
  | { type: 'patch'; patch: Partial<MeetingCreateState> };

export interface MeetingEditState {
  title: string;
  agenda: string;
  startAt: string;
  endAt: string;
  attendees: MeetingAttendeeInput[];
  knownUsers: MeetingUser[];
  users: MeetingUser[];
  userQuery: string;
  userQueryFocused: boolean;
  usersLoading: boolean;
  submitting: boolean;
  error: string | null;
}

export interface MeetingCreateFormProjection {
  availabilityUsers: MeetingUser[];
  canSubmit: boolean;
  filteredUsers: MeetingUser[];
  pickedDocIds: string[];
  pickedTaskIds: string[];
  userLookup: Map<string, MeetingUser>;
  visibleAttendees: MeetingAttendeeInput[];
}

export interface MeetingEditFormProjection {
  availabilityUsers: MeetingUser[];
  canSubmit: boolean;
  filteredUsers: MeetingUser[];
  lockedOrganizerIds: Set<string>;
  userLookup: Map<string, MeetingUser>;
  visibleAttendees: MeetingAttendeeInput[];
}

export type MeetingEditAction =
  | { type: 'reset'; meeting: MeetingDetail }
  | { type: 'patch'; patch: Partial<MeetingEditState> };

type FileLike = Pick<File, 'lastModified' | 'name' | 'size'>;

export type FileUploadResult<TFile extends FileLike> =
  | { file: TFile; failure: string }
  | { file: TFile; failure: null };

export function toLocalInputValue(date: Date): string {
  return formatNativeDateTimeInputValue(date);
}

export function serverDateTimeToLocalInputValue(iso: string): string {
  return toLocalInputValue(parseServerDateTime(iso));
}

export function localInputToIso(value: string): string {
  return nativeDateTimeInputValueToIso(value);
}

export function createDefaultMeetingRange(now = new Date()): {
  start: string;
  end: string;
} {
  const start = new Date(now.getTime());
  start.setMinutes(0, 0, 0);
  start.setHours(start.getHours() + 1);

  const end = new Date(now.getTime());
  end.setMinutes(0, 0, 0);
  end.setHours(end.getHours() + 2);

  return { start: toLocalInputValue(start), end: toLocalInputValue(end) };
}

/** Derive (startAt, endAt) inputs from a calendar slot selection.
 *  Month-view cells arrive as all-day ranges: convert to a 1-hour 09:00 slot
 *  on the selected day since meetings aren't stored as all-day. */
export function rangeToInputs(range: MeetingInitialRange): {
  start: string;
  end: string;
} {
  if (range.allDay) {
    const start = new Date(
      range.start.getFullYear(),
      range.start.getMonth(),
      range.start.getDate(),
      9,
      0,
      0,
      0,
    );
    const end = new Date(start.getTime());
    end.setHours(end.getHours() + 1);
    return { start: toLocalInputValue(start), end: toLocalInputValue(end) };
  }
  return {
    start: toLocalInputValue(range.start),
    end: toLocalInputValue(range.end),
  };
}

export function createInitialMeetingState(
  initialRange: MeetingInitialRange | null | undefined,
  currentUserId: string | undefined,
  now = new Date(),
): MeetingCreateState {
  const rangeInput = initialRange
    ? rangeToInputs(initialRange)
    : createDefaultMeetingRange(now);

  return {
    title: '',
    agenda: '',
    startAt: rangeInput.start,
    endAt: rangeInput.end,
    attendees: currentUserId
      ? [{ user_id: currentUserId, role: 'required' }]
      : [],
    pickedAttendeeUsers: [],
    users: [],
    userQuery: '',
    userQueryFocused: false,
    usersLoading: false,
    pickedTasks: [],
    pickedDocs: [],
    pickedFiles: [],
    taskPickerOpen: false,
    docPickerOpen: false,
    submitting: false,
    error: null,
    createdMeetingId: null,
    partialFailures: [],
  };
}

export function meetingCreateReducer(
  state: MeetingCreateState,
  action: MeetingCreateAction,
): MeetingCreateState {
  switch (action.type) {
    case 'reset':
      return createInitialMeetingState(
        action.initialRange,
        action.currentUserId,
      );
    case 'patch':
      return { ...state, ...action.patch };
  }
}

export function createInitialMeetingEditState(
  meeting: MeetingDetail,
): MeetingEditState {
  return {
    title: meeting.title,
    agenda: meeting.agenda,
    startAt: serverDateTimeToLocalInputValue(meeting.start_at),
    endAt: serverDateTimeToLocalInputValue(meeting.end_at),
    attendees: meeting.attendees.map((attendee) => ({
      user_id: attendee.user_id,
      role: attendee.role,
    })),
    knownUsers: meeting.attendees.map((attendee) => ({
      id: attendee.user_id,
      email: attendee.email,
      full_name: attendee.full_name,
    })),
    users: [],
    userQuery: '',
    userQueryFocused: false,
    usersLoading: false,
    submitting: false,
    error: null,
  };
}

export function meetingEditReducer(
  state: MeetingEditState,
  action: MeetingEditAction,
): MeetingEditState {
  switch (action.type) {
    case 'reset':
      return createInitialMeetingEditState(action.meeting);
    case 'patch':
      return { ...state, ...action.patch };
  }
}

export function buildUserLookup(
  primaryUsers: MeetingUser[],
  searchedUsers: MeetingUser[],
): Map<string, MeetingUser> {
  const map = new Map<string, MeetingUser>();
  primaryUsers.forEach((user) => map.set(user.id, user));
  searchedUsers.forEach((user) => map.set(user.id, user));
  return map;
}

export function filterCreateCandidateUsers(
  users: MeetingUser[],
  attendees: MeetingAttendeeInput[],
  currentUserId: string | undefined,
): MeetingUser[] {
  const selectedIds = new Set(attendees.map((item) => item.user_id));
  return users
    .filter(
      (candidate) =>
        candidate.id !== currentUserId && !selectedIds.has(candidate.id),
    )
    .slice(0, 8);
}

export function filterEditCandidateUsers(
  users: MeetingUser[],
  attendees: MeetingAttendeeInput[],
  organizerId: string,
  currentUserId: string | undefined,
): MeetingUser[] {
  const selectedIds = new Set(attendees.map((item) => item.user_id));
  return users
    .filter((candidate) => {
      if (selectedIds.has(candidate.id)) return false;
      if (currentUserId === organizerId && candidate.id === organizerId) {
        return false;
      }
      return true;
    })
    .slice(0, 8);
}

export function getVisibleCreateAttendees(
  attendees: MeetingAttendeeInput[],
  currentUserId: string | undefined,
): MeetingAttendeeInput[] {
  return attendees.filter((attendee) => attendee.user_id !== currentUserId);
}

export function getVisibleEditAttendees(
  attendees: MeetingAttendeeInput[],
  organizerId: string,
  currentUserId: string | undefined,
): MeetingAttendeeInput[] {
  if (currentUserId !== organizerId) {
    return attendees;
  }
  return attendees.filter((attendee) => attendee.user_id !== organizerId);
}

export function mapAvailabilityUsers(
  visibleAttendees: MeetingAttendeeInput[],
  userLookup: Map<string, MeetingUser>,
): MeetingUser[] {
  return visibleAttendees.map((attendee) => {
    const candidate = userLookup.get(attendee.user_id);
    return {
      id: attendee.user_id,
      email: candidate?.email ?? '',
      full_name: candidate?.full_name ?? attendee.user_id,
    };
  });
}

export function projectMeetingCreateForm(
  state: Pick<
    MeetingCreateState,
    | 'attendees'
    | 'pickedAttendeeUsers'
    | 'pickedDocs'
    | 'pickedTasks'
    | 'submitting'
    | 'title'
    | 'users'
  >,
  currentUserId: string | undefined,
): MeetingCreateFormProjection {
  const userLookup = buildUserLookup(state.pickedAttendeeUsers, state.users);
  const visibleAttendees = getVisibleCreateAttendees(state.attendees, currentUserId);
  return {
    availabilityUsers: mapAvailabilityUsers(visibleAttendees, userLookup),
    canSubmit: Boolean(state.title.trim() && !state.submitting),
    filteredUsers: filterCreateCandidateUsers(state.users, state.attendees, currentUserId),
    pickedDocIds: state.pickedDocs.map((doc) => doc.id),
    pickedTaskIds: state.pickedTasks.map((task) => task.id),
    userLookup,
    visibleAttendees,
  };
}

export function projectMeetingEditForm(
  state: Pick<
    MeetingEditState,
    | 'attendees'
    | 'knownUsers'
    | 'submitting'
    | 'title'
    | 'users'
  >,
  organizerId: string,
  currentUserId: string | undefined,
): MeetingEditFormProjection {
  const userLookup = buildUserLookup(state.knownUsers, state.users);
  const visibleAttendees = getVisibleEditAttendees(
    state.attendees,
    organizerId,
    currentUserId,
  );
  return {
    availabilityUsers: mapAvailabilityUsers(visibleAttendees, userLookup),
    canSubmit: Boolean(state.title.trim() && !state.submitting),
    filteredUsers: filterEditCandidateUsers(
      state.users,
      state.attendees,
      organizerId,
      currentUserId,
    ),
    lockedOrganizerIds: new Set([organizerId]),
    userLookup,
    visibleAttendees,
  };
}

export function addCreateAttendeeToForm(
  state: Pick<MeetingCreateState, 'attendees' | 'pickedAttendeeUsers'>,
  user: MeetingUser,
): Pick<MeetingCreateState, 'attendees' | 'pickedAttendeeUsers' | 'userQuery'> {
  return {
    attendees: [...state.attendees, { user_id: user.id, role: 'required' }],
    pickedAttendeeUsers: state.pickedAttendeeUsers.some(
      (item) => item.id === user.id,
    )
      ? state.pickedAttendeeUsers
      : [...state.pickedAttendeeUsers, user],
    userQuery: '',
  };
}

export function addEditAttendeeToForm(
  state: Pick<MeetingEditState, 'attendees' | 'knownUsers'>,
  user: MeetingUser,
): Pick<MeetingEditState, 'attendees' | 'knownUsers' | 'userQuery'> {
  return {
    attendees: [...state.attendees, { user_id: user.id, role: 'required' }],
    knownUsers: state.knownUsers.some((item) => item.id === user.id)
      ? state.knownUsers
      : [...state.knownUsers, user],
    userQuery: '',
  };
}

export function removeAttendeeFromForm(
  attendees: MeetingAttendeeInput[],
  userId: string,
  lockedUserIds: ReadonlySet<string>,
): MeetingAttendeeInput[] {
  if (lockedUserIds.has(userId)) {
    return attendees;
  }
  return attendees.filter((item) => item.user_id !== userId);
}

export function removePickedItem<TItem extends { id: string }>(
  items: TItem[],
  id: string,
): TItem[] {
  return items.filter((item) => item.id !== id);
}

export function removePickedFileAtIndex<TFile>(
  files: TFile[],
  index: number,
): TFile[] {
  return files.filter((_, i) => i !== index);
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function buildCreateMeetingPayload(
  state: Pick<
    MeetingCreateState,
    | 'agenda'
    | 'attendees'
    | 'endAt'
    | 'pickedDocs'
    | 'pickedTasks'
    | 'startAt'
    | 'title'
  >,
): MeetingCreateInput {
  return {
    title: state.title.trim(),
    agenda: state.agenda.trim(),
    start_at: localInputToIso(state.startAt),
    end_at: localInputToIso(state.endAt),
    attendees: state.attendees,
    task_ids: state.pickedTasks.map((task) => task.id),
    doc_ids: state.pickedDocs.map((doc) => doc.id),
  };
}

export function buildUpdateMeetingPayload(
  state: Pick<
    MeetingEditState,
    'agenda' | 'attendees' | 'endAt' | 'startAt' | 'title'
  >,
): MeetingUpdateInput {
  return {
    title: state.title.trim(),
    agenda: state.agenda,
    start_at: localInputToIso(state.startAt),
    end_at: localInputToIso(state.endAt),
    attendees: state.attendees,
  };
}

export function isEndAfterStart(startAt: string, endAt: string): boolean {
  return new Date(endAt) > new Date(startAt);
}

export function fileChipKey(file: FileLike): string {
  return `${file.name}-${file.size}-${file.lastModified}`;
}

export function summarizeFileUploadResults<TFile extends FileLike>(
  pickedFiles: TFile[],
  uploadResults: FileUploadResult<TFile>[],
): { failures: string[]; remainingFiles: TFile[] } {
  const failures: string[] = [];
  const succeededFileKeys = new Set<string>();
  for (const result of uploadResults) {
    if (result.failure) {
      failures.push(result.failure);
    } else {
      succeededFileKeys.add(fileChipKey(result.file));
    }
  }

  return {
    failures,
    remainingFiles: pickedFiles.filter(
      (file) => !succeededFileKeys.has(fileChipKey(file)),
    ),
  };
}
