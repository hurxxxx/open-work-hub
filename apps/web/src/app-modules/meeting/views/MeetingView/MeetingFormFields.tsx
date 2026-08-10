import { useId } from 'react';

import { DateTimeInput } from '@/src/components/date/DateInput';
import {
  FORM_FIELD_CONTROL_CLASS_NAME,
  FORM_TEXTAREA_CONTROL_CLASS_NAME,
  FormFieldRow,
} from '@/src/components/form/FormDialog';

import type { MeetingAttendeeInput, MeetingUser } from '../../api/meeting-api';

import { MeetingAvailabilityPanel } from './MeetingAvailabilityPanel';
import { MeetingCreateAttendeesSection } from './MeetingCreateAttendeesSection';

type MeetingFormFieldsState = {
  agenda: string;
  endAt: string;
  startAt: string;
  title: string;
  userQuery: string;
  userQueryFocused: boolean;
  usersLoading: boolean;
};

type MeetingFormFieldsProjection = {
  availabilityUsers: MeetingUser[];
  filteredUsers: MeetingUser[];
  lockedUserIds?: Set<string>;
  userLookup: Map<string, MeetingUser>;
  visibleAttendees: MeetingAttendeeInput[];
};

type MeetingFormFieldsLabels = {
  agenda: string;
  agendaPlaceholder: string;
  attendees: string;
  autoIncluded: string;
  end: string;
  lockedLabel?: string;
  noUserMatch: string;
  optional: string;
  removeItem: (name: string) => string;
  searchPlaceholder: string;
  searchPrompt: string;
  searching: string;
  start: string;
  title: string;
  titlePlaceholder?: string;
};

type MeetingFormFieldsActions = {
  addAttendee: (user: MeetingUser) => void;
  patch: (patch: Partial<MeetingFormFieldsState>) => void;
  removeAttendee: (userId: string) => void;
};

type MeetingFormFieldsProps = {
  actions: MeetingFormFieldsActions;
  labels: MeetingFormFieldsLabels;
  projection: MeetingFormFieldsProjection;
  state: MeetingFormFieldsState;
  timeZone?: string | null;
  workspaceSlug: string;
};

export function MeetingFormFields({
  actions,
  labels,
  projection,
  state,
  timeZone,
  workspaceSlug,
}: MeetingFormFieldsProps) {
  const titleInputId = useId();
  const startInputId = useId();
  const endInputId = useId();
  const agendaInputId = useId();

  return (
    <>
      <FormFieldRow htmlFor={titleInputId} label={labels.title} required>
        <input
          id={titleInputId}
          type="text"
          value={state.title}
          aria-label={labels.title}
          onChange={(event) => actions.patch({ title: event.target.value })}
          placeholder={labels.titlePlaceholder}
          maxLength={200}
          className={FORM_FIELD_CONTROL_CLASS_NAME}
        />
      </FormFieldRow>

      <div className="grid grid-cols-2 gap-3">
        <FormFieldRow htmlFor={startInputId} label={labels.start}>
          <DateTimeInput
            id={startInputId}
            value={state.startAt}
            aria-label={labels.start}
            onValueChange={(value) => actions.patch({ startAt: value })}
            className={FORM_FIELD_CONTROL_CLASS_NAME}
          />
        </FormFieldRow>
        <FormFieldRow htmlFor={endInputId} label={labels.end}>
          <DateTimeInput
            id={endInputId}
            value={state.endAt}
            aria-label={labels.end}
            onValueChange={(value) => actions.patch({ endAt: value })}
            className={FORM_FIELD_CONTROL_CLASS_NAME}
          />
        </FormFieldRow>
      </div>

      <MeetingAvailabilityPanel
        workspaceSlug={workspaceSlug}
        attendeeUsers={projection.availabilityUsers}
        meetingStart={state.startAt ? new Date(state.startAt) : null}
        meetingEnd={state.endAt ? new Date(state.endAt) : null}
        timeZone={timeZone}
      />

      <MeetingCreateAttendeesSection
        handlers={{
          onAddAttendee: actions.addAttendee,
          onQueryChange: (query) => actions.patch({ userQuery: query }),
          onQueryFocusChange: (focused) =>
            actions.patch({ userQueryFocused: focused }),
          onRemoveAttendee: actions.removeAttendee,
        }}
        labels={{
          attendees: labels.attendees,
          autoIncluded: labels.autoIncluded,
          noUserMatch: labels.noUserMatch,
          removeItem: labels.removeItem,
          searchPlaceholder: labels.searchPlaceholder,
          searchPrompt: labels.searchPrompt,
          searching: labels.searching,
        }}
        state={{
          filteredUsers: projection.filteredUsers,
          lockedLabel: labels.lockedLabel,
          lockedUserIds: projection.lockedUserIds,
          userLookup: projection.userLookup,
          userQuery: state.userQuery,
          userQueryFocused: state.userQueryFocused,
          usersLoading: state.usersLoading,
          visibleAttendees: projection.visibleAttendees,
        }}
      />

      <FormFieldRow
        htmlFor={agendaInputId}
        label={labels.agenda}
        optionalLabel={labels.optional}
      >
        <textarea
          id={agendaInputId}
          value={state.agenda}
          aria-label={labels.agenda}
          onChange={(event) => actions.patch({ agenda: event.target.value })}
          rows={4}
          placeholder={labels.agendaPlaceholder}
          className={FORM_TEXTAREA_CONTROL_CLASS_NAME}
        />
      </FormFieldRow>
    </>
  );
}
