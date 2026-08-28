import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import { RefreshCw, Search } from 'lucide-react';

import {
  Select,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Tooltip,
  useFeedback,
} from '@open-work-hub/ui';

import { useWorkspaceBootstrapContext } from '@/src/platform/workspaces/workspace-bootstrap-context';

import {
  listCompanyAppControls,
  listWorkspaceAppDefaults,
  listWorkspaceAppOverrides,
  listWorkspaces,
  updateCompanyAppControls,
  updateWorkspaceAppDefaults,
  updateWorkspaceAppOverrides,
  type CompanyAppControlItem,
  type WorkspaceAppDefaultItem,
  type WorkspaceAppOverrideItem,
  type WorkspaceItem,
} from './admin-api';
import { EmptyPanel, SectionMessage, getErrorMessage } from './admin-shared';

export type WorkspaceAppsTab = 'defaults' | 'overrides';
type WorkspaceAppOverrideValue = 'inherit' | 'enable' | 'disable';

export function resolveWorkspaceAppsTab(
  value: string | null,
): WorkspaceAppsTab {
  return value === 'overrides' ? 'overrides' : 'defaults';
}

function StatusPill({ active, label }: { active: boolean; label: string }) {
  return (
    <span
      className={`app-text-caption inline-flex h-5 items-center rounded-full border px-1.5 font-medium ${
        active
          ? 'border-app-success-border bg-app-success/10 text-app-success-text'
          : 'border-app-warning/20 bg-app-warning/10 text-app-warning-text dark:text-app-warning-text'
      }`}
    >
      {label}
    </span>
  );
}

function RefreshButton({
  disabled,
  label,
  onClick,
}: {
  disabled: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <Tooltip content={label}>
      <button
        aria-label={label}
        className="inline-flex size-8 shrink-0 items-center justify-center rounded-md border border-app-border text-app-ink transition-colors hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-50"
        disabled={disabled}
        onClick={onClick}
        type="button"
      >
        <RefreshCw size={14} />
      </button>
    </Tooltip>
  );
}

function AppIdentity({
  app,
}: {
  app: { app_id: string; title: string; route_base: string };
}) {
  const { t } = useTranslation('shell');
  return (
    <div className="min-w-0">
      <div className="flex min-w-0 items-baseline gap-2">
        <span className="app-text-body-sm truncate font-medium text-app-ink">
          {t(`apps.${app.app_id}`, { defaultValue: app.title })}
        </span>
        <span className="app-text-caption shrink-0 text-app-ink/50">
          {app.app_id}
        </span>
      </div>
      <div className="app-text-caption truncate font-mono text-app-ink/45">
        {app.route_base}
      </div>
    </div>
  );
}

function WorkspaceMeta({ workspace }: { workspace: WorkspaceItem }) {
  const { t } = useTranslation('apps');
  return (
    <div className="app-text-caption flex min-w-0 items-center gap-1 text-app-ink/50">
      <span className="truncate">{workspace.key}</span>
      <span aria-hidden="true">·</span>
      <span className="shrink-0">
        {t('admin.console.workspaces.memberCount', {
          count: workspace.member_count,
        })}
      </span>
    </div>
  );
}

function TableEmpty({ loading }: { loading: boolean }) {
  const { t } = useTranslation('apps');
  return (
    <EmptyPanel
      description={t(
        loading
          ? 'admin.console.apps.controls.loadingDescription'
          : 'admin.console.apps.controls.emptyDescription',
      )}
      title={t(
        loading
          ? 'admin.console.apps.controls.loadingTitle'
          : 'admin.console.apps.controls.emptyTitle',
      )}
    />
  );
}

