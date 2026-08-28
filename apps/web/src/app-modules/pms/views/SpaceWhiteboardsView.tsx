import { useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  buildAppEntryHref,
  buildAppHref,
} from '@open-work-hub/contracts/app-routes';

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
  const workspaceSlug = workspaceSlugProp ?? routeWorkspaceSlug ?? null;

  useEffect(() => {
    navigate(
      resolveSpaceWhiteboardsRedirectPath({
        spaceId,
        whiteboardId,
        workspaceSlug,
      }),
      { replace: true },
    );
  }, [navigate, spaceId, whiteboardId, workspaceSlug]);

  return null;
};

export function resolveSpaceWhiteboardsRedirectPath({
  spaceId,
  whiteboardId,
  workspaceSlug,
}: {
  spaceId: string;
  whiteboardId?: string | null;
  workspaceSlug: string | null;
}): string {
  if (!workspaceSlug) return buildAppEntryHref('whiteboard');
  return whiteboardId
    ? buildAppHref({
        routeId: 'whiteboard.board',
        workspaceSlug,
        pathParams: { whiteboardId },
        queryParams: { space_id: spaceId },
      })
    : buildAppHref({
        routeId: 'whiteboard.root',
        workspaceSlug,
        queryParams: { space_id: spaceId, view: 'all' },
      });
}
