import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { InlineNotice } from '@aidoo/ui';

import { useAuth } from '@/src/domains/auth/auth-provider';
import { workspaceRoleAllows } from '@/src/domains/auth/auth-api';
import { AccessDeniedView } from '@/src/domains/auth/settings-pages';
import {
  listGroups,
  listWorkspaces,
  type AccessGroupItem,
  type WorkspaceItem,
} from '@/src/domains/admin/admin-api';
import { getErrorMessage } from '@/src/domains/admin/admin-shared';
import { WorkspaceDetailPanel } from '@/src/domains/admin/workspace-detail-panel';

export function WorkspaceSettingsView() {
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
  const canManageWorkspace = workspaceRoleAllows(currentWorkspaceSummary?.role, 'admin');
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
          setError(getErrorMessage(caughtError, '워크스페이스 설정을 불러오지 못했습니다.'));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, workspaceSlug, canManageWorkspace, canReadGroups]);

  if (!workspaceSlug || !currentWorkspaceSummary) {
    return <AccessDeniedView description="현재 계정은 이 workspace 설정에 접근할 수 없습니다." />;
  }

  if (!canManageWorkspace) {
    return <AccessDeniedView description="이 workspace 설정은 admin 이상만 접근할 수 있습니다." />;
  }

  return (
    <div className="custom-scrollbar h-full overflow-y-auto p-8">
      <div className="mx-auto max-w-6xl space-y-6">
        <header className="space-y-2 border-b border-app-border pb-6">
          <div className="app-text-overline text-app-ink/50">Workspace Settings</div>
          <div className="flex items-center justify-between gap-4">
            <div>
              <h1 className="app-text-title-lg text-app-ink">
                {workspace?.name ?? currentWorkspaceSummary.name}
              </h1>
              <p className="app-text-body mt-1 text-app-ink/60">
                이 협업 공간의 프로필, enabled apps, 멤버십을 관리합니다.
              </p>
            </div>
            <div className="rounded-lg border border-app-border bg-app-surface-sidebar px-3 py-2 text-right">
              <div className="app-text-caption text-app-ink/50">Your role</div>
              <div className="app-text-body-sm text-app-ink">{currentWorkspaceSummary.role}</div>
            </div>
          </div>
        </header>

        {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}
        {message ? <InlineNotice tone="success">{message}</InlineNotice> : null}
        {loading ? (
          <InlineNotice tone="info">Workspace settings 를 불러오는 중입니다.</InlineNotice>
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
              canManageApps: true,
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
