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
  workspaceSlug: workspaceSlugProp,
}: {
  spaceId: string;
  spaceName?: string | null;
  whiteboardId?: string | null;
  workspaceSlug?: string | null;
}) => {
  const navigate = useNavigate();
  const { workspaceSlug: routeWorkspaceSlug } = useParams();
  const { user } = useAuth();
  const workspaceSlug = workspaceSlugProp ?? routeWorkspaceSlug ?? null;

  useEffect(() => {
    navigate(
      resolveSpaceWhiteboardsRedirectPath({
        spaceId,
        user,
        whiteboardId,
        workspaceSlug,
      }),
      { replace: true },
    );
  }, [navigate, spaceId, user, whiteboardId, workspaceSlug]);

  return null;
};

type WorkspaceUser = Parameters<typeof resolveDefaultWorkspaceAppPath>[0];

export function resolveSpaceWhiteboardsRedirectPath({
  spaceId,
  user,
  whiteboardId,
  workspaceSlug,
}: {
  spaceId: string;
  user: WorkspaceUser;
  whiteboardId?: string | null;
  workspaceSlug: string | null;
}): string {
  const search = new URLSearchParams({ space_id: spaceId });
  const suffix = whiteboardId
    ? `/${whiteboardId}?${search}`
    : `?view=all&${search}`;
  return workspaceSlug
    ? buildWorkspaceAppPath(workspaceSlug, 'whiteboard', suffix)
    : resolveDefaultWorkspaceAppPath(user, 'whiteboard', suffix);
}