function CompanyControlsTable({
  items,
  loading,
  onToggle,
  savingAppId,
}: {
  items: CompanyAppControlItem[];
  loading: boolean;
  onToggle: (item: CompanyAppControlItem, enabled: boolean) => void;
  savingAppId: string | null;
}) {
  const { t } = useTranslation('apps');
  if (items.length === 0) return <TableEmpty loading={loading} />;
  return (
    <div className="max-h-[68vh] overflow-auto border border-app-border">
      <table className="w-full min-w-[800px] table-fixed border-collapse">
        <thead className="sticky top-0 z-10 bg-app-surface-sidebar shadow-[0_1px_0_var(--color-app-border)]">
          <tr>
            <th className="app-text-overline w-[36%] border-b border-app-border px-3 py-2 text-left text-app-ink/55">
              {t('admin.console.apps.controls.columns.app')}
            </th>
            <th className="app-text-overline w-[140px] border-b border-app-border px-3 py-2 text-left text-app-ink/55">
              {t('admin.console.apps.controls.columns.context')}
            </th>
            <th className="app-text-overline w-[130px] border-b border-app-border px-3 py-2 text-left text-app-ink/55">
              {t('admin.console.apps.controls.columns.scope')}
            </th>
            <th className="app-text-overline w-[130px] border-b border-app-border px-3 py-2 text-left text-app-ink/55">
              {t('admin.console.apps.controls.columns.effective')}
            </th>
            <th className="app-text-overline w-[84px] border-b border-app-border px-3 py-2 text-right text-app-ink/55">
              {t('admin.console.apps.controls.columns.company')}
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((app) => (
            <tr className="hover:bg-app-surface-hover/40" key={app.app_id}>
              <td className="border-b border-app-border px-3 py-2">
                <AppIdentity app={app} />
              </td>
              <td className="border-b border-app-border px-3 py-2">
                {t(
                  `admin.console.apps.controls.context.${app.execution_context_kind}`,
                )}
              </td>
              <td className="border-b border-app-border px-3 py-2">
                {t(
                  `admin.console.apps.controls.scope.${app.availability_scope}`,
                )}
              </td>
              <td className="border-b border-app-border px-3 py-2">
                <StatusPill
                  active={app.runtime_enabled}
                  label={t(
                    app.runtime_enabled
                      ? 'admin.console.apps.controls.enabled'
                      : 'admin.console.apps.controls.disabled',
                  )}
                />
              </td>
              <td className="border-b border-app-border px-3 py-2 text-right">
                <input
                  aria-label={t('admin.console.apps.controls.companyToggle', {
                    app: app.title,
                  })}
                  checked={app.enabled}
                  className="accent-app-accent"
                  disabled={savingAppId === app.app_id}
                  onChange={(event) => onToggle(app, event.target.checked)}
                  type="checkbox"
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function WorkspaceDefaultsTable({
  items,
  loading,
  onToggle,
  savingAppId,
}: {
  items: WorkspaceAppDefaultItem[];
  loading: boolean;
  onToggle: (item: WorkspaceAppDefaultItem, enabled: boolean) => void;
  savingAppId: string | null;
}) {
  const { t } = useTranslation('apps');
  if (items.length === 0) return <TableEmpty loading={loading} />;
  return (
    <div className="max-h-[68vh] overflow-auto border border-app-border">
      <table className="w-full min-w-[760px] table-fixed border-collapse">
        <thead className="sticky top-0 z-10 bg-app-surface-sidebar shadow-[0_1px_0_var(--color-app-border)]">
          <tr>
            <th className="app-text-overline w-[42%] border-b border-app-border px-3 py-2 text-left text-app-ink/55">
              {t('admin.console.apps.controls.columns.app')}
            </th>
            <th className="app-text-overline w-[130px] border-b border-app-border px-3 py-2 text-left text-app-ink/55">
              {t('admin.console.apps.controls.columns.company')}
            </th>
            <th className="app-text-overline w-[130px] border-b border-app-border px-3 py-2 text-left text-app-ink/55">
              {t('admin.console.apps.controls.columns.effective')}
            </th>
            <th className="app-text-overline w-[130px] border-b border-app-border px-3 py-2 text-right text-app-ink/55">
              {t('admin.console.apps.controls.columns.default')}
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((app) => (
            <tr className="hover:bg-app-surface-hover/40" key={app.app_id}>
              <td className="border-b border-app-border px-3 py-2">
                <AppIdentity app={app} />
              </td>
              <td className="border-b border-app-border px-3 py-2">
                <StatusPill
                  active={app.company_enabled}
                  label={t(
                    app.company_enabled
                      ? 'admin.console.apps.controls.enabled'
                      : 'admin.console.apps.controls.disabled',
                  )}
                />
              </td>
              <td className="border-b border-app-border px-3 py-2">
                <StatusPill
                  active={app.runtime_enabled}
                  label={t(
                    app.runtime_enabled
                      ? 'admin.console.apps.controls.enabled'
                      : 'admin.console.apps.controls.disabled',
                  )}
                />
              </td>
              <td className="border-b border-app-border px-3 py-2 text-right">
                <input
                  aria-label={t('admin.console.apps.controls.defaultToggle', {
                    app: app.title,
                  })}
                  checked={app.enabled}
                  className="accent-app-accent"
                  disabled={savingAppId === app.app_id}
                  onChange={(event) => onToggle(app, event.target.checked)}
                  type="checkbox"
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function WorkspaceOverridesTable({
  items,
  loading,
  onChange,
  savingAppId,
}: {
  items: WorkspaceAppOverrideItem[];
  loading: boolean;
  onChange: (
    item: WorkspaceAppOverrideItem,
    value: WorkspaceAppOverrideValue,
  ) => void;
  savingAppId: string | null;
}) {
  const { t } = useTranslation('apps');
  const options = useMemo(
    () => [
      {
        label: t('admin.console.apps.controls.override.inherit'),
        value: 'inherit',
      },
      {
        label: t('admin.console.apps.controls.override.enable'),
        value: 'enable',
      },
      {
        label: t('admin.console.apps.controls.override.disable'),
        value: 'disable',
      },
    ],
    [t],
  );
  if (items.length === 0) return <TableEmpty loading={loading} />;
  return (
    <div className="max-h-[68vh] overflow-auto border border-app-border">
      <table className="w-full min-w-[850px] table-fixed border-collapse">
        <thead className="sticky top-0 z-10 bg-app-surface-sidebar shadow-[0_1px_0_var(--color-app-border)]">
          <tr>
            <th className="app-text-overline w-[38%] border-b border-app-border px-3 py-2 text-left text-app-ink/55">
              {t('admin.console.apps.controls.columns.app')}
            </th>
            <th className="app-text-overline w-[120px] border-b border-app-border px-3 py-2 text-left text-app-ink/55">
              {t('admin.console.apps.controls.columns.company')}
            </th>
            <th className="app-text-overline w-[120px] border-b border-app-border px-3 py-2 text-left text-app-ink/55">
              {t('admin.console.apps.controls.columns.default')}
            </th>
            <th className="app-text-overline w-[120px] border-b border-app-border px-3 py-2 text-left text-app-ink/55">
              {t('admin.console.apps.controls.columns.effective')}
            </th>
            <th className="app-text-overline w-[180px] border-b border-app-border px-3 py-2 text-right text-app-ink/55">
              {t('admin.console.apps.controls.columns.override')}
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((app) => {
            const value: WorkspaceAppOverrideValue =
              app.override_enabled == null
                ? 'inherit'
                : app.override_enabled
                  ? 'enable'
                  : 'disable';
            return (
              <tr className="hover:bg-app-surface-hover/40" key={app.app_id}>
                <td className="border-b border-app-border px-3 py-2">
                  <AppIdentity app={app} />
                </td>
                <td className="border-b border-app-border px-3 py-2">
                  <StatusPill
                    active={app.company_enabled}
                    label={t(
                      app.company_enabled
                        ? 'admin.console.apps.controls.enabled'
                        : 'admin.console.apps.controls.disabled',
                    )}
                  />
                </td>
                <td className="border-b border-app-border px-3 py-2">
                  <StatusPill
                    active={app.default_enabled}
                    label={t(
                      app.default_enabled
                        ? 'admin.console.apps.controls.enabled'
                        : 'admin.console.apps.controls.disabled',
                    )}
                  />
                </td>
                <td className="border-b border-app-border px-3 py-2">
                  <StatusPill
                    active={app.effective_enabled}
                    label={t(
                      app.effective_enabled
                        ? 'admin.console.apps.controls.enabled'
                        : 'admin.console.apps.controls.disabled',
                    )}
                  />
                </td>
                <td className="border-b border-app-border px-3 py-2 text-right">
                  <Select
                    ariaLabel={t('admin.console.apps.controls.overrideSelect', {
                      app: app.title,
                    })}
                    disabled={savingAppId === app.app_id}
                    onValueChange={(nextValue) =>
                      onChange(app, nextValue as WorkspaceAppOverrideValue)
                    }
                    options={options}
                    value={value}
                  />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function AppControlsSection({
  page,
  token,
}: {
  page: 'platform' | 'workspace';
  token: string;
}) {
  const { t } = useTranslation('apps');
  const toast = useFeedback();
  const [searchParams, setSearchParams] = useSearchParams();
  const workspaceTab = resolveWorkspaceAppsTab(searchParams.get('tab'));
  const { reload, reloadGlobalApps } = useWorkspaceBootstrapContext();
  const [companyItems, setCompanyItems] = useState<CompanyAppControlItem[]>([]);
  const [defaultItems, setDefaultItems] = useState<WorkspaceAppDefaultItem[]>(
    [],
  );
  const [overrideItems, setOverrideItems] = useState<
    WorkspaceAppOverrideItem[]
  >([]);
  const [workspaces, setWorkspaces] = useState<WorkspaceItem[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState('');
  const [workspaceQuery, setWorkspaceQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [overrideLoading, setOverrideLoading] = useState(false);
  const [savingAppId, setSavingAppId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refreshShell = useCallback(() => {
    reload();
    reloadGlobalApps?.();
  }, [reload, reloadGlobalApps]);

  const loadPrimary = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      if (page === 'platform') {
        setCompanyItems((await listCompanyAppControls(token)).items);
      } else if (workspaceTab === 'defaults') {
        setDefaultItems((await listWorkspaceAppDefaults(token)).items);
      } else {
        const response = await listWorkspaces(token);
        setWorkspaces(response);
        setSelectedWorkspaceId((current) =>
          current && response.some((workspace) => workspace.id === current)
            ? current
            : (response[0]?.id ?? ''),
        );
      }
    } catch (caughtError) {
      setError(
        getErrorMessage(
          caughtError,
          t('admin.console.apps.controls.loadFailed'),
        ),
      );
    } finally {
      setLoading(false);
    }
  }, [page, t, token, workspaceTab]);

  useEffect(() => {
    void loadPrimary();
  }, [loadPrimary]);

  const loadOverrides = useCallback(async () => {
    if (!selectedWorkspaceId) {
      setOverrideItems([]);
      return;
    }
    setOverrideLoading(true);
    setError(null);
    try {
      setOverrideItems(
        (await listWorkspaceAppOverrides(token, selectedWorkspaceId)).items,
      );
    } catch (caughtError) {
      setError(
        getErrorMessage(
          caughtError,
          t('admin.console.apps.controls.loadFailed'),
        ),
      );
    } finally {
      setOverrideLoading(false);
    }
  }, [selectedWorkspaceId, t, token]);

  useEffect(() => {
    if (page === 'workspace' && workspaceTab === 'overrides') {
      void loadOverrides();
    }
  }, [loadOverrides, page, workspaceTab]);

  const selectedWorkspace = useMemo(
    () =>
      workspaces.find((workspace) => workspace.id === selectedWorkspaceId) ??
      null,
    [selectedWorkspaceId, workspaces],
  );
  const filteredWorkspaces = useMemo(() => {
    const query = workspaceQuery.trim().toLocaleLowerCase();
    if (!query) return workspaces;
    return workspaces.filter(
      (workspace) =>
        workspace.name.toLocaleLowerCase().includes(query) ||
        workspace.key.toLocaleLowerCase().includes(query),
    );
  }, [workspaceQuery, workspaces]);

  const updateCompany = useCallback(
    async (app: CompanyAppControlItem, enabled: boolean) => {
      setSavingAppId(app.app_id);
      setError(null);
      try {
        setCompanyItems(
          (
            await updateCompanyAppControls(token, {
              items: [{ app_id: app.app_id, enabled }],
            })
          ).items,
        );
        refreshShell();
        toast.success(t('admin.console.apps.controls.saved'));
      } catch (caughtError) {
        setError(
          getErrorMessage(
            caughtError,
            t('admin.console.apps.controls.saveFailed'),
          ),
        );
      } finally {
        setSavingAppId(null);
      }
    },
    [refreshShell, t, toast, token],
  );

  const updateDefault = useCallback(
    async (app: WorkspaceAppDefaultItem, enabled: boolean) => {
      setSavingAppId(app.app_id);
      setError(null);
      try {
        setDefaultItems(
          (
            await updateWorkspaceAppDefaults(token, {
              items: [{ app_id: app.app_id, enabled }],
            })
          ).items,
        );
        refreshShell();
        toast.success(t('admin.console.apps.controls.saved'));
      } catch (caughtError) {
        setError(
          getErrorMessage(
            caughtError,
            t('admin.console.apps.controls.saveFailed'),
          ),
        );
      } finally {
        setSavingAppId(null);
      }
    },
    [refreshShell, t, toast, token],
  );

  const updateOverride = useCallback(
    async (app: WorkspaceAppOverrideItem, value: WorkspaceAppOverrideValue) => {
      if (!selectedWorkspaceId) return;
      const enabled = value === 'inherit' ? null : value === 'enable';
      setSavingAppId(app.app_id);
      setError(null);
      try {
        setOverrideItems(
          (
            await updateWorkspaceAppOverrides(token, selectedWorkspaceId, {
              items: [{ app_id: app.app_id, enabled }],
            })
          ).items,
        );
        refreshShell();
        toast.success(t('admin.console.apps.controls.saved'));
      } catch (caughtError) {
        setError(
          getErrorMessage(
            caughtError,
            t('admin.console.apps.controls.saveFailed'),
          ),
        );
      } finally {
        setSavingAppId(null);
      }
    },
    [refreshShell, selectedWorkspaceId, t, toast, token],
  );

  const sectionHeader = (
    title: string,
    description: string,
    onRefresh: () => void,
  ) => (
    <div className="flex flex-col gap-2 border-b border-app-border pb-2 lg:flex-row lg:items-center lg:justify-between">
      <div className="min-w-0">
        <h2 className="app-text-control text-app-ink">{title}</h2>
        <p className="app-text-caption mt-0.5 max-w-3xl text-app-ink/55">
          {description}
        </p>
      </div>
      <RefreshButton
        disabled={loading || overrideLoading}
        label={t('admin.console.apps.controls.refresh')}
        onClick={onRefresh}
      />
    </div>
  );

  return (
    <div className="space-y-3">
      <SectionMessage error={error} message={null} />
      {page === 'platform' ? (
        <section className="space-y-2">
          {sectionHeader(
            t('admin.console.apps.controls.companyTitle'),
            t('admin.console.apps.controls.companyDescription'),
            () => void loadPrimary(),
          )}
          <CompanyControlsTable
            items={companyItems}
            loading={loading}
            onToggle={(app, enabled) => void updateCompany(app, enabled)}
            savingAppId={savingAppId}
          />
        </section>
      ) : (
        <Tabs
          onValueChange={(value) => {
            const next = new URLSearchParams(searchParams);
            next.set('tab', resolveWorkspaceAppsTab(value));
            setSearchParams(next);
          }}
          value={workspaceTab}
        >
          <div className="flex border-b border-app-border pb-2">
            <TabsList>
              <TabsTrigger value="defaults">
                {t('admin.console.apps.controls.defaultsTab')}
              </TabsTrigger>
              <TabsTrigger value="overrides">
                {t('admin.console.apps.controls.overridesTab')}
              </TabsTrigger>
            </TabsList>
          </div>
          <TabsContent className="space-y-2" value="defaults">
            {sectionHeader(
              t('admin.console.apps.controls.defaultsTitle'),
              t('admin.console.apps.controls.defaultsDescription'),
              () => void loadPrimary(),
            )}
            <WorkspaceDefaultsTable
              items={defaultItems}
              loading={loading}
              onToggle={(app, enabled) => void updateDefault(app, enabled)}
              savingAppId={savingAppId}
            />
          </TabsContent>
          <TabsContent className="space-y-2" value="overrides">
            {sectionHeader(
              t('admin.console.apps.controls.overridesTitle'),
              t('admin.console.apps.controls.overridesDescription'),
              () => void loadPrimary(),
            )}
            <div className="grid gap-3 lg:grid-cols-[260px_1fr]">
              <aside className="overflow-hidden rounded-md border border-app-border bg-app-bg">
                <div className="border-b border-app-border px-3 py-2">
                  <div className="flex items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-2 py-1">
                    <Search className="text-app-ink/50" size={12} />
                    <input
                      aria-label={t(
                        'admin.console.apps.controls.workspaceSearch',
                      )}
                      className="app-text-body-sm min-w-0 flex-1 bg-transparent text-app-ink outline-none placeholder:text-app-ink/40"
                      onChange={(event) =>
                        setWorkspaceQuery(event.target.value)
                      }
                      placeholder={t(
                        'admin.console.apps.controls.workspaceSearch',
                      )}
                      value={workspaceQuery}
                    />
                  </div>
                </div>
                <div className="max-h-[520px] overflow-y-auto py-1">
                  {filteredWorkspaces.map((workspace) => (
                    <button
                      className={`relative flex w-full items-center gap-2 px-3 py-1.5 text-left transition-colors ${
                        workspace.id === selectedWorkspaceId
                          ? 'bg-app-accent/10 text-app-ink'
                          : 'text-app-ink/85 hover:bg-app-surface-sidebar'
                      }`}
                      key={workspace.id}
                      onClick={() => setSelectedWorkspaceId(workspace.id)}
                      type="button"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="app-text-body-sm truncate font-medium text-app-ink">
                          {workspace.name}
                        </div>
                        <WorkspaceMeta workspace={workspace} />
                      </div>
                    </button>
                  ))}
                  {!loading && filteredWorkspaces.length === 0 ? (
                    <p className="app-text-body-sm px-3 py-8 text-center text-app-ink/45">
                      {t('admin.console.apps.controls.workspaceEmpty')}
                    </p>
                  ) : null}
                </div>
              </aside>
              <div className="min-w-0 space-y-2">
                <div className="flex min-h-12 items-center justify-between gap-3 rounded-md border border-app-border bg-app-bg px-3 py-2">
                  <div className="min-w-0">
                    <h3 className="app-text-control truncate text-app-ink">
                      {selectedWorkspace?.name ??
                        t('admin.console.apps.controls.workspaceEmpty')}
                    </h3>
                    {selectedWorkspace ? (
                      <WorkspaceMeta workspace={selectedWorkspace} />
                    ) : null}
                  </div>
                  <RefreshButton
                    disabled={!selectedWorkspaceId || overrideLoading}
                    label={t('admin.console.apps.controls.refresh')}
                    onClick={() => void loadOverrides()}
                  />
                </div>
                <WorkspaceOverridesTable
                  items={overrideItems}
                  loading={overrideLoading}
                  onChange={(app, value) => void updateOverride(app, value)}
                  savingAppId={savingAppId}
                />
              </div>
            </div>
          </TabsContent>
        </Tabs>
      )}
    </div>
  );
}
