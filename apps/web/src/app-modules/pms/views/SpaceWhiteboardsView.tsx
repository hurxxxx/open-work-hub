import { useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  buildWorkspaceAppPath,
  resolveDefaultWorkspaceAppPath,
} from '@/src/platform/workspaces/workspace-utils';

export const SpaceWhiteboardsView = ({
  spaceId,
  whiteboardId,
}: {
  spaceId: string;
  spaceName?: string | null;
  whiteboardId?: string | null;
}) => {
  const navigate = useNavigate();
  const { workspaceSlug } = useParams();
  const { user } = useAuth();

  useEffect(() => {
    const search = new URLSearchParams({
      container_app: 'pms',
      container_type: 'space',
      container_id: spaceId,
    });
    const target = whiteboardId
      ? (workspaceSlug
        ? buildWorkspaceAppPath(workspaceSlug, 'whiteboard', `/${whiteboardId}?${search}`)
        : resolveDefaultWorkspaceAppPath(user, 'whiteboard', `/${whiteboardId}?${search}`))
      : (workspaceSlug
        ? buildWorkspaceAppPath(workspaceSlug, 'whiteboard', `?view=all&${search}`)
        : resolveDefaultWorkspaceAppPath(user, 'whiteboard', `?view=all&${search}`));
    navigate(target, { replace: true });
  }, [navigate, spaceId, user, whiteboardId, workspaceSlug]);

  return null;
};
