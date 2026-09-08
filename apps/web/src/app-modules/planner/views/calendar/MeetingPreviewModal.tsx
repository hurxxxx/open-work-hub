// Full meeting modal for calendar event clicks. Hosts the same two-pane
// `<MeetingDetailLayout/>` that the dedicated meeting page route uses,
// so the user gets ALL meeting features inside the modal:
//   - collaborative notes editor (회의록)
//   - MeetingDetail sidebar (status / edit / delete / tasks / docs / recordings /
//     transcription / attendees)
//
// The modal stays mounted on the calendar — the user can deep-edit the meeting
// + notes without losing their place. `embedded` mode on the @open-work-hub/ui Dialog
// suppresses the built-in header / padding / scroll wrapper so the layout's
// own chrome fills the surface cleanly.
import { Dialog } from '@open-work-hub/ui';
import { useTranslation } from 'react-i18next';

import { MeetingDetailLayout } from '@/src/app-modules/meeting';

interface MeetingPreviewModalProps {
  contentClassName?: string;
  meetingId: string | null;

  onClose: () => void;
  /** Called after the meeting (or its notes) is changed so the calendar can refetch. */
  onChanged?: () => void;
  overlayClassName?: string;
}

export function MeetingPreviewModal({
  contentClassName,
  meetingId,
  onClose,
  onChanged,
  overlayClassName,
}: MeetingPreviewModalProps) {
  const { t } = useTranslation('apps');
  const open = meetingId !== null;

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
      // Recording / form interactions inside MeetingDetailLayout must not
      // be lost by an accidental backdrop click.
      dismissOnInteractOutside={false}
      contentClassName={contentClassName}
      overlayClassName={overlayClassName}
    >
      {meetingId ? (
        <MeetingDetailLayout
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
