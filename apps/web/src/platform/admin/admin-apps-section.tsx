import { Fragment, useCallback, useEffect, useMemo, useState } from 'react';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import {
  ArrowDown,
  ArrowRight,
  ArrowUp,
  Plus,
  RefreshCw,
  Save,
  Search,
  Trash2,
  X,
} from 'lucide-react';

import {
  Button,
  DropdownMenu,
  SearchField,
  Select,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Tooltip,
  useToast,
} from '@ai-do/ui';

import { IconPickerDialog } from '@/src/components/picker/IconPickerDialog';
import type { IconPickerGroup } from '@/src/components/picker/icon-picker-model';
import {
  WORKSPACE_APP_ICON_KEYS,
  WORKSPACE_APP_ICON_PICKER_GROUPS,
  workspaceAppIconForKey,
} from '@/src/platform/workspaces/workspace-app-icons';
import { useWorkspaceBootstrapContext } from '@/src/platform/workspaces/workspace-bootstrap-context';

import {
  createAdminAppBarCategory,
  deleteAdminAppBarCategory,
  listAdminAppBarCategories,
  listPlatformAppVisibility,
  listWorkspaceAppVisibility,
  listWorkspaces,
  updateAdminAppBarCategoryLayout,
  updatePlatformAppVisibility,
  updateWorkspaceAppVisibility,
  type AdminAppBarCategoriesResponse,
  type AdminAppBarCategory,
  type AdminAppBarCategoryAppItem,
  type PlatformAppVisibilityItem,
  type WorkspaceAppVisibilityItem,
  type WorkspaceItem,
} from './admin-api';
import {
  buildAppVisibilityGroups,
  partitionAppVisibilityItems,
  PERSONAL_TOOLS_APP_VISIBILITY_GROUP_ID,
  UNCATEGORIZED_APP_VISIBILITY_GROUP_ID,
  type AppVisibilityGroup,
  type AppVisibilityGroupableItem,
} from './admin-app-visibility-groups';
import {
  EmptyPanel,
  FORM_FIELD_CLASS as fieldClassName,
  SectionMessage,
  getErrorMessage,
} from './admin-shared';

export type AdminAppsPage = 'app-bar' | 'platform' | 'workspace';
export type WorkspaceAppsTab = 'defaults' | 'overrides';
type WorkspaceAppVisibilityOverrideValue = 'inherit' | 'show' | 'hide';

export function resolveWorkspaceAppsTab(
  value: string | null,
): WorkspaceAppsTab {
  return value === 'overrides' ? 'overrides' : 'defaults';
}

function WorkspaceListItemMeta({
  className = '',
  t,
  workspace,
}: {
  className?: string;
  t: TFunction;
  workspace: Pick<WorkspaceItem, 'key' | 'member_count'>;
}) {
  const memberCountLabel = t('admin.console.workspaces.memberCount', {
    count: workspace.member_count,
  });
  return (
    <div
      className={`app-text-caption flex min-w-0 items-center gap-1 text-app-ink/50 ${className}`}
      title={`${workspace.key} · ${memberCountLabel}`}
    >
      <span className="min-w-0 truncate">{workspace.key}</span>
      <span aria-hidden="true" className="shrink-0 text-app-ink/35">
        ·
      </span>
      <span className="shrink-0 whitespace-nowrap">{memberCountLabel}</span>
    </div>
  );
}
function appVisibilityPillClass(active: boolean): string {
  return active
    ? 'border-app-success-border bg-app-success/10 text-app-success dark:text-app-success-text'
    : 'border-app-warning/20 bg-app-warning/10 text-app-warning-text dark:text-app-warning-text';
}

function AppVisibilityPill({
  active,
  label,
}: {
  active: boolean;
  label: string;
}) {
  return (
    <span
      className={`app-text-caption inline-flex h-5 items-center rounded-full border px-1.5 font-medium ${appVisibilityPillClass(
        active,
      )}`}
    >
      {label}
    </span>
  );
}

function appVisibilityGroupTitle<T extends AppVisibilityGroupableItem>(
  group: AppVisibilityGroup<T>,
  t: TFunction,
): string {
  if (group.title) return group.title;
  if (group.id === UNCATEGORIZED_APP_VISIBILITY_GROUP_ID) {
    return t('admin.console.apps.uncategorizedGroup');
  }
  if (group.id === PERSONAL_TOOLS_APP_VISIBILITY_GROUP_ID) {
    return t('admin.console.apps.personalToolsGroup');
  }
  return t(`shell:apps.${group.id}`, { defaultValue: group.id });
}

function AppVisibilityIdentity({
  app,
  appTitle,
}: {
  app: AppVisibilityGroupableItem;
  appTitle: string;
}) {
  return (
    <div className="flex min-w-0 items-baseline gap-2">
      <div className="app-text-body-sm truncate font-medium text-app-ink">
        {appTitle}
      </div>
      <div className="app-text-caption shrink-0 text-app-ink/55">
        {app.app_id}
      </div>
    </div>
  );
}

function AppVisibilityGroupRow({
  colSpan,
  count,
  groupId,
  title,
  t,
}: {
  colSpan: number;
  count: number;
  groupId: string | null;
  title: string;
  t: TFunction;
}) {
  return (
    <tr className="bg-app-surface-sidebar">
      <td
        className="border-b border-app-border px-2 py-1.5 align-middle"
        colSpan={colSpan}
      >
        <div className="flex min-w-0 items-center justify-between gap-3">
          <div className="flex min-w-0 items-baseline gap-2">
            <div className="app-text-body-sm truncate font-semibold text-app-ink">
              {title}
            </div>
            {groupId ? (
              <div className="app-text-caption shrink-0 text-app-ink/45">
                {groupId}
              </div>
            ) : null}
          </div>
          <span className="app-text-caption shrink-0 text-app-ink/50">
            {t('admin.console.apps.groupCount', { count })}
          </span>
        </div>
      </td>
    </tr>
  );
}

function PlatformVisibleWorkspaceMenu({
  app,
  appTitle,
  t,
}: {
  app: PlatformAppVisibilityItem;
  appTitle: string;
  t: TFunction;
}) {
  const workspaces = app.visible_workspaces ?? [];
  const workspaceList =
    workspaces.length > 0
      ? workspaces.map((workspace) => `${workspace.name} (${workspace.key})`)
      : [t('admin.console.apps.visibleWorkspaceEmpty')];
  return (
    <DropdownMenu
      align="end"
      contentClassName="max-h-[320px] overflow-y-auto"
      items={
        workspaces.length > 0
          ? workspaces.map((workspace) => ({
              disabled: true,
              id: workspace.id,
              label: (
                <div className="min-w-0">
                  <div className="truncate font-medium">{workspace.name}</div>
                  <div className="truncate text-app-ink/50">
                    {workspace.key}
                  </div>
                </div>
              ),
            }))
          : [
              {
                disabled: true,
                id: 'empty',
                label: t('admin.console.apps.visibleWorkspaceEmpty'),
              },
            ]
      }
      side="bottom"
      trigger={
        <button
          aria-label={t('admin.console.apps.visibleWorkspaceListLabel', {
            app: appTitle,
          })}
          className="app-text-caption inline-flex h-6 min-w-12 items-center justify-center rounded-md border border-app-border bg-app-bg px-2 text-app-ink/70 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
          title={workspaceList.join('\n')}
          type="button"
        >
          {t('admin.console.apps.visibleWorkspaceCount', {
            count: app.visible_workspace_count ?? workspaces.length,
          })}
        </button>
      }
    />
  );
}

