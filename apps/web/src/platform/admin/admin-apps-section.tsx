import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
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

import { Button, SearchField, Tooltip, useFeedback } from '@open-work-hub/ui';

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
  updateAdminAppBarCategoryLayout,
  type AdminAppBarCategoriesResponse,
  type AdminAppBarCategory,
  type AdminAppBarCategoryAppItem,
} from './admin-api';
import { AppControlsSection } from './admin-app-controls-section';
import {
  EmptyPanel,
  FORM_FIELD_CLASS as fieldClassName,
  getErrorMessage,
} from './admin-shared';

export type AdminAppsPage = 'app-bar' | 'platform' | 'workspace';
export {
  resolveWorkspaceAppsTab,
  type WorkspaceAppsTab,
} from './admin-app-controls-section';

export function AppsSection({
  page,
  token,
}: {
  page: AdminAppsPage;
  token: string;
}) {
  const { reload, reloadGlobalApps } = useWorkspaceBootstrapContext();
  const handleAppBarCategoriesChanged = useCallback(() => {
    reload();
    reloadGlobalApps?.();
  }, [reload, reloadGlobalApps]);

  if (page !== 'app-bar') {
    return <AppControlsSection page={page} token={token} />;
  }

  return (
    <AppBarCategoriesAdmin
      onChanged={handleAppBarCategoriesChanged}
      token={token}
    />
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
  const toast = useFeedback();
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
