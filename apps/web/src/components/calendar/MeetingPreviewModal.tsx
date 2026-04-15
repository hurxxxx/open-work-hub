// Full meeting modal for calendar event clicks. Hosts the same two-pane
// `<MeetingWorkspaceLayout/>` that the dedicated meeting page route uses,
// so the user gets ALL meeting features inside the modal:
//   - collaborative notes editor (회의록)
//   - MeetingDetail sidebar (status / edit / delete / tasks / docs / recordings /
//     transcription / attendees)
//
// The modal stays mounted on the calendar — the user can deep-edit the meeting
// + notes without losing their place. `embedded` mode on the @aidoo/ui Dialog
// suppresses the built-in header / padding / scroll wrapper so the layout's
// own chrome fills the surface cleanly.
import { Dialog } from '@aidoo/ui';

import { MeetingWorkspaceLayout } from '@/src/components/views/MeetingView/MeetingWorkspaceLayout';

interface MeetingPreviewModalProps {
  meetingId: string | null;
  workspaceSlug: string | undefined;
  onClose: () => void;
  /** Called after the meeting (or its notes) is changed so the calendar can refetch. */
  onChanged?: () => void;
}

export function MeetingPreviewModal({
  meetingId,
  workspaceSlug,
  onClose,
  onChanged,
}: MeetingPreviewModalProps) {
  const open = meetingId !== null && Boolean(workspaceSlug);

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
      title="회의 정보"
      description="캘린더에서 선택한 회의의 상세 정보입니다."
      fullSize
      embedded
      // Recording / form interactions inside MeetingWorkspaceLayout must not
      // be lost by an accidental backdrop click.
      dismissOnInteractOutside={false}
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
