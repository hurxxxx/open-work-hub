import { useCallback, useEffect, useMemo, useReducer } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import { InlineNotice } from '@open-alm/ui';

import { useAuth } from '@/src/platform/auth/auth-provider';
import { AccessDeniedView } from '@/src/platform/auth/settings-pages';
import { listWorkspaces } from '@/src/platform/admin/admin-api';
import { getErrorMessage } from '@/src/platform/admin/admin-shared';
import { WorkspaceDetailPanel } from '@/src/platform/admin/workspace-detail-panel';
import {
  INITIAL_WORKSPACE_SETTINGS_STATE,
  buildWorkspaceDetailCapabilities,
  buildWorkspaceSettingsTitle,
  canManageWorkspaceSettings,
  selectCurrentWorkspaceSummary,
  shouldLoadWorkspaceSettings,
  workspaceSettingsReducer,
} from './workspace-settings-model';

export function WorkspaceSettingsView() {
  const { t } = useTranslation('apps');
  const { workspaceSlug } = useParams();
  const { token, user, hasPermission } = useAuth();
  const [state, dispatch] = useReducer(
    workspaceSettingsReducer,
    INITIAL_WORKSPACE_SETTINGS_STATE,
  );

  const currentWorkspaceSummary = useMemo(
    () => selectCurrentWorkspaceSummary(user?.workspaces, workspaceSlug),
    [user?.workspaces, workspaceSlug],
  );
  const canManageWorkspace = canManageWorkspaceSettings(
    user,
    workspaceSlug,
    currentWorkspaceSummary,
  );
  const canBrowseDirectory = hasPermission('user.read');
  const workspaceTitle = buildWorkspaceSettingsTitle({
    workspace: state.workspace,
    summary: currentWorkspaceSummary,
    workspaceSlug,
  });
  const workspaceDetailCapabilities = buildWorkspaceDetailCapabilities({
    canBrowseDirectory,
  });

  const flashSuccess = useCallback((text: string) => {
    dispatch({ type: 'flash-success', message: text });
    window.setTimeout(() => dispatch({ type: 'clear-message' }), 3500);
  }, []);

  const flashError = useCallback((text: string) => {
    dispatch({ type: 'flash-error', error: text });
  }, []);

  useEffect(() => {
    const loadParams = { token, workspaceSlug, canManageWorkspace };
    if (!shouldLoadWorkspaceSettings(loadParams)) {
      dispatch({ type: 'load-skipped' });
      return;
    }
    let cancelled = false;
    dispatch({ type: 'load-started' });
    void (async () => {
      try {
        const workspaceItems = await listWorkspaces(loadParams.token, {
          includeArchived: true,
        });
        if (cancelled) return;
        const next =
          workspaceItems.find(
            (item) => item.key === loadParams.workspaceSlug,
          ) ?? null;
        dispatch({ type: 'load-succeeded', workspace: next });
      } catch (caughtError) {
        if (!cancelled) {
          dispatch({
            type: 'load-failed',
            error: getErrorMessage(
              caughtError,
              t('workspace.settingsLoadFailed'),
            ),
          });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, workspaceSlug, canManageWorkspace, t]);

  if (!workspaceSlug) {
    return (
      <AccessDeniedView description={t('workspace.settingsAccessDenied')} />
    );
  }

  if (!canManageWorkspace) {
    return (
      <AccessDeniedView description={t('workspace.settingsAdminRequired')} />
    );
  }

  return (
    <div className="custom-scrollbar h-full overflow-y-auto p-8">
      <div className="mx-auto max-w-6xl space-y-6">
        <header className="space-y-2 border-b border-app-border pb-6">
          <div className="app-text-overline text-app-ink/50">
            {t('workspace.settingsTitle')}
          </div>
          <h1 className="app-text-title-lg text-app-ink">{workspaceTitle}</h1>
          <p className="app-text-body text-app-ink/60">
            {t('workspace.settingsDescription')}
          </p>
        </header>

        {state.error ? (
          <InlineNotice tone="danger">{state.error}</InlineNotice>
        ) : null}
        {state.message ? (
          <InlineNotice tone="success">{state.message}</InlineNotice>
        ) : null}
        {state.loading ? (
          <InlineNotice tone="info">
            {t('workspace.settingsLoading')}
          </InlineNotice>
        ) : null}

        <section className="flex min-h-[560px] flex-col overflow-hidden rounded-md border border-app-border bg-app-bg">
          <WorkspaceDetailPanel
            workspace={state.workspace}
            token={token ?? ''}
            currentUserId={user?.id ?? ''}
            capabilities={workspaceDetailCapabilities}
            onWorkspaceChanged={(workspace) =>
              dispatch({ type: 'workspace-changed', workspace })
            }
            flashSuccess={flashSuccess}
            flashError={flashError}
          />
        </section>
      </div>
    </div>
  );
}
