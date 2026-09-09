import { InlineNotice } from '@open-work-hub/ui';
import { useRef, type ChangeEvent } from 'react';

import { FormDialog } from '@/src/components/form/FormDialog';
import { DocPickerModal } from './DocPickerModal';
import { MeetingCreateLinkedWorkSection } from './MeetingCreateLinkedWorkSection';
import { MeetingFormFields } from './MeetingFormFields';
import { TaskPickerModal } from './TaskPickerModal';
import { formatFileSize } from './meeting-form-model';
import { useMeetingCreateFormWorkflow } from './meeting-form-workflow';

export type { PickedDoc, PickedTask } from './meeting-form-model';

export interface MeetingCreateModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreated: (meetingId: string) => void;

  /** Pre-fill start/end when opened from a calendar slot selection. */
  initialRange?: { start: Date; end: Date; allDay: boolean } | null;
}

export function MeetingCreateModal({
  isOpen,
  onClose,
  onCreated,
  initialRange,
}: MeetingCreateModalProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const { state, projection, t, user, actions } = useMeetingCreateFormWorkflow({
    isOpen,
    onCreated,
    initialRange,
  });
  const {
    agenda,
    createdMeetingId,
    docPickerOpen,
    endAt,
    error,
    partialFailures,
    pickedDocs,
    pickedFiles,
    pickedTasks,
    startAt,
    submitting,
    taskPickerOpen,
    title,
    userQuery,
    userQueryFocused,
    usersLoading,
  } = state;
  const {
    availabilityUsers,
    canSubmit,
    filteredUsers,
    pickedDocIds,
    pickedTaskIds,
    userLookup,
    visibleAttendees,
  } = projection;

  function handleFileInputChange(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    event.target.value = '';
    actions.addFiles(files);
  }

  return (
    <FormDialog
      cancelLabel={
        createdMeetingId
          ? t('common:actions.close')
          : t('common:actions.cancel')
      }
      closeLabel={t('common:actions.close')}
      open={isOpen}
      onCancel={onClose}
      onPrimary={
        createdMeetingId
          ? actions.openCreatedMeeting
          : () => void actions.submit()
      }
      title={t('meeting.create.title')}
      description={t('meeting.create.description')}
      maxWidth="max-w-xl"
      dismissOnInteractOutside={false}
      primaryDisabled={createdMeetingId ? false : !canSubmit}
      primaryLabel={
        createdMeetingId
          ? t('meeting.create.openCreated')
          : t('meeting.create.createButton')
      }
      primaryPendingLabel={t('meeting.create.creating')}
      submitting={createdMeetingId ? false : submitting}
    >
      <div className="space-y-5 text-app-ink">
        <p className="app-text-caption text-app-ink/60">
          {t('meeting.companyContentNotice')}
        </p>
        {error ? (
          <InlineNotice role="alert" tone="warning">
            <p>{error}</p>
            {partialFailures.length > 0 ? (
              <ul className="mt-2 list-disc space-y-0.5 pl-5 text-[var(--ui-color-warning)]/90">
                {partialFailures.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            ) : null}
          </InlineNotice>
        ) : null}

        <MeetingCreateLinkedWorkSection
          fileInputRef={fileInputRef}
          formatFileSize={formatFileSize}
          handlers={{
            onFileInputChange: handleFileInputChange,
            onOpenDocPicker: () => actions.patch({ docPickerOpen: true }),
            onOpenTaskPicker: () => actions.patch({ taskPickerOpen: true }),
            onRemoveDoc: actions.removePickedDoc,
            onRemoveFile: actions.removePickedFile,
            onRemoveTask: actions.removePickedTask,
          }}
          labels={{
            addDoc: t('meeting.attachments.addDoc'),
            addFile: t('meeting.attachments.addFile'),
            addTask: t('meeting.attachments.addTask'),
            description: t('meeting.form.linkedWorkDescription'),
            removeItem: (name) => t('meeting.form.removeItem', { name }),
            title: t('meeting.form.linkedWork'),
          }}
          state={{ pickedDocs, pickedFiles, pickedTasks }}
        />

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
            autoIncluded: t('meeting.form.attendeeAutoIncluded'),
            end: t('meeting.form.end'),
            noUserMatch: t('meeting.form.noUserMatch'),
            optional: t('meeting.form.optional'),
            removeItem: (name) => t('meeting.form.removeItem', { name }),
            searchPlaceholder: t('meeting.form.searchUsersPlaceholder'),
            searchPrompt: t('meeting.form.searchUsersPrompt'),
            searching: t('meeting.form.searchingUsers'),
            start: t('meeting.form.start'),
            title: t('meeting.form.title'),
            titlePlaceholder: t('meeting.form.titlePlaceholder'),
          }}
          projection={{
            availabilityUsers,
            filteredUsers,
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
        />
      </div>

      <TaskPickerModal
        isOpen={taskPickerOpen}
        onClose={() => actions.patch({ taskPickerOpen: false })}
        excludeTaskIds={pickedTaskIds}
        onPick={(task) => {
          actions.pickTask({
            id: task.id,
            title: task.title,
            reference: task.reference,
          });
        }}
      />
      <DocPickerModal
        isOpen={docPickerOpen}
        onClose={() => actions.patch({ docPickerOpen: false })}
        excludeDocIds={pickedDocIds}
        onPick={(doc) => {
          actions.pickDoc({ id: doc.source_id, title: doc.title });
        }}
      />
    </FormDialog>
  );
}