function PlatformAppVisibilityGroups({
  appDisplayName,
  groups,
  itemsLength,
  loading,
  onToggle,
  platformScopeLabel,
  savingAppId,
  scopeColumnLabel,
  t,
}: {
  appDisplayName: (app: AppVisibilityGroupableItem) => string;
  groups: AppVisibilityGroup<PlatformAppVisibilityItem>[];
  itemsLength: number;
  loading: boolean;
  onToggle: (app: PlatformAppVisibilityItem, visible: boolean) => void;
  platformScopeLabel?: string;
  savingAppId: string | null;
  scopeColumnLabel?: string;
  t: TFunction;
}) {
  if (loading && itemsLength === 0) {
    return (
      <EmptyPanel
        description={t('admin.console.apps.loadingDescription')}
        title={t('admin.console.apps.loadingTitle')}
      />
    );
  }

  if (itemsLength === 0) {
    return (
      <EmptyPanel
        description={t('admin.console.apps.emptyDescription')}
        title={t('admin.console.apps.emptyTitle')}
      />
    );
  }

  return (
    <div className="max-h-[68vh] overflow-auto border border-app-border">
      <table className="w-full min-w-[840px] table-fixed border-collapse">
        <thead className="sticky top-0 z-10 bg-app-surface-sidebar shadow-[0_1px_0_var(--color-app-border)]">
          <tr className="bg-app-surface-sidebar">
            <th className="app-text-overline w-[28%] border-b border-app-border px-2 py-1 text-left text-app-ink/55">
              {t('admin.console.apps.columns.app')}
            </th>
            <th className="app-text-overline w-[22%] border-b border-app-border px-2 py-1 text-left text-app-ink/55">
              {t('admin.console.apps.columns.route')}
            </th>
            <th className="app-text-overline w-[96px] border-b border-app-border px-2 py-1 text-left text-app-ink/55">
              {t('admin.console.apps.columns.status')}
            </th>
            <th className="app-text-overline w-[116px] border-b border-app-border px-2 py-1 text-left text-app-ink/55">
              {t('admin.console.apps.runtime')}
            </th>
            <th className="app-text-overline w-[132px] border-b border-app-border px-2 py-1 text-left text-app-ink/55">
              {scopeColumnLabel ?? t('admin.console.apps.columns.workspaces')}
            </th>
            <th className="app-text-overline w-[64px] border-b border-app-border px-2 py-1 text-right text-app-ink/55">
              {t('admin.console.apps.columns.visibility')}
            </th>
          </tr>
        </thead>
        <tbody>
          {groups.map((group) => (
            <Fragment key={group.id}>
              <AppVisibilityGroupRow
                colSpan={6}
                count={group.rows.length}
                groupId={
                  group.title ||
                  group.id === UNCATEGORIZED_APP_VISIBILITY_GROUP_ID ||
                  group.id === PERSONAL_TOOLS_APP_VISIBILITY_GROUP_ID
                    ? null
                    : group.id
                }
                title={appVisibilityGroupTitle(group, t)}
                t={t}
              />
              {group.rows.map((app) => {
                const appTitle = appDisplayName(app);
                const saving = savingAppId === app.app_id;
                return (
                  <tr
                    className="transition-colors hover:bg-app-surface-hover/40"
                    key={app.app_id}
                  >
                    <td className="border-b border-app-border px-2 py-1 align-middle">
                      <AppVisibilityIdentity app={app} appTitle={appTitle} />
                    </td>
                    <td className="app-text-caption border-b border-app-border px-2 py-1 align-middle font-mono text-app-ink/55">
                      <span className="block truncate">{app.route_base}</span>
                    </td>
                    <td className="border-b border-app-border px-2 py-1 align-middle">
                      <AppVisibilityPill
                        active={app.visible}
                        label={
                          app.visible
                            ? t('admin.console.apps.visible')
                            : t('admin.console.apps.hidden')
                        }
                      />
                    </td>
                    <td className="border-b border-app-border px-2 py-1 align-middle">
                      <AppVisibilityPill
                        active={app.runtime_enabled}
                        label={
                          app.runtime_enabled
                            ? t('admin.console.apps.runtimeEnabled')
                            : t('admin.console.apps.runtimeDisabled')
                        }
                      />
                    </td>
                    <td className="border-b border-app-border px-2 py-1 align-middle">
                      {app.availability_scope === 'platform' ? (
                        <AppVisibilityPill
                          active={app.visible}
                          label={
                            platformScopeLabel ??
                            t('admin.console.apps.platformTab')
                          }
                        />
                      ) : (
                        <PlatformVisibleWorkspaceMenu
                          app={app}
                          appTitle={appTitle}
                          t={t}
                        />
                      )}
                    </td>
                    <td className="border-b border-app-border px-2 py-1 text-right align-middle">
                      <label className="inline-flex h-5 items-center justify-end text-app-ink/55">
                        <input
                          aria-label={t('admin.console.apps.toggleLabel', {
                            app: appTitle,
                          })}
                          checked={app.visible}
                          className="accent-app-accent"
                          disabled={saving}
                          onChange={(event) =>
                            onToggle(app, event.target.checked)
                          }
                          type="checkbox"
                        />
                      </label>
                    </td>
                  </tr>
                );
              })}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function WorkspaceAppVisibilityGroups({
  appDisplayName,
  groups,
  loading,
  onOverrideChange,
  overrideOptions,
  savingWorkspaceAppId,
  t,
  workspacesLength,
  workspaceItemsLength,
}: {
  appDisplayName: (app: AppVisibilityGroupableItem) => string;
  groups: AppVisibilityGroup<WorkspaceAppVisibilityItem>[];
  loading: boolean;
  onOverrideChange: (
    app: WorkspaceAppVisibilityItem,
    value: WorkspaceAppVisibilityOverrideValue,
  ) => void;
  overrideOptions: Array<{
    label: string;
    value: WorkspaceAppVisibilityOverrideValue;
  }>;
  savingWorkspaceAppId: string | null;
  t: TFunction;
  workspacesLength: number;
  workspaceItemsLength: number;
}) {
  if (loading && workspaceItemsLength === 0) {
    return (
      <EmptyPanel
        description={t('admin.console.apps.loadingDescription')}
        title={t('admin.console.apps.workspaceLoadingTitle')}
      />
    );
  }

  if (workspacesLength === 0) {
    return (
      <EmptyPanel
        description={t('admin.console.apps.workspaceEmptyDescription')}
        title={t('admin.console.apps.workspaceEmptyTitle')}
      />
    );
  }

  if (workspaceItemsLength === 0) {
    return (
      <EmptyPanel
        description={t('admin.console.apps.emptyDescription')}
        title={t('admin.console.apps.emptyTitle')}
      />
    );
  }

  return (
    <div className="max-h-[68vh] overflow-auto">
      <table className="w-full min-w-[820px] table-fixed border-collapse">
        <thead className="sticky top-0 z-10 bg-app-surface-sidebar shadow-[0_1px_0_var(--color-app-border)]">
          <tr className="bg-app-surface-sidebar">
            <th className="app-text-overline w-[28%] border-b border-app-border px-2 py-1 text-left text-app-ink/55">
              {t('admin.console.apps.columns.app')}
            </th>
            <th className="app-text-overline w-[120px] border-b border-app-border px-2 py-1 text-left text-app-ink/55">
              {t('admin.console.apps.platformDefault')}
            </th>
            <th className="app-text-overline w-[120px] border-b border-app-border px-2 py-1 text-left text-app-ink/55">
              {t('admin.console.apps.effective')}
            </th>
            <th className="app-text-overline w-[116px] border-b border-app-border px-2 py-1 text-left text-app-ink/55">
              {t('admin.console.apps.runtime')}
            </th>
            <th className="app-text-overline w-[190px] border-b border-app-border px-2 py-1 text-right text-app-ink/55">
              {t('admin.console.apps.workspaceOverride')}
            </th>
          </tr>
        </thead>
        <tbody>
          {groups.map((group) => (
            <Fragment key={group.id}>
              <AppVisibilityGroupRow
                colSpan={5}
                count={group.rows.length}
                groupId={group.title ? null : group.id}
                title={appVisibilityGroupTitle(group, t)}
                t={t}
              />
              {group.rows.map((app) => {
                const appTitle = appDisplayName(app);
                const overrideValue: WorkspaceAppVisibilityOverrideValue =
                  app.visibility_override == null
                    ? 'inherit'
                    : app.visibility_override
                      ? 'show'
                      : 'hide';
                const saving = savingWorkspaceAppId === app.app_id;
                return (
                  <tr
                    className="transition-colors hover:bg-app-surface-hover/40"
                    key={app.app_id}
                  >
                    <td className="border-b border-app-border px-2 py-1 align-middle">
                      <AppVisibilityIdentity app={app} appTitle={appTitle} />
                    </td>
                    <td className="border-b border-app-border px-2 py-1 align-middle">
                      <AppVisibilityPill
                        active={app.platform_visible}
                        label={
                          app.platform_visible
                            ? t('admin.console.apps.visible')
                            : t('admin.console.apps.hidden')
                        }
                      />
                    </td>
                    <td className="border-b border-app-border px-2 py-1 align-middle">
                      <AppVisibilityPill
                        active={app.effective_visible}
                        label={
                          app.effective_visible
                            ? t('admin.console.apps.visible')
                            : t('admin.console.apps.hidden')
                        }
                      />
                    </td>
                    <td className="border-b border-app-border px-2 py-1 align-middle">
                      <AppVisibilityPill
                        active={app.runtime_enabled}
                        label={
                          app.runtime_enabled
                            ? t('admin.console.apps.runtimeEnabled')
                            : t('admin.console.apps.runtimeDisabled')
                        }
                      />
                    </td>
                    <td className="border-b border-app-border px-2 py-1 text-right align-middle">
                      <Select
                        disabled={saving}
                        onValueChange={(value) =>
                          onOverrideChange(
                            app,
                            value as WorkspaceAppVisibilityOverrideValue,
                          )
                        }
                        options={overrideOptions}
                        value={overrideValue}
                      />
                    </td>
                  </tr>
                );
              })}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function AppsSection({
  page,
  token,
}: {
  page: AdminAppsPage;
  token: string;
}) {
  const { t } = useTranslation(['apps', 'shell', 'common']);
  const toast = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const workspaceAppsTab = resolveWorkspaceAppsTab(searchParams.get('tab'));
  const { reload: reloadWorkspaceBootstrap, reloadGlobalApps } =
    useWorkspaceBootstrapContext();
  const [items, setItems] = useState<PlatformAppVisibilityItem[]>([]);
  const [appBarCategories, setAppBarCategories] = useState<
    AdminAppBarCategory[]
  >([]);
  const [workspaces, setWorkspaces] = useState<WorkspaceItem[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string>('');
  const [workspaceItems, setWorkspaceItems] = useState<
    WorkspaceAppVisibilityItem[]
  >([]);
  const [workspaceSearchQuery, setWorkspaceSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [workspaceLoading, setWorkspaceLoading] = useState(false);
  const [savingAppId, setSavingAppId] = useState<string | null>(null);
  const [savingWorkspaceAppId, setSavingWorkspaceAppId] = useState<
    string | null
  >(null);
  const [error, setError] = useState<string | null>(null);

  const loadApps = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      if (page === 'app-bar') {
        return;
      }

      const appBarCategoriesResponse = await listAdminAppBarCategories(token);
      setAppBarCategories(appBarCategoriesResponse.categories);

      if (
        page === 'platform' ||
        (page === 'workspace' && workspaceAppsTab === 'defaults')
      ) {
        const response = await listPlatformAppVisibility(token);
        setItems(response.items);
        return;
      }

      const workspaceResponse = await listWorkspaces(token);
      setWorkspaces(workspaceResponse);
      setSelectedWorkspaceId((current) =>
        current &&
        workspaceResponse.some((workspace) => workspace.id === current)
          ? current
          : (workspaceResponse[0]?.id ?? ''),
      );
    } catch (caughtError) {
      setError(
        getErrorMessage(caughtError, t('admin.console.apps.loadFailed')),
      );
    } finally {
      setLoading(false);
    }
  }, [page, t, token, workspaceAppsTab]);

  useEffect(() => {
    void loadApps();
  }, [loadApps]);

  const selectedWorkspace = useMemo(
    () =>
      workspaces.find((workspace) => workspace.id === selectedWorkspaceId) ??
      null,
    [selectedWorkspaceId, workspaces],
  );

  const platformVisibilityItems = useMemo(
    () =>
      items.filter(
        (item) =>
          item.kind === 'launcher_app' &&
          item.availability_scope === 'platform',
      ),
    [items],
  );

  const { configurableApps, personalTools } = useMemo(
    () => partitionAppVisibilityItems(platformVisibilityItems),
    [platformVisibilityItems],
  );

  const workspaceDefaultItems = useMemo(
    () =>
      items.filter(
        (item) =>
          item.kind === 'launcher_app' &&
          item.availability_scope === 'workspace',
      ),
    [items],
  );

  const platformGroups = useMemo(
    () => buildAppVisibilityGroups(configurableApps, appBarCategories),
    [appBarCategories, configurableApps],
  );

  const personalToolGroups = useMemo(
    () => buildAppVisibilityGroups(personalTools),
    [personalTools],
  );

  const workspaceDefaultGroups = useMemo(
    () => buildAppVisibilityGroups(workspaceDefaultItems, appBarCategories),
    [appBarCategories, workspaceDefaultItems],
  );

  const workspaceGroups = useMemo(
    () => buildAppVisibilityGroups(workspaceItems, appBarCategories),
    [appBarCategories, workspaceItems],
  );

  const filteredWorkspaces = useMemo(() => {
    const query = workspaceSearchQuery.trim().toLocaleLowerCase();
    if (!query) return workspaces;
    return workspaces.filter((workspace) => {
      return (
        workspace.name.toLocaleLowerCase().includes(query) ||
        workspace.key.toLocaleLowerCase().includes(query)
      );
    });
  }, [workspaceSearchQuery, workspaces]);

  const overrideOptions = useMemo<
    Array<{ label: string; value: WorkspaceAppVisibilityOverrideValue }>
  >(
    () => [
      { value: 'inherit', label: t('admin.console.apps.workspaceInherit') },
      { value: 'show', label: t('admin.console.apps.workspaceShow') },
      { value: 'hide', label: t('admin.console.apps.workspaceHide') },
    ],
    [t],
  );

  const loadWorkspaceApps = useCallback(
    async (workspaceId: string) => {
      if (!workspaceId) {
        setWorkspaceItems([]);
        return;
      }
      setWorkspaceLoading(true);
      setError(null);
      try {
        const response = await listWorkspaceAppVisibility(token, workspaceId);
        setWorkspaceItems(
          response.items.filter(
            (item) => item.availability_scope === 'workspace',
          ),
        );
      } catch (caughtError) {
        setError(
          getErrorMessage(
            caughtError,
            t('admin.console.apps.workspaceLoadFailed'),
          ),
        );
      } finally {
        setWorkspaceLoading(false);
      }
    },
    [t, token],
  );

  useEffect(() => {
    if (page === 'workspace' && workspaceAppsTab === 'overrides') {
      void loadWorkspaceApps(selectedWorkspaceId);
    }
  }, [loadWorkspaceApps, page, selectedWorkspaceId, workspaceAppsTab]);

  const handleWorkspaceAppsTabChange = useCallback(
    (value: string) => {
      const next = new URLSearchParams(searchParams);
      next.set('tab', resolveWorkspaceAppsTab(value));
      setSearchParams(next);
    },
    [searchParams, setSearchParams],
  );

  const handleToggle = useCallback(
    async (app: PlatformAppVisibilityItem, visible: boolean) => {
      setSavingAppId(app.app_id);
      setError(null);
      try {
        const response = await updatePlatformAppVisibility(token, {
          items: [{ app_id: app.app_id, visible }],
        });
        setItems(response.items);
        reloadWorkspaceBootstrap();
        reloadGlobalApps?.();
        toast.success(
          t(
            visible
              ? 'admin.console.apps.showSaved'
              : 'admin.console.apps.hideSaved',
            {
              app: t(`shell:apps.${app.app_id}`, {
                defaultValue: app.title,
              }),
            },
          ),
        );
      } catch (caughtError) {
        setError(
          getErrorMessage(caughtError, t('admin.console.apps.saveFailed')),
        );
      } finally {
        setSavingAppId(null);
      }
    },
    [reloadGlobalApps, reloadWorkspaceBootstrap, t, toast, token],
  );

  const handleWorkspaceOverrideChange = useCallback(
    async (
      app: WorkspaceAppVisibilityItem,
      value: WorkspaceAppVisibilityOverrideValue,
    ) => {
      if (!selectedWorkspace) return;
      const visibilityOverride = value === 'inherit' ? null : value === 'show';
      setSavingWorkspaceAppId(app.app_id);
      setError(null);
      try {
        const response = await updateWorkspaceAppVisibility(
          token,
          selectedWorkspace.id,
          {
            items: [
              {
                app_id: app.app_id,
                visibility_override: visibilityOverride,
              },
            ],
          },
        );
        setWorkspaceItems(
          response.items.filter(
            (item) => item.availability_scope === 'workspace',
          ),
        );
        reloadWorkspaceBootstrap();
        toast.success(
          t('admin.console.apps.workspaceSaved', {
            app: t(`shell:apps.${app.app_id}`, {
              defaultValue: app.title,
            }),
            workspace: selectedWorkspace.name,
          }),
        );
      } catch (caughtError) {
        setError(
          getErrorMessage(
            caughtError,
            t('admin.console.apps.workspaceSaveFailed'),
          ),
        );
      } finally {
        setSavingWorkspaceAppId(null);
      }
    },
    [reloadWorkspaceBootstrap, selectedWorkspace, t, toast, token],
  );

  const handleAppBarCategoriesChanged = useCallback(() => {
    reloadWorkspaceBootstrap();
    reloadGlobalApps?.();
    void loadApps();
  }, [loadApps, reloadGlobalApps, reloadWorkspaceBootstrap]);

  const appDisplayName = useCallback(
    (app: AppVisibilityGroupableItem) =>
      t(`shell:apps.${app.app_id}`, {
        defaultValue: app.title,
      }),
    [t],
  );

  return (
    <div className="space-y-3">
      <SectionMessage error={error} message={null} />

      {page === 'platform' ? (
        <div className="space-y-6">
          <section className="space-y-2">
            <div className="flex flex-col gap-2 border-b border-app-border pb-2 lg:flex-row lg:items-center lg:justify-between">
              <div className="min-w-0">
                <h2 className="app-text-control text-app-ink">
                  {t('admin.console.apps.title')}
                </h2>
                <p className="app-text-caption mt-0.5 max-w-3xl truncate text-app-ink/55">
                  {t('admin.console.apps.description')}
                </p>
              </div>
              <Tooltip content={t('admin.console.apps.refresh')}>
                <button
                  aria-label={t('admin.console.apps.refresh')}
                  className="inline-flex size-8 shrink-0 items-center justify-center rounded-md border border-app-border text-app-ink transition-colors hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={loading}
                  onClick={() => void loadApps()}
                  type="button"
                >
                  <RefreshCw size={14} />
                </button>
              </Tooltip>
            </div>
            <PlatformAppVisibilityGroups
              appDisplayName={appDisplayName}
              groups={platformGroups}
              itemsLength={configurableApps.length}
              loading={loading}
              onToggle={(app, visible) => void handleToggle(app, visible)}
              savingAppId={savingAppId}
              t={t}
            />
          </section>
          <section className="space-y-2">
            <div className="flex flex-col gap-2 border-b border-app-border pb-2 lg:flex-row lg:items-center lg:justify-between">
              <div className="min-w-0">
                <h2 className="app-text-control text-app-ink">
                  {t('admin.console.apps.personalToolsTitle')}
                </h2>
                <p className="app-text-caption mt-0.5 max-w-3xl text-app-ink/55">
                  {t('admin.console.apps.personalToolsDescription')}
                </p>
              </div>
              <Tooltip content={t('admin.console.apps.refresh')}>
                <button
                  aria-label={t('admin.console.apps.refresh')}
                  className="inline-flex size-8 shrink-0 items-center justify-center rounded-md border border-app-border text-app-ink transition-colors hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={loading}
                  onClick={() => void loadApps()}
                  type="button"
                >
                  <RefreshCw size={14} />
                </button>
              </Tooltip>
            </div>
            <PlatformAppVisibilityGroups
              appDisplayName={appDisplayName}
              groups={personalToolGroups}
              itemsLength={personalTools.length}
              loading={loading}
              onToggle={(app, visible) => void handleToggle(app, visible)}
              platformScopeLabel={t('admin.console.apps.personalToolsScope')}
              savingAppId={savingAppId}
              scopeColumnLabel={t(
                'admin.console.apps.personalToolsScopeColumn',
              )}
              t={t}
            />
          </section>
        </div>
      ) : null}

      {page === 'workspace' ? (
        <Tabs
          onValueChange={handleWorkspaceAppsTabChange}
          value={workspaceAppsTab}
        >
          <div className="flex border-b border-app-border pb-2">
            <TabsList>
              <TabsTrigger value="defaults">
                {t('admin.console.apps.workspaceDefaultsTab')}
              </TabsTrigger>
              <TabsTrigger value="overrides">
                {t('admin.console.apps.workspaceOverridesTab')}
              </TabsTrigger>
            </TabsList>
          </div>

          <TabsContent className="space-y-2" value="defaults">
            <section className="space-y-2">
              <div className="flex flex-col gap-2 border-b border-app-border pb-2 lg:flex-row lg:items-center lg:justify-between">
                <div className="min-w-0">
                  <h2 className="app-text-control text-app-ink">
                    {t('admin.console.apps.workspaceDefaultsTitle')}
                  </h2>
                  <p className="app-text-caption mt-0.5 max-w-3xl text-app-ink/55">
                    {t('admin.console.apps.workspaceDefaultsDescription')}
                  </p>
                </div>
                <Tooltip content={t('admin.console.apps.refresh')}>
                  <button
                    aria-label={t('admin.console.apps.refresh')}
                    className="inline-flex size-8 shrink-0 items-center justify-center rounded-md border border-app-border text-app-ink transition-colors hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-50"
                    disabled={loading}
                    onClick={() => void loadApps()}
                    type="button"
                  >
                    <RefreshCw size={14} />
                  </button>
                </Tooltip>
              </div>
              <PlatformAppVisibilityGroups
                appDisplayName={appDisplayName}
                groups={workspaceDefaultGroups}
                itemsLength={workspaceDefaultItems.length}
                loading={loading}
                onToggle={(app, visible) => void handleToggle(app, visible)}
                savingAppId={savingAppId}
                t={t}
              />
            </section>
          </TabsContent>

          <TabsContent className="space-y-2" value="overrides">
            <section className="space-y-2">
              <div className="flex flex-col gap-2 border-b border-app-border pb-2 lg:flex-row lg:items-center lg:justify-between">
                <div className="min-w-0">
                  <h2 className="app-text-control text-app-ink">
                    {t('admin.console.apps.workspaceTitle')}
                  </h2>
                  <p className="app-text-caption mt-0.5 max-w-3xl truncate text-app-ink/55">
                    {t('admin.console.apps.workspaceDescription')}
                  </p>
                </div>
              </div>
              <div className="grid gap-3 lg:grid-cols-[260px_1fr]">
                <aside className="overflow-hidden rounded-md border border-app-border bg-app-bg">
                  <div className="flex items-center justify-between gap-2 border-b border-app-border px-3 py-2">
                    <h3 className="app-text-overline uppercase text-app-ink/60">
                      {t('admin.console.apps.workspaceListTitle')} ·{' '}
                      {workspaces.length}
                    </h3>
                    <Tooltip content={t('admin.console.apps.refresh')}>
                      <button
                        aria-label={t('admin.console.apps.refresh')}
                        className="inline-flex size-7 shrink-0 items-center justify-center rounded-md text-app-ink/60 transition-colors hover:bg-app-surface-hover hover:text-app-ink disabled:cursor-not-allowed disabled:opacity-50"
                        disabled={loading}
                        onClick={() => void loadApps()}
                        type="button"
                      >
                        <RefreshCw size={13} />
                      </button>
                    </Tooltip>
                  </div>
                  <div className="border-b border-app-border px-3 py-2">
                    <div className="flex items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-2 py-1">
                      <Search size={12} className="text-app-ink/50" />
                      <input
                        aria-label={t(
                          'admin.console.apps.workspaceSearchPlaceholder',
                        )}
                        className="app-text-body-sm min-w-0 flex-1 bg-transparent text-app-ink outline-none placeholder:text-app-ink/40"
                        onChange={(event) =>
                          setWorkspaceSearchQuery(event.target.value)
                        }
                        placeholder={t(
                          'admin.console.apps.workspaceSearchPlaceholder',
                        )}
                        value={workspaceSearchQuery}
                      />
                    </div>
                  </div>
                  <div className="max-h-[520px] overflow-y-auto pb-1">
                    {loading && workspaces.length === 0 ? (
                      <div className="px-3 py-8 text-center text-app-ink/45">
                        <p className="app-text-body-sm">
                          {t('admin.console.apps.workspaceLoadingTitle')}
                        </p>
                      </div>
                    ) : filteredWorkspaces.length === 0 ? (
                      <div className="px-3 py-8 text-center text-app-ink/45">
                        <p className="app-text-body-sm">
                          {workspaces.length === 0
                            ? t('admin.console.apps.workspaceEmptyTitle')
                            : t('admin.console.apps.workspaceNoResults')}
                        </p>
                      </div>
                    ) : (
                      filteredWorkspaces.map((workspace) => {
                        const isSelected = workspace.id === selectedWorkspaceId;
                        return (
                          <button
                            className={`relative flex w-full items-center gap-2 px-3 py-1.5 text-left transition-colors ${
                              isSelected
                                ? 'bg-app-accent/10 text-app-ink'
                                : 'text-app-ink/85 hover:bg-app-surface-sidebar'
                            }`}
                            key={workspace.id}
                            onClick={() => setSelectedWorkspaceId(workspace.id)}
                            type="button"
                          >
                            {isSelected ? (
                              <span className="absolute left-0 top-1 bottom-1 w-[3px] rounded-r bg-app-accent" />
                            ) : null}
                            <span
                              className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                                workspace.active
                                  ? 'bg-app-success'
                                  : 'bg-app-ink/30'
                              }`}
                            />
                            <div className="min-w-0 flex-1">
                              <div className="app-text-body-sm truncate font-medium text-app-ink">
                                {workspace.name}
                              </div>
                              <WorkspaceListItemMeta
                                t={t}
                                workspace={workspace}
                              />
                            </div>
                          </button>
                        );
                      })
                    )}
                  </div>
                </aside>

                <div className="min-w-0 space-y-3">
                  <div className="flex min-h-12 items-center justify-between gap-3 rounded-md border border-app-border bg-app-bg px-3 py-2">
                    <div className="min-w-0">
                      <h3 className="app-text-control truncate text-app-ink">
                        {selectedWorkspace?.name ??
                          t('admin.console.apps.workspaceEmptyTitle')}
                      </h3>
                      {selectedWorkspace ? (
                        <WorkspaceListItemMeta
                          t={t}
                          workspace={selectedWorkspace}
                        />
                      ) : (
                        <p className="app-text-caption truncate text-app-ink/50">
                          {t('admin.console.apps.workspaceEmptyDescription')}
                        </p>
                      )}
                    </div>
                    <Tooltip content={t('admin.console.apps.refresh')}>
                      <button
                        aria-label={t('admin.console.apps.refresh')}
                        className="inline-flex size-8 shrink-0 items-center justify-center rounded-md border border-app-border text-app-ink transition-colors hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-50"
                        disabled={workspaceLoading || !selectedWorkspaceId}
                        onClick={() =>
                          void loadWorkspaceApps(selectedWorkspaceId)
                        }
                        type="button"
                      >
                        <RefreshCw size={14} />
                      </button>
                    </Tooltip>
                  </div>
                  <WorkspaceAppVisibilityGroups
                    appDisplayName={appDisplayName}
                    groups={workspaceGroups}
                    loading={workspaceLoading}
                    onOverrideChange={(app, value) =>
                      void handleWorkspaceOverrideChange(app, value)
                    }
                    overrideOptions={overrideOptions}
                    savingWorkspaceAppId={savingWorkspaceAppId}
                    t={t}
                    workspacesLength={workspaces.length}
                    workspaceItemsLength={workspaceItems.length}
                  />
                </div>
              </div>
            </section>
          </TabsContent>
        </Tabs>
      ) : null}
      {page === 'app-bar' ? (
        <AppBarCategoriesAdmin
          onChanged={handleAppBarCategoriesChanged}
          token={token}
        />
      ) : null}
    </div>
  );
}

function appBarCategoryIconKeys(
  apiIconKeys: readonly string[] | undefined,
): readonly string[] {
  return Array.from(
    new Set([...(apiIconKeys ?? []), ...WORKSPACE_APP_ICON_KEYS]),
  ).sort((left, right) => left.localeCompare(right));
}

function appBarIconPickerGroups(
  iconKeys: readonly string[],
  labelForGroup: (groupId: string) => string,
): readonly IconPickerGroup[] {
  const allowedIconKeys = new Set(iconKeys);
  const groups: IconPickerGroup[] = WORKSPACE_APP_ICON_PICKER_GROUPS.map(
    (group) => ({
      id: group.id,
      iconKeys: group.iconKeys.filter((iconKey) =>
        allowedIconKeys.has(iconKey),
      ),
      label: labelForGroup(group.id),
    }),
  ).filter((group) => group.iconKeys.length > 0);
  const groupedIconKeys = new Set(
    groups.flatMap((group) => [...group.iconKeys]),
  );
  const otherIconKeys = iconKeys.filter(
    (iconKey) => !groupedIconKeys.has(iconKey),
  );
  if (otherIconKeys.length > 0) {
    groups.push({
      id: 'other',
      iconKeys: otherIconKeys,
      label: labelForGroup('other'),
    });
  }
  return groups;
}

function AppBarCategoriesAdmin({
  onChanged,
  token,
}: {
  onChanged: () => void;
  token: string;
}) {
  const { t } = useTranslation(['apps', 'shell', 'common']);
  const toast = useToast();
  const [response, setResponse] =
    useState<AdminAppBarCategoriesResponse | null>(null);
  const [draftCategories, setDraftCategories] = useState<AdminAppBarCategory[]>(
    [],
  );
  const [selectedCategoryId, setSelectedCategoryId] = useState<string | null>(
    null,
  );
  const [iconPickerTarget, setIconPickerTarget] = useState<string | null>(null);
  const [appSearchQuery, setAppSearchQuery] = useState('');
  const [newCategoryTitle, setNewCategoryTitle] = useState('');
  const [newCategoryIcon, setNewCategoryIcon] = useState('layout');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const applyResponse = useCallback((next: AdminAppBarCategoriesResponse) => {
    setResponse(next);
    setDraftCategories(next.categories.map(copyAdminAppBarCategory));
    setSelectedCategoryId((current) =>
      current && next.categories.some((category) => category.id === current)
        ? current
        : (next.categories[0]?.id ?? null),
    );
    const nextIconKeys = appBarCategoryIconKeys(next.icon_keys);
    setNewCategoryIcon((current) =>
      nextIconKeys.includes(current) ? current : 'layout',
    );
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      applyResponse(await listAdminAppBarCategories(token));
    } catch (caughtError) {
      toast.error(
        getErrorMessage(caughtError, t('admin.console.apps.appBarLoadFailed')),
      );
    } finally {
      setLoading(false);
    }
  }, [applyResponse, t, toast, token]);

  useEffect(() => {
    void load();
  }, [load]);

  const iconKeys = useMemo(
    () => appBarCategoryIconKeys(response?.icon_keys),
    [response?.icon_keys],
  );
  const iconPickerGroups = useMemo(
    () =>
      appBarIconPickerGroups(iconKeys, (groupId) =>
        t(`admin.console.apps.appBarIconGroups.${groupId}`),
      ),
    [iconKeys, t],
  );
  const availableApps = useMemo(
    () => response?.available_apps ?? [],
    [response?.available_apps],
  );
  const availableAppById = useMemo(() => {
    const items = new Map<string, AdminAppBarCategoryAppItem>();
    for (const app of availableApps) {
      items.set(app.app_id, app);
    }
    for (const category of draftCategories) {
      for (const app of category.items) {
        items.set(app.app_id, app);
      }
    }
    return items;
  }, [availableApps, draftCategories]);
  const assignedCategoryByAppId = useMemo(() => {
    const items = new Map<string, AdminAppBarCategory>();
    for (const category of draftCategories) {
      for (const app of category.items) {
        items.set(app.app_id, category);
      }
    }
    return items;
  }, [draftCategories]);
  const selectedCategory = useMemo(() => {
    if (draftCategories.length === 0) {
      return null;
    }
    return (
      draftCategories.find((category) => category.id === selectedCategoryId) ??
      draftCategories[0]
    );
  }, [draftCategories, selectedCategoryId]);
  const selectedCategoryApps = selectedCategory?.items ?? [];
  const selectedCategoryAssignableApps = useMemo(() => {
    if (!selectedCategory) {
      return [];
    }
    const selectedAppIds = new Set(
      selectedCategory.items.map((item) => item.app_id),
    );
    return availableApps.filter((app) => !selectedAppIds.has(app.app_id));
  }, [availableApps, selectedCategory]);
  const iconPickerValue =
    iconPickerTarget === 'new'
      ? newCategoryIcon
      : (draftCategories.find((category) => category.id === iconPickerTarget)
          ?.icon_key ?? 'layout');
  const iconPickerTitle =
    iconPickerTarget === 'new'
      ? t('admin.console.apps.appBarNewCategoryTitle')
      : (draftCategories.find((category) => category.id === iconPickerTarget)
          ?.title ?? t('admin.console.apps.appBarCategoryIcon'));
  const SelectedCategoryIcon = selectedCategory
    ? workspaceAppIconForKey(selectedCategory.icon_key)
    : null;

  useEffect(() => {
    setAppSearchQuery('');
  }, [selectedCategory?.id]);

  const appDisplayName = useCallback(
    (app: AdminAppBarCategoryAppItem) =>
      t(`shell:apps.${app.app_id}`, { defaultValue: app.title }),
    [t],
  );
  const normalizedAppSearchQuery = appSearchQuery.trim().toLowerCase();
  const hasAppSearchQuery = normalizedAppSearchQuery.length > 0;
  const filteredSelectedCategoryAssignableApps = useMemo(() => {
    if (!hasAppSearchQuery) {
      return selectedCategoryAssignableApps;
    }
    return selectedCategoryAssignableApps.filter((app) => {
      const assignedCategory = assignedCategoryByAppId.get(app.app_id);
      const searchableValues = [
        app.app_id,
        app.title,
        appDisplayName(app),
        assignedCategory?.title,
      ];
      return searchableValues.some((value) =>
        (value ?? '').toLowerCase().includes(normalizedAppSearchQuery),
      );
    });
  }, [
    appDisplayName,
    assignedCategoryByAppId,
    hasAppSearchQuery,
    normalizedAppSearchQuery,
    selectedCategoryAssignableApps,
  ]);
  const unassignedAssignableApps = useMemo(
    () =>
      filteredSelectedCategoryAssignableApps.filter(
        (app) => !assignedCategoryByAppId.has(app.app_id),
      ),
    [assignedCategoryByAppId, filteredSelectedCategoryAssignableApps],
  );
  const movableAssignableApps = useMemo(
    () =>
      filteredSelectedCategoryAssignableApps.filter((app) =>
        assignedCategoryByAppId.has(app.app_id),
      ),
    [assignedCategoryByAppId, filteredSelectedCategoryAssignableApps],
  );

  const updateDraftCategory = useCallback(
    (categoryId: string, patch: Partial<AdminAppBarCategory>) => {
      setDraftCategories((current) =>
        current.map((category) =>
          category.id === categoryId ? { ...category, ...patch } : category,
        ),
      );
    },
    [],
  );

  const selectIcon = useCallback(
    (iconKey: string) => {
      if (iconPickerTarget === 'new') {
        setNewCategoryIcon(iconKey);
      } else if (iconPickerTarget) {
        updateDraftCategory(iconPickerTarget, { icon_key: iconKey });
      }
      setIconPickerTarget(null);
    },
    [iconPickerTarget, updateDraftCategory],
  );

  const moveDraftCategory = useCallback(
    (categoryId: string, direction: -1 | 1) => {
      setDraftCategories((current) => {
        const index = current.findIndex(
          (category) => category.id === categoryId,
        );
        const nextIndex = index + direction;
        if (index < 0 || nextIndex < 0 || nextIndex >= current.length) {
          return current;
        }
        const next = [...current];
        [next[index], next[nextIndex]] = [next[nextIndex], next[index]];
        return next;
      });
    },
    [],
  );

  const toggleCategoryApp = useCallback(
    (categoryId: string, appId: string, checked: boolean) => {
      const app = availableAppById.get(appId);
      if (!app) return;
      setDraftCategories((current) =>
        current.map((category) => {
          const items = category.items.filter((item) => item.app_id !== appId);
          if (checked && category.id === categoryId) {
            items.push(app);
          }
          return { ...category, items };
        }),
      );
    },
    [availableAppById],
  );

  const createCategory = useCallback(async () => {
    const title = newCategoryTitle.trim();
    if (!title) {
      toast.error(t('admin.console.apps.appBarCategoryTitleRequired'));
      return;
    }
    setSaving(true);
    try {
      const next = await createAdminAppBarCategory(token, {
        icon_key: newCategoryIcon,
        title,
      });
      applyResponse(next);
      setSelectedCategoryId(
        next.categories[next.categories.length - 1]?.id ?? null,
      );
      setIconPickerTarget(null);
      setNewCategoryTitle('');
      onChanged();
      toast.success(t('admin.console.apps.appBarCategoryCreated'));
    } catch (caughtError) {
      toast.error(
        getErrorMessage(
          caughtError,
          t('admin.console.apps.appBarCategoryCreateFailed'),
        ),
      );
    } finally {
      setSaving(false);
    }
  }, [
    applyResponse,
    newCategoryIcon,
    newCategoryTitle,
    onChanged,
    t,
    toast,
    token,
  ]);

  const deleteCategory = useCallback(
    async (category: AdminAppBarCategory) => {
      if (
        !window.confirm(
          t('admin.console.apps.appBarCategoryDeleteConfirm', {
            title: category.title,
          }),
        )
      ) {
        return;
      }
      setSaving(true);
      try {
        const next = await deleteAdminAppBarCategory(token, category.id);
        applyResponse(next);
        setIconPickerTarget((current) =>
          current === category.id ? null : current,
        );
        onChanged();
        toast.success(t('admin.console.apps.appBarCategoryDeleted'));
      } catch (caughtError) {
        toast.error(
          getErrorMessage(
            caughtError,
            t('admin.console.apps.appBarCategoryDeleteFailed'),
          ),
        );
      } finally {
        setSaving(false);
      }
    },
    [applyResponse, onChanged, t, toast, token],
  );

  const saveLayout = useCallback(async () => {
    setSaving(true);
    try {
      const next = await updateAdminAppBarCategoryLayout(token, {
        categories: draftCategories.map((category) => ({
          app_ids: category.items.map((item) => item.app_id),
          icon_key: category.icon_key,
          id: category.id,
          title: category.title.trim(),
        })),
      });
      applyResponse(next);
      onChanged();
      toast.success(t('admin.console.apps.appBarLayoutSaved'));
    } catch (caughtError) {
      toast.error(
        getErrorMessage(
          caughtError,
          t('admin.console.apps.appBarLayoutSaveFailed'),
        ),
      );
    } finally {
      setSaving(false);
    }
  }, [applyResponse, draftCategories, onChanged, t, toast, token]);

  return (
    <section className="space-y-3">
      <div className="flex flex-col gap-2 border-b border-app-border pb-2 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0">
          <h2 className="app-text-control text-app-ink">
            {t('admin.console.apps.appBarTitle')}
          </h2>
          <p className="app-text-caption mt-0.5 max-w-3xl text-app-ink/55">
            {t('admin.console.apps.appBarDescription')}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Tooltip content={t('admin.console.apps.refresh')}>
            <button
              aria-label={t('admin.console.apps.refresh')}
              className="inline-flex size-8 items-center justify-center rounded-md border border-app-border text-app-ink transition-colors hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-50"
              disabled={loading || saving}
              onClick={() => void load()}
              type="button"
            >
              <RefreshCw size={14} />
            </button>
          </Tooltip>
          <Button
            disabled={loading || saving}
            onClick={() => void saveLayout()}
          >
            <Save size={15} />
            {t('admin.console.apps.appBarSaveLayout')}
          </Button>
        </div>
      </div>

      <div className="rounded-md border border-app-border bg-app-bg p-3">
        <div className="grid gap-3 lg:grid-cols-[minmax(260px,1fr)_auto_auto] lg:items-end">
          <label className="space-y-1">
            <span className="app-text-caption text-app-ink/60">
              {t('admin.console.apps.appBarNewCategoryTitle')}
            </span>
            <input
              className={fieldClassName}
              onChange={(event) =>
                setNewCategoryTitle(event.currentTarget.value)
              }
              placeholder={t('admin.console.apps.appBarNewCategoryPlaceholder')}
              value={newCategoryTitle}
            />
          </label>
          <CategoryIconButton
            disabled={loading || saving || iconKeys.length === 0}
            iconKey={newCategoryIcon}
            label={t('admin.console.apps.appBarCategoryIcon')}
            onClick={() => setIconPickerTarget('new')}
          />
          <Button
            disabled={loading || saving}
            onClick={() => void createCategory()}
          >
            <Plus size={15} />
            {t('admin.console.apps.appBarAddCategory')}
          </Button>
        </div>
      </div>

      {loading && draftCategories.length === 0 ? (
        <EmptyPanel
          description={t('admin.console.apps.appBarLoadingDescription')}
          title={t('admin.console.apps.appBarLoadingTitle')}
        />
      ) : draftCategories.length === 0 ? (
        <EmptyPanel
          description={t('admin.console.apps.appBarEmptyDescription')}
          title={t('admin.console.apps.appBarEmptyTitle')}
        />
      ) : (
        <div className="grid gap-3 xl:grid-cols-[minmax(260px,340px)_minmax(0,1fr)]">
          <aside className="min-w-0 self-start rounded-md border border-app-border bg-app-bg">
            <div className="flex items-center justify-between gap-2 border-b border-app-border bg-app-surface-sidebar px-3 py-2">
              <h3 className="app-text-caption font-medium text-app-ink">
                {t('admin.console.apps.appBarCategoriesList')}
              </h3>
              <span className="app-text-micro text-app-ink/45">
                {draftCategories.length}
              </span>
            </div>
            <div className="divide-y divide-app-border">
              {draftCategories.map((category, index) => {
                const CategoryIcon = workspaceAppIconForKey(category.icon_key);
                const selected = selectedCategory?.id === category.id;
                return (
                  <div
                    className={`flex min-w-0 items-center gap-1 border-l-2 px-2 py-1.5 ${
                      selected
                        ? 'border-app-accent bg-app-accent/10'
                        : 'border-transparent bg-app-bg'
                    }`}
                    key={category.id}
                  >
                    <button
                      aria-pressed={selected}
                      className="flex min-w-0 flex-1 items-center gap-2 rounded-md px-2 py-2 text-left transition-colors hover:bg-app-surface-hover"
                      onClick={() => setSelectedCategoryId(category.id)}
                      type="button"
                    >
                      <span
                        className={`flex size-8 shrink-0 items-center justify-center rounded-md border ${
                          selected
                            ? 'border-app-accent/35 bg-app-bg text-app-accent'
                            : 'border-app-border bg-app-surface-sidebar text-app-ink/55'
                        }`}
                      >
                        <CategoryIcon size={15} />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="app-text-body-sm block truncate font-medium text-app-ink">
                          {category.title}
                        </span>
                        <span className="app-text-micro block truncate text-app-ink/45">
                          {t('admin.console.apps.appBarCategoryAppCount', {
                            count: category.items.length,
                          })}
                        </span>
                      </span>
                    </button>
                    <div className="flex shrink-0 items-center gap-1">
                      <Tooltip content={t('admin.console.apps.appBarMoveUp')}>
                        <button
                          aria-label={t('admin.console.apps.appBarMoveUp')}
                          className="inline-flex size-7 items-center justify-center rounded-md border border-app-border bg-app-bg text-app-ink/60 transition-colors hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-40"
                          disabled={saving || index === 0}
                          onClick={() => moveDraftCategory(category.id, -1)}
                          type="button"
                        >
                          <ArrowUp size={13} />
                        </button>
                      </Tooltip>
                      <Tooltip content={t('admin.console.apps.appBarMoveDown')}>
                        <button
                          aria-label={t('admin.console.apps.appBarMoveDown')}
                          className="inline-flex size-7 items-center justify-center rounded-md border border-app-border bg-app-bg text-app-ink/60 transition-colors hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-40"
                          disabled={
                            saving || index === draftCategories.length - 1
                          }
                          onClick={() => moveDraftCategory(category.id, 1)}
                          type="button"
                        >
                          <ArrowDown size={13} />
                        </button>
                      </Tooltip>
                    </div>
                  </div>
                );
              })}
            </div>
          </aside>

          <section className="min-w-0 rounded-md border border-app-border bg-app-bg">
            {selectedCategory ? (
              <>
                <div className="grid gap-3 border-b border-app-border bg-app-surface-sidebar p-3 lg:grid-cols-[auto_minmax(260px,1fr)_auto_auto] lg:items-end">
                  <span className="flex size-10 items-center justify-center rounded-md border border-app-border bg-app-bg text-app-accent">
                    {SelectedCategoryIcon ? (
                      <SelectedCategoryIcon size={18} />
                    ) : null}
                  </span>
                  <label className="space-y-1">
                    <span className="app-text-caption text-app-ink/60">
                      {t('admin.console.apps.appBarCategoryTitle')}
                    </span>
                    <input
                      aria-label={t('admin.console.apps.appBarCategoryTitle')}
                      className={fieldClassName}
                      onChange={(event) =>
                        updateDraftCategory(selectedCategory.id, {
                          title: event.currentTarget.value,
                        })
                      }
                      value={selectedCategory.title}
                    />
                  </label>
                  <CategoryIconButton
                    disabled={saving || iconKeys.length === 0}
                    iconKey={selectedCategory.icon_key}
                    label={t('admin.console.apps.appBarCategoryIcon')}
                    onClick={() => setIconPickerTarget(selectedCategory.id)}
                  />
                  <Tooltip content={t('common:actions.delete')}>
                    <button
                      aria-label={t('common:actions.delete')}
                      className="inline-flex size-9 items-center justify-center rounded-md border border-app-border bg-app-bg text-app-danger transition-colors hover:bg-app-danger/10 disabled:cursor-not-allowed disabled:opacity-40"
                      disabled={saving}
                      onClick={() => void deleteCategory(selectedCategory)}
                      type="button"
                    >
                      <Trash2 size={15} />
                    </button>
                  </Tooltip>
                </div>
                <div className="grid gap-3 p-3 xl:grid-cols-[minmax(280px,0.8fr)_minmax(360px,1.2fr)]">
                  <section className="space-y-2">
                    <div className="flex items-center justify-between gap-2">
                      <h3 className="app-text-caption font-medium text-app-ink">
                        {t('admin.console.apps.appBarSelectedApps')}
                      </h3>
                      <span className="app-text-micro text-app-ink/45">
                        {selectedCategoryApps.length}
                      </span>
                    </div>
                    {selectedCategoryApps.length === 0 ? (
                      <div className="app-text-caption rounded-md border border-dashed border-app-border bg-app-surface-sidebar px-3 py-6 text-center text-app-ink/50">
                        {t('admin.console.apps.appBarNoSelectedApps')}
                      </div>
                    ) : (
                      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
                        {selectedCategoryApps.map((app) => (
                          <AdminAppCategoryItem
                            app={app}
                            disabled={saving}
                            key={app.app_id}
                            onClick={() =>
                              toggleCategoryApp(
                                selectedCategory.id,
                                app.app_id,
                                false,
                              )
                            }
                            action="remove"
                            title={appDisplayName(app)}
                            tooltip={t('admin.console.apps.appBarRemoveApp')}
                            variant="selected"
                          />
                        ))}
                      </div>
                    )}
                  </section>
                  <section className="space-y-2">
                    <div className="flex items-center justify-between gap-2">
                      <h3 className="app-text-caption font-medium text-app-ink">
                        {t('admin.console.apps.appBarAvailableApps')}
                      </h3>
                      <span className="app-text-micro text-app-ink/45">
                        {filteredSelectedCategoryAssignableApps.length}
                      </span>
                    </div>
                    <SearchField
                      aria-label={t('admin.console.apps.appBarSearchApps')}
                      endAdornment={
                        <Search size={14} className="text-app-ink/50" />
                      }
                      onChange={(event) =>
                        setAppSearchQuery(event.currentTarget.value)
                      }
                      placeholder={t(
                        'admin.console.apps.appBarSearchAppsPlaceholder',
                      )}
                      value={appSearchQuery}
                    />
                    {filteredSelectedCategoryAssignableApps.length === 0 ? (
                      <div className="app-text-caption rounded-md border border-dashed border-app-border bg-app-surface-sidebar px-3 py-6 text-center text-app-ink/50">
                        {t(
                          hasAppSearchQuery
                            ? 'admin.console.apps.appBarNoFilteredApps'
                            : 'admin.console.apps.appBarNoAvailableApps',
                        )}
                      </div>
                    ) : (
                      <div className="max-h-[28rem] space-y-3 overflow-y-auto pr-1">
                        {unassignedAssignableApps.length > 0 ? (
                          <section className="space-y-2">
                            <div className="flex items-center justify-between gap-2">
                              <h4 className="app-text-micro font-medium text-app-ink/55">
                                {t('admin.console.apps.appBarUnassignedApps')}
                              </h4>
                              <span className="app-text-micro text-app-ink/40">
                                {unassignedAssignableApps.length}
                              </span>
                            </div>
                            <div className="grid gap-2 sm:grid-cols-2 2xl:grid-cols-3">
                              {unassignedAssignableApps.map((app) => (
                                <AdminAppCategoryItem
                                  action="add"
                                  app={app}
                                  disabled={saving}
                                  key={app.app_id}
                                  onClick={() =>
                                    toggleCategoryApp(
                                      selectedCategory.id,
                                      app.app_id,
                                      true,
                                    )
                                  }
                                  title={appDisplayName(app)}
                                  tooltip={t('admin.console.apps.appBarAddApp')}
                                  variant="available"
                                />
                              ))}
                            </div>
                          </section>
                        ) : null}
                        {movableAssignableApps.length > 0 ? (
                          <section className="space-y-2">
                            <div className="flex items-center justify-between gap-2">
                              <h4 className="app-text-micro font-medium text-app-ink/55">
                                {t(
                                  'admin.console.apps.appBarMoveFromOtherCategories',
                                )}
                              </h4>
                              <span className="app-text-micro text-app-ink/40">
                                {movableAssignableApps.length}
                              </span>
                            </div>
                            <div className="grid gap-2 sm:grid-cols-2 2xl:grid-cols-3">
                              {movableAssignableApps.map((app) => {
                                const assignedCategory =
                                  assignedCategoryByAppId.get(app.app_id);
                                return (
                                  <AdminAppCategoryItem
                                    action="move"
                                    app={app}
                                    detail={
                                      assignedCategory
                                        ? t(
                                            'admin.console.apps.appBarAssignedTo',
                                            {
                                              title: assignedCategory.title,
                                            },
                                          )
                                        : null
                                    }
                                    disabled={saving}
                                    key={app.app_id}
                                    onClick={() =>
                                      toggleCategoryApp(
                                        selectedCategory.id,
                                        app.app_id,
                                        true,
                                      )
                                    }
                                    title={appDisplayName(app)}
                                    tooltip={t(
                                      'admin.console.apps.appBarMoveAppHere',
                                    )}
                                    variant="available"
                                  />
                                );
                              })}
                            </div>
                          </section>
                        ) : null}
                      </div>
                    )}
                  </section>
                </div>
              </>
            ) : (
              <div className="app-text-caption p-6 text-center text-app-ink/55">
                {t('admin.console.apps.appBarNoCategorySelected')}
              </div>
            )}
          </section>
        </div>
      )}
      <IconPickerDialog
        allLabel={t('admin.console.apps.appBarIconGroups.all')}
        closeLabel={t('common:actions.close')}
        emptyLabel={t('admin.console.apps.appBarNoFilteredIcons')}
        groups={iconPickerGroups}
        iconForKey={workspaceAppIconForKey}
        onClose={() => setIconPickerTarget(null)}
        onSelect={selectIcon}
        open={iconPickerTarget !== null}
        searchLabel={t('admin.console.apps.appBarSearchIcons')}
        searchPlaceholder={t('admin.console.apps.appBarSearchIconsPlaceholder')}
        title={t('admin.console.apps.appBarChooseIcon', {
          title: iconPickerTitle,
        })}
        value={iconPickerValue}
      />
    </section>
  );
}

function CategoryIconButton({
  disabled,
  iconKey,
  label,
  onClick,
}: {
  disabled: boolean;
  iconKey: string;
  label: string;
  onClick: () => void;
}) {
  const Icon = workspaceAppIconForKey(iconKey);
  return (
    <div className="space-y-1">
      <span className="app-text-caption text-app-ink/60">{label}</span>
      <Tooltip content={label}>
        <button
          aria-label={label}
          className="inline-flex size-9 items-center justify-center rounded-md border border-app-border bg-app-bg text-app-accent transition-colors hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-40"
          disabled={disabled}
          onClick={onClick}
          type="button"
        >
          <Icon size={17} />
        </button>
      </Tooltip>
    </div>
  );
}

function AdminAppCategoryItem({
  action,
  app,
  detail,
  disabled,
  onClick,
  title,
  tooltip,
  variant,
}: {
  action?: 'add' | 'move' | 'remove';
  app: AdminAppBarCategoryAppItem;
  detail?: string | null;
  disabled: boolean;
  onClick: () => void;
  title: string;
  tooltip: string;
  variant: 'available' | 'selected';
}) {
  const Icon = workspaceAppIconForKey(app.icon_key);
  const itemAction = action ?? (variant === 'selected' ? 'remove' : 'add');
  const ActionIcon =
    itemAction === 'remove' ? X : itemAction === 'move' ? ArrowRight : Plus;
  return (
    <Tooltip content={tooltip}>
      <button
        className={`flex min-h-11 min-w-0 items-center gap-2 rounded-md border px-2.5 py-2 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
          variant === 'selected'
            ? 'border-app-accent/25 bg-app-accent/10 text-app-ink hover:border-app-accent/45'
            : 'border-app-border bg-app-surface-sidebar text-app-ink/75 hover:bg-app-surface-hover hover:text-app-ink'
        }`}
        disabled={disabled}
        onClick={onClick}
        type="button"
      >
        <Icon size={15} className="shrink-0 text-app-ink/55" />
        <span className="min-w-0 flex-1">
          <span className="app-text-body-sm block truncate font-medium">
            {title}
          </span>
          {detail ? (
            <span className="app-text-micro block truncate text-app-ink/45">
              {detail}
            </span>
          ) : null}
        </span>
        <span
          className={`inline-flex size-6 shrink-0 items-center justify-center rounded-md border ${
            variant === 'selected'
              ? 'border-app-accent/25 bg-app-bg text-app-accent'
              : itemAction === 'move'
                ? 'border-app-accent/25 bg-app-bg text-app-accent'
                : 'border-app-border bg-app-bg text-app-ink/55'
          }`}
        >
          <ActionIcon size={13} />
        </span>
      </button>
    </Tooltip>
  );
}

function copyAdminAppBarCategory(
  category: AdminAppBarCategory,
): AdminAppBarCategory {
  return {
    ...category,
    items: category.items.map((item) => ({ ...item })),
  };
}
