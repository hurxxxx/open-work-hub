import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import { InlineNotice } from '@ai-do/ui';

import { useAuth } from '@/src/platform/auth/auth-provider';
import { hasWorkspaceAdminAccess, workspaceRoleAllows } from '@/src/platform/auth/auth-api';
import { AccessDeniedView } from '@/src/platform/auth/settings-pages';
import {
  listGroups,
  listWorkspaces,
  type AccessGroupItem,
  type WorkspaceItem,
} from '@/src/platform/admin/admin-api';
import { getErrorMessage } from '@/src/platform/admin/admin-shared';
import { WorkspaceDetailPanel } from '@/src/platform/admin/workspace-detail-panel';

export function WorkspaceSettingsView() {
  const { t } = useTranslation('apps');
  const { workspaceSlug } = useParams();
  const { token, user, hasPermission } = useAuth();
  const [workspace, setWorkspace] = useState<WorkspaceItem | null>(null);
  const [groups, setGroups] = useState<AccessGroupItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const currentWorkspaceSummary = useMemo(
    () => user?.workspaces.find((item) => item.slug === workspaceSlug) ?? null,
    [user?.workspaces, workspaceSlug],
  );
  const canManageWorkspace = hasWorkspaceAdminAccess(user, workspaceSlug)
    || workspaceRoleAllows(currentWorkspaceSummary?.role, 'admin');
  const canReadGroups = hasPermission('group.read');
  const canBrowseDirectory = hasPermission('user.read');

  const flashSuccess = useCallback((text: string) => {
    setError(null);
    setMessage(text);
    window.setTimeout(() => setMessage(null), 3500);
  }, []);

  const flashError = useCallback((text: string) => {
    setMessage(null);
    setError(text);
  }, []);

  useEffect(() => {
    if (!token || !workspaceSlug || !canManageWorkspace) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    void (async () => {
      try {
        const [workspaceItems, groupItems] = await Promise.all([
          listWorkspaces(token, { includeArchived: true }),
          canReadGroups ? listGroups(token) : Promise.resolve([]),
        ]);
        if (cancelled) return;
        const next = workspaceItems.find((item) => item.key === workspaceSlug) ?? null;
        setWorkspace(next);
        setGroups(groupItems);
      } catch (caughtError) {
        if (!cancelled) {
          setError(getErrorMessage(caughtError, t('workspace.settingsLoadFailed')));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, workspaceSlug, canManageWorkspace, canReadGroups, t]);

  if (!workspaceSlug) {
    return <AccessDeniedView description={t('workspace.settingsAccessDenied')} />;
  }

  if (!canManageWorkspace) {
    return <AccessDeniedView description={t('workspace.settingsAdminRequired')} />;
  }

  return (
    <div className="custom-scrollbar h-full overflow-y-auto p-8">
      <div className="mx-auto max-w-6xl space-y-6">
        <header className="space-y-2 border-b border-app-border pb-6">
          <div className="app-text-overline text-app-ink/50">{t('workspace.settingsTitle')}</div>
          <h1 className="app-text-title-lg text-app-ink">
            {workspace?.name ?? currentWorkspaceSummary?.name ?? workspaceSlug}
          </h1>
          <p className="app-text-body text-app-ink/60">
            {t('workspace.settingsDescription')}
          </p>
        </header>

        {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}
        {message ? <InlineNotice tone="success">{message}</InlineNotice> : null}
        {loading ? (
          <InlineNotice tone="info">{t('workspace.settingsLoading')}</InlineNotice>
        ) : null}

        <section className="flex min-h-[560px] flex-col overflow-hidden rounded-md border border-app-border bg-app-bg">
          <WorkspaceDetailPanel
            workspace={workspace}
            token={token ?? ''}
            currentUserId={user?.id ?? ''}
            groups={groups}
            canReadGroups={canReadGroups}
            capabilities={{
              canEditProfile: true,
              canManageMembers: true,
              canArchive: false,
              canDelete: false,
              canBrowseDirectory,
            }}
            onWorkspaceChanged={setWorkspace}
            flashSuccess={flashSuccess}
            flashError={flashError}
          />
        </section>
      </div>
    </div>
  );
}
