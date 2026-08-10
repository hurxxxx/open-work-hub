import { InlineNotice } from '@open-alm/ui';

import { FormDialog } from '@/src/components/form/FormDialog';
import type { MeetingDetail } from '../../api/meeting-api';

import { MeetingFormFields } from './MeetingFormFields';
import { useMeetingEditFormWorkflow } from './meeting-form-workflow';

interface MeetingEditModalProps {
  isOpen: boolean;
  meeting: MeetingDetail;
  onClose: () => void;
  onSaved: (updated: MeetingDetail) => void;
  workspaceSlug: string;
}

export function MeetingEditModal({
  isOpen,
  meeting,
  onClose,
  onSaved,
  workspaceSlug,
}: MeetingEditModalProps) {
  const { state, projection, t, user, actions } = useMeetingEditFormWorkflow({
    isOpen,
    meeting,
    onSaved,
    workspaceSlug,
  });
  const {
    agenda,
    endAt,
    error,
    startAt,
    submitting,
    title,
    userQuery,
    userQueryFocused,
    usersLoading,
  } = state;
  const {
    availabilityUsers,
    canSubmit,
    filteredUsers,
    lockedOrganizerIds,
    userLookup,
    visibleAttendees,
  } = projection;

  return (
    <FormDialog
      cancelLabel={t('common:actions.cancel')}
      closeLabel={t('common:actions.close')}
      open={isOpen}
      onCancel={onClose}
      onPrimary={() => void actions.submit()}
      title={t('meeting.editMeeting.title')}
      description={t('meeting.editMeeting.description')}
      maxWidth="max-w-xl"
      dismissOnInteractOutside={false}
      primaryDisabled={!canSubmit}
      primaryLabel={t('meeting.editMeeting.saveChanges')}
      primaryPendingLabel={t('meeting.editMeeting.saving')}
      submitting={submitting}
    >
      <div className="space-y-5 text-app-ink">
        {error ? (
          <InlineNotice role="alert" tone="warning">
            {error}
          </InlineNotice>
        ) : null}

        <MeetingFormFields
          actions={{
            addAttendee: actions.addAttendee,
            patch: actions.patch,
            removeAttendee: actions.removeAttendee,
          }}
          labels={{
            agenda: t('meeting.form.agenda'),
            agendaPlaceholder: t('meeting.form.agendaPlaceholder'),
            attendees: t('meeting.form.attendees'),
            autoIncluded:
              user?.id === meeting.organizer_id
                ? t('meeting.form.attendeeAutoIncluded')
                : '',
            end: t('meeting.form.end'),
            lockedLabel: t('meeting.form.organizer'),
            noUserMatch: t('meeting.form.noUserMatch'),
            optional: t('meeting.form.optional'),
            removeItem: (name) => t('meeting.form.removeItem', { name }),
            searchPlaceholder: t('meeting.form.searchUsersPlaceholder'),
            searchPrompt: t('meeting.form.searchUsersPrompt'),
            searching: t('meeting.form.searchingUsers'),
            start: t('meeting.form.start'),
            title: t('meeting.form.title'),
          }}
          projection={{
            availabilityUsers,
            filteredUsers,
            lockedUserIds: lockedOrganizerIds,
            userLookup,
            visibleAttendees,
          }}
          state={{
            agenda,
            endAt,
            startAt,
            title,
            userQuery,
            userQueryFocused,
            usersLoading,
          }}
          timeZone={user?.time_zone}
          workspaceSlug={workspaceSlug}
        />
      </div>
    </FormDialog>
  );
}
