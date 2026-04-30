// Route shell for /w/{workspaceSlug}/meeting/{meetingId}.
// All actual rendering lives in MeetingWorkspaceLayout so the same two-pane
// layout (notes editor + MeetingDetail sidebar) can also be hosted inside
// the calendar's MeetingPreviewModal.
import { Navigate, useNavigate, useParams } from 'react-router-dom';

import { buildWorkspaceAppPath } from '@/src/platform/workspaces/workspace-utils';

import { MeetingWorkspaceLayout } from './MeetingWorkspaceLayout';

export function MeetingWorkspaceView() {
  const navigate = useNavigate();
  const { workspaceSlug, meetingId } = useParams();

  if (!workspaceSlug || !meetingId) {
    return <Navigate replace to="/" />;
  }

  const meetingsRoot = buildWorkspaceAppPath(workspaceSlug, 'meeting');

  return (
    <MeetingWorkspaceLayout
      workspaceSlug={workspaceSlug}
      meetingId={meetingId}
      backHref={meetingsRoot}
      onDeleted={() => navigate(meetingsRoot, { replace: true })}
    />
  );
}
