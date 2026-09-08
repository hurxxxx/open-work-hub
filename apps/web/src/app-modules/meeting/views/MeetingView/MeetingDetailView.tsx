// Route shell for /apps/meeting/meetings/{meetingId}.
// All actual rendering lives in MeetingDetailLayout so the same two-pane
// layout (notes editor + MeetingDetail sidebar) can also be hosted inside
// the calendar's MeetingPreviewModal.
import { Navigate, useNavigate, useParams } from 'react-router-dom';

import { buildAppPath } from '@/src/platform/apps/app-links';

import { MeetingDetailLayout } from './MeetingDetailLayout';

export function MeetingDetailView() {
  const navigate = useNavigate();
  const { meetingId } = useParams();

  if (!meetingId) {
    return <Navigate replace to="/" />;
  }

  const meetingsRoot = buildAppPath('meeting');

  return (
    <MeetingDetailLayout
      meetingId={meetingId}
      backHref={meetingsRoot}
      onDeleted={() => navigate(meetingsRoot, { replace: true })}
    />
  );
}
