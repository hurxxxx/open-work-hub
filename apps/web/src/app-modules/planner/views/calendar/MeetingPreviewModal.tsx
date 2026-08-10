// Full meeting modal for calendar event clicks. Hosts the same two-pane
// `<MeetingWorkspaceLayout/>` that the dedicated meeting page route uses,
// so the user gets ALL meeting features inside the modal:
//   - collaborative notes editor (회의록)
//   - MeetingDetail sidebar (status / edit / delete / tasks / docs / recordings /
//     transcription / attendees)
//
// The modal stays mounted on the calendar — the user can deep-edit the meeting
// + notes without losing their place. `embedded` mode on the @ai-do/ui Dialog
// suppresses the built-in header / padding / scroll wrapper so the layout's
// own chrome fills the surface cleanly.
import { Dialog } from '@ai-do/ui';
import { useTranslation } from 'react-i18next';

import { MeetingWorkspaceLayout } from '@/src/app-modules/meeting';

interface MeetingPreviewModalProps {
  contentClassName?: string;
  meetingId: string | null;
  workspaceSlug: string | undefined;
  onClose: () => void;
  /** Called after the meeting (or its notes) is changed so the calendar can refetch. */
  onChanged?: () => void;
  overlayClassName?: string;
}

export function MeetingPreviewModal({
  contentClassName,
  meetingId,
  workspaceSlug,
  onClose,
  onChanged,
  overlayClassName,
}: MeetingPreviewModalProps) {
  const { t } = useTranslation('apps');
  const open = meetingId !== null && Boolean(workspaceSlug);

  return (
    <Dialog
      closeLabel={t('common:actions.close')}
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
      title={t('planner.meetingPreviewTitle')}
      description={t('planner.meetingPreviewDescription')}
      fullSize
      embedded
      // Recording / form interactions inside MeetingWorkspaceLayout must not
      // be lost by an accidental backdrop click.
      dismissOnInteractOutside={false}
      contentClassName={contentClassName}
      overlayClassName={overlayClassName}
    >
      {meetingId && workspaceSlug ? (
        <MeetingWorkspaceLayout
          workspaceSlug={workspaceSlug}
          meetingId={meetingId}
          onClose={onClose}
          onChanged={onChanged}
          onDeleted={() => {
            onChanged?.();
            onClose();
          }}
        />
      ) : null}
    </Dialog>
  );
}
