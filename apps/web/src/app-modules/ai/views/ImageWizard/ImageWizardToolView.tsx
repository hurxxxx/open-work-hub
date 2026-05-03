import { useCallback, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  buildWorkspaceAppPath,
  resolveDefaultWorkspaceAppPath,
  resolveShellWorkspaceSlug,
} from '@/src/platform/workspaces/workspace-utils';
import { ImageWizardView } from './ImageWizardView';
import { ImageWizardGalleryView } from './ImageWizardGalleryView';

export function ImageWizardToolView() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const workspaceSlug = useMemo(
    () =>
      searchParams.get('workspace')
      || resolveShellWorkspaceSlug(user, null)
      || '',
    [searchParams, user],
  );

  const view = searchParams.get('view') === 'gallery' ? 'gallery' : 'wizard';
  const generationId = searchParams.get('gen');

  const newWizardHref = useMemo(() => {
    const params = new URLSearchParams();
    if (workspaceSlug) params.set('workspace', workspaceSlug);
    return `/tool/image-wizard${params.toString() ? `?${params.toString()}` : ''}`;
  }, [workspaceSlug]);

  const buildDetailHref = useCallback(
    (gen: string) => {
      const params = new URLSearchParams();
      if (workspaceSlug) params.set('workspace', workspaceSlug);
      params.set('gen', gen);
      return `/tool/image-wizard?${params.toString()}`;
    },
    [workspaceSlug],
  );

  const handleGenerationCreated = useCallback(
    (id: string) => {
      const params = new URLSearchParams(searchParams);
      params.set('gen', id);
      setSearchParams(params, { replace: true });
    },
    [searchParams, setSearchParams],
  );

  if (!workspaceSlug) {
    const fallback =
      resolveDefaultWorkspaceAppPath(user, 'ai')
      || buildWorkspaceAppPath(resolveShellWorkspaceSlug(user, null) ?? '', 'ai');
    if (fallback) {
      navigate(fallback, { replace: true });
    }
    return null;
  }

  if (view === 'gallery') {
    return (
      <div className="px-6 py-6">
        <ImageWizardGalleryView
          workspaceSlug={workspaceSlug}
          newWizardHref={newWizardHref}
          buildDetailHref={buildDetailHref}
          onChanged={() => {
            // No-op; the gallery refetches on mount.
          }}
        />
      </div>
    );
  }

  return (
    <div className="px-6 py-6">
      <ImageWizardView
        workspaceSlug={workspaceSlug}
        generationId={generationId}
        onGenerationCreated={handleGenerationCreated}
      />
    </div>
  );
}

export default ImageWizardToolView;
