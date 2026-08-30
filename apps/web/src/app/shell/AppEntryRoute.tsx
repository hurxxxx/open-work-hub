import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Navigate,
  useNavigate,
  useParams,
  useSearchParams,
} from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  APP_CONTRACT_BY_ID,
  type AppId,
} from '@open-work-hub/contracts/app-contracts';
import { buildAppHref } from '@open-work-hub/contracts/app-routes';

import { useAuth } from '@/src/platform/auth/auth-provider';
import { AccessDeniedView } from '@/src/platform/auth/settings-pages';
import {
  setAppWorkspacePreference,
  type AppsBootstrapResponse,
  type EligibleWorkspace,
} from '@/src/platform/workspaces/workspaces-api';
import {
  projectAppEntryQueryParams,
  resolveAppEntryDecision,
} from './app-entry-model';
import { useEligibleWorkspaceSearch } from './useEligibleWorkspaceSearch';

export function AppEntryRoute({
  bootstrap,
  error,
  loading,
  reload,
}: {
  bootstrap: AppsBootstrapResponse | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
}) {
  const { appId = '' } = useParams<{ appId: string }>();
  const { token, user } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { t } = useTranslation('shell');
  const app = bootstrap?.apps.find((item) => item.app_id === appId) ?? null;
  const entryDecision = useMemo(() => resolveAppEntryDecision(app), [app]);
  const [selectionError, setSelectionError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const attemptedSingleSelectionRef = useRef<string | null>(null);
  const staticContract = APP_CONTRACT_BY_ID.get(appId as AppId) ?? null;
  const workspaceUnavailableWithoutMembership = Boolean(
    staticContract?.availability_scope === 'workspace' &&
      user?.workspaces.length === 0,
  );

  const entryQueryParams = useMemo(
    () => projectAppEntryQueryParams(searchParams),
    [searchParams],
  );
  const workspaceSearch = useEligibleWorkspaceSearch({
    appId: app?.app_id ?? '',
    enabled: entryDecision.kind === 'choose-workspace',
    token,
  });

  const destination = useCallback(
    (workspace: EligibleWorkspace) => {
      const contract = app ? APP_CONTRACT_BY_ID.get(app.app_id as AppId) : null;
      if (!contract) {
        throw new Error(`Unknown app contract: ${app?.app_id ?? appId}`);
      }
      return buildAppHref({
        routeId: contract.entry_route_id,
        workspaceSlug: workspace.slug,
        queryParams: entryQueryParams,
      });
    },
    [app, appId, entryQueryParams],
  );

  useEffect(() => {
    const single =
      entryDecision.kind === 'workspace' && entryDecision.persistPreference
        ? entryDecision.workspace
        : null;
    const attemptKey = app && single ? `${app.app_id}:${single.id}` : null;
    if (
      !token ||
      !app ||
      !single ||
      saving ||
      attemptedSingleSelectionRef.current === attemptKey
    ) {
      return;
    }
    attemptedSingleSelectionRef.current = attemptKey;
    setSaving(true);
    setAppWorkspacePreference(token, app.app_id, single.id)
      .then(() => {
        reload();
        navigate(destination(single), { replace: true });
      })
      .catch((caught: unknown) =>
        setSelectionError(
          caught instanceof Error ? caught.message : String(caught),
        ),
      )
      .finally(() => setSaving(false));
  }, [app, destination, entryDecision, navigate, reload, saving, token]);

  if (workspaceUnavailableWithoutMembership) {
    return (
      <AccessDeniedView
        description={t('launcher.workspaceMembershipRequiredDescription')}
        title={t('launcher.workspaceMembershipRequiredTitle')}
      />
    );
  }
  if (loading && !bootstrap) {
    return (
      <div className="m-8 h-48 animate-pulse rounded-2xl bg-app-surface" />
    );
  }
  if (error) {
    return <p className="m-8 text-app-danger">{error}</p>;
  }
  if (
    staticContract?.availability_scope === 'workspace' &&
    (!app || entryDecision.kind === 'unavailable')
  ) {
    return <AccessDeniedView description={t('gates.workspaceAppDenied')} />;
  }
  if (entryDecision.kind === 'unavailable' || !app) {
    return (
      <p className="m-8 text-app-ink/60">{t('launcher.appUnavailable')}</p>
    );
  }
  if (entryDecision.kind === 'global') {
    return <Navigate replace to={entryDecision.href} />;
  }
  if (entryDecision.kind === 'workspace' && !entryDecision.persistPreference) {
    return <Navigate replace to={destination(entryDecision.workspace)} />;
  }
  if ((entryDecision.kind === 'workspace' && !selectionError) || saving) {
    return (
      <div className="m-8 h-48 animate-pulse rounded-2xl bg-app-surface" />
    );
  }

  const choose = async (workspace: EligibleWorkspace) => {
    if (!token || saving) return;
    setSaving(true);
    setSelectionError(null);
    try {
      await setAppWorkspacePreference(token, app.app_id, workspace.id);
      reload();
      navigate(destination(workspace), { replace: true });
    } catch (caught) {
      setSelectionError(
        caught instanceof Error ? caught.message : String(caught),
      );
      setSaving(false);
    }
  };

  return (
    <div className="mx-auto w-full max-w-2xl px-5 py-12">
      <h1 className="app-text-title-lg text-app-ink">
        {t('workspaceContext.chooseTitle', {
          app: t(`apps.${app.app_id}`, { defaultValue: app.title }),
        })}
      </h1>
      <p className="app-text-body mt-2 text-app-ink/60">
        {t('workspaceContext.chooseDescription')}
      </p>
      {selectionError ? (
        <p className="app-text-body mt-4 text-app-danger">{selectionError}</p>
      ) : null}
      <label className="mt-6 block">
        <span className="app-text-overline text-app-ink/55">
          {t('workspaceContext.searchLabel')}
        </span>
        <input
          className="app-text-body-sm mt-1.5 w-full rounded-xl border border-app-border bg-app-surface px-4 py-3 text-app-ink outline-none placeholder:text-app-ink/40 focus:border-app-accent"
          onChange={(event) =>
            workspaceSearch.setQuery(event.currentTarget.value)
          }
          placeholder={t('workspaceContext.searchPlaceholder')}
          type="search"
          value={workspaceSearch.query}
        />
      </label>
      {workspaceSearch.error ? (
        <div className="app-text-body mt-4 flex items-center justify-between gap-3 text-app-danger-text">
          <p>{t('workspaceContext.loadFailed')}</p>
          <button
            className="shrink-0 rounded-lg border border-app-danger/30 px-3 py-2 font-medium"
            disabled={workspaceSearch.loading}
            onClick={workspaceSearch.retry}
            type="button"
          >
            {t('workspaceContext.retry')}
          </button>
        </div>
      ) : null}
      <div className="mt-6 space-y-2">
        {(workspaceSearch.items.length > 0
          ? workspaceSearch.items
          : app.single_eligible_workspace
            ? [app.single_eligible_workspace]
            : []
        ).map((workspace) => (
          <button
            className="flex w-full items-center justify-between rounded-xl border border-app-border bg-app-surface px-4 py-3 text-left transition hover:border-app-accent/40"
            disabled={saving}
            key={workspace.id}
            onClick={() => void choose(workspace)}
            type="button"
          >
            <span>
              <span className="app-text-body-sm block font-semibold text-app-ink">
                {workspace.name}
              </span>
              <span className="app-text-caption block text-app-ink/50">
                {workspace.slug}
              </span>
            </span>
          </button>
        ))}
        {workspaceSearch.loading && workspaceSearch.items.length === 0 ? (
          <div className="h-24 animate-pulse rounded-xl bg-app-surface" />
        ) : null}
        {!workspaceSearch.loading &&
        !workspaceSearch.error &&
        workspaceSearch.items.length === 0 ? (
          <p className="app-text-body-sm py-6 text-center text-app-ink/55">
            {t('workspaceContext.noResults')}
          </p>
        ) : null}
        {workspaceSearch.hasMore ? (
          <button
            className="app-text-body-sm w-full rounded-xl border border-app-border bg-app-bg px-4 py-3 font-medium text-app-ink transition hover:border-app-accent/40"
            disabled={workspaceSearch.loading}
            onClick={() => void workspaceSearch.loadMore()}
            type="button"
          >
            {workspaceSearch.loading
              ? t('workspaceContext.loading')
              : t('workspaceContext.loadMore')}
          </button>
        ) : null}
      </div>
    </div>
  );
}
