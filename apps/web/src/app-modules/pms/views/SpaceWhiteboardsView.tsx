import { buildAppHref } from '@open-work-hub/contracts/app-routes';
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

export const SpaceWhiteboardsView = ({
  spaceId,
  whiteboardId,
}: {
  spaceId: string;
  spaceName?: string | null;
  whiteboardId?: string | null;
}) => {
  const navigate = useNavigate();

  useEffect(() => {
    navigate(
      resolveSpaceWhiteboardsRedirectPath({
        spaceId,
        whiteboardId,
      }),
      { replace: true },
    );
  }, [navigate, spaceId, whiteboardId]);

  return null;
};

export function resolveSpaceWhiteboardsRedirectPath({
  spaceId,
  whiteboardId,
}: {
  spaceId: string;
  whiteboardId?: string | null;
}): string {
  return whiteboardId
    ? buildAppHref({
        routeId: 'whiteboard.board',
        pathParams: { whiteboardId },
        queryParams: { space_id: spaceId },
      })
    : buildAppHref({
        routeId: 'whiteboard.root',
        queryParams: { space_id: spaceId, view: 'all' },
      });
}
