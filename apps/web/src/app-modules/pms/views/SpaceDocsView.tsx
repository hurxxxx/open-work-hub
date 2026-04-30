import { useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  buildWorkspaceAppPath,
  resolveDefaultWorkspaceAppPath,
} from '@/src/platform/workspaces/workspace-utils';

export const SpaceDocsView = ({
  spaceId,
  docId,
}: {
  spaceId: string;
  spaceName?: string | null;
  docId?: string | null;
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
    const target = docId
      ? (workspaceSlug
        ? buildWorkspaceAppPath(workspaceSlug, 'docs', `/${docId}?${search}`)
        : resolveDefaultWorkspaceAppPath(user, 'docs', `/${docId}?${search}`))
      : (workspaceSlug
        ? buildWorkspaceAppPath(workspaceSlug, 'docs', `?view=all&${search}`)
        : resolveDefaultWorkspaceAppPath(user, 'docs', `?view=all&${search}`));
    navigate(target, { replace: true });
  }, [docId, navigate, spaceId, user, workspaceSlug]);

  return null;
};
