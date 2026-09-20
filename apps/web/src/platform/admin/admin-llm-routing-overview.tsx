import { RefreshCw, RotateCcw, Save, Search } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button, useFeedback } from '@open-work-hub/ui';

import {
  AdminAiModelSettingsApiError,
  getAdminAiModelSettings,
  isAiModelProviderReady,
  isConfigurableModelRoutingWorkload,
  modelSupportsCapabilities,
  resetAdminAiModelWorkloadRoute,
  updateAdminAiModelWorkloadRoute,
  type AdminAiModelSettings,
  type AiModelCatalogEntry,
  type AiModelRoute,
  type AiModelWorkload,
  type AiModelRouteUpdate,
} from './admin-ai-model-settings-api';
import { AdminLlmDefaults } from './admin-llm-defaults';
import { EmptyPanel, FORM_FIELD_CLASS as fieldClassName } from './admin-shared';

export interface WorkloadDraft {
  routeMode: AiModelRoute;
  providerId: string;
  providerExplicit: boolean;
  modelIds: Record<string, string>;
  localMaxOutputK: string;
  externalMaxOutputK: string;
  runtimeAdapterId: string;
}

export function buildLlmWorkloadUpdate(
  data: AdminAiModelSettings,
  workload: AiModelWorkload,
  draft: WorkloadDraft,
): AiModelRouteUpdate {
  const modelIds = Object.fromEntries(
    Object.entries(draft.modelIds).filter(([, id]) => Boolean(id)),
  );
  const localCap = parseOutputK(draft.localMaxOutputK);
  const externalCap = parseOutputK(draft.externalMaxOutputK);
  return {
    expected_registry_digest: data.registry_digest,
    expected_version: workload.override?.version ?? null,
    route_mode:
      draft.routeMode === workload.effective_route
        ? (workload.override?.route_mode ?? null)
        : draft.routeMode,
    provider_id:
      draft.providerExplicit || Object.keys(modelIds).length > 0
        ? draft.providerId || null
        : null,
    model_ids: modelIds,
    local_max_output_tokens:
      localCap === workload.local_max_output_tokens
        ? (workload.override?.local_max_output_tokens ?? null)
        : localCap,
    external_max_output_tokens:
      externalCap === workload.external_max_output_tokens
        ? (workload.override?.external_max_output_tokens ?? null)
        : externalCap,
    runtime_adapter_id:
      draft.runtimeAdapterId === workload.effective_runtime_adapter
        ? (workload.override?.runtime_adapter_id ?? null)
        : draft.runtimeAdapterId,
  };
}

type RouteFilter = 'all' | AiModelRoute;

const TOKENS_PER_K = 1024;
const MIN_OUTPUT_K = 1;
const MAX_OUTPUT_K = 64;
const COMPACT_SELECT_CLASS = 'app-field-input-sm';

function tokenCapToK(tokens: number): string {
  return String(tokens / TOKENS_PER_K);
}

function parseOutputK(value: string): number | null {
  const parsed = Number(value);
  if (
    !Number.isInteger(parsed) ||
    parsed < MIN_OUTPUT_K ||
    parsed > MAX_OUTPUT_K
  ) {
    return null;
  }
  return parsed * TOKENS_PER_K;
}

function outputCapsValid(
  workload: AiModelWorkload,
  draft: WorkloadDraft,
): boolean {
  return workload.allowed_routes.every((route) =>
    route === 'local'
      ? parseOutputK(draft.localMaxOutputK) !== null
      : parseOutputK(draft.externalMaxOutputK) !== null,
  );
}

function inheritedProviderId(
  data: AdminAiModelSettings,
  workload: AiModelWorkload,
  route: AiModelRoute,
): string {
  return (
    data.defaults.find(
      (row) => row.app_id === workload.app_id && row.route_mode === route,
    )?.provider_id ??
    data.defaults.find((row) => row.app_id === '' && row.route_mode === route)
      ?.provider_id ??
    ''
  );
}

function modelsForWorkload(
  data: AdminAiModelSettings,
  workload: AiModelWorkload,
  providerId: string,
): AiModelCatalogEntry[] {
  return data.models.filter(
    (model) =>
      model.provider_id === providerId &&
      model.enabled &&
      model.discovery_status === 'active' &&
      modelSupportsCapabilities(model, workload.required_capabilities),
  );
}

export function selectedModelId(
  data: AdminAiModelSettings,
  workload: AiModelWorkload,
  draft: WorkloadDraft,
  role: string,
): string {
  const models = modelsForWorkload(data, workload, draft.providerId);
  const selected = draft.modelIds[role];
  if (selected)
    return models.some((model) => model.id === selected) ? selected : '';
  const explicitConnection =
    draft.providerExplicit || Object.values(draft.modelIds).some(Boolean);
  const inherited = explicitConnection
    ? undefined
    : [workload.app_id, '']
        .map((appId) =>
          data.defaults.find(
            (row) => row.app_id === appId && row.route_mode === draft.routeMode,
          ),
        )
        .find((row) => row?.provider_id);
  const providerDefault = data.providers.find(
    (provider) => provider.provider_id === draft.providerId,
  )?.default_model_id;
  const modelId = inherited?.model_id || providerDefault;
  return models.some((model) => model.id === modelId) ? modelId || '' : '';
}

function workloadReady(
  data: AdminAiModelSettings,
  workload: AiModelWorkload,
  draft: WorkloadDraft,
): boolean {
  const provider = data.providers.find(
    (item) => item.provider_id === draft.providerId,
  );
  if (!isAiModelProviderReady(data, provider)) return false;
  const roles =
    workload.model_roles.length > 0 ? workload.model_roles : ['default'];
  return roles.every((role) =>
    Boolean(selectedModelId(data, workload, draft, role)),
  );
}

function workloadSelectionUnchanged(
  workload: AiModelWorkload,
  draft: WorkloadDraft,
): boolean {
  const persistedProvider =
    workload.override?.provider_id ?? workload.resolved_routes[0]?.provider_id;
  const persistedModels = workload.override?.model_ids ?? {};
  return (
    draft.providerExplicit === Boolean(workload.override?.provider_id) &&
    draft.routeMode === workload.effective_route &&
    draft.providerId === persistedProvider &&
    JSON.stringify(draft.modelIds) === JSON.stringify(persistedModels) &&
    draft.runtimeAdapterId === workload.effective_runtime_adapter
  );
}

function effectiveWorkloadReady(
  data: AdminAiModelSettings,
  workload: AiModelWorkload,
  draft: WorkloadDraft,
): boolean {
  return workloadSelectionUnchanged(workload, draft)
    ? workload.ready
    : workloadReady(data, workload, draft);
}

function effectiveReadinessCode(
  data: AdminAiModelSettings,
  workload: AiModelWorkload,
  draft: WorkloadDraft,
): string | null {
  if (workloadSelectionUnchanged(workload, draft)) {
    return workload.readiness_code;
  }
  if (!draft.providerId) return 'admin.ai_model_provider_required';
  const provider = data.providers.find(
    (item) => item.provider_id === draft.providerId,
  );
  if (!isAiModelProviderReady(data, provider)) {
    return provider?.provider_id !== 'local' && provider?.enabled
      ? 'admin.ai_model_provider_key_required'
      : 'admin.ai_model_provider_not_ready';
  }
  const roles =
    workload.model_roles.length > 0 ? workload.model_roles : ['default'];
  return roles.some((role) => !selectedModelId(data, workload, draft, role))
    ? 'admin.ai_model_selection_required'
    : null;
}

function workloadDraftUnchanged(
  workload: AiModelWorkload,
  draft: WorkloadDraft,
): boolean {
  return (
    workloadSelectionUnchanged(workload, draft) &&
    parseOutputK(draft.localMaxOutputK) === workload.local_max_output_tokens &&
    parseOutputK(draft.externalMaxOutputK) ===
      workload.external_max_output_tokens
  );
}

function initialDrafts(
  data: AdminAiModelSettings,
): Record<string, WorkloadDraft> {
  return Object.fromEntries(
    data.workloads.map((workload) => {
      const routeMode =
        workload.override?.route_mode ?? workload.effective_route;
      return [
        `${workload.app_id}:${workload.workload_id}`,
        {
          routeMode,
          providerExplicit: Boolean(workload.override?.provider_id),
          providerId:
            workload.override?.provider_id ??
            workload.resolved_routes[0]?.provider_id ??
            inheritedProviderId(data, workload, routeMode),
          modelIds: workload.override?.model_ids ?? {},
          localMaxOutputK: tokenCapToK(workload.local_max_output_tokens),
          externalMaxOutputK: tokenCapToK(workload.external_max_output_tokens),
          runtimeAdapterId:
            workload.override?.runtime_adapter_id ??
            workload.effective_runtime_adapter,
        },
      ];
    }),
  );
}

function readinessLabelKey(code: string | null): string {
  return code?.replace(/^admin\./, '') ?? 'unknown';
}

export function AdminLlmRoutingOverview({ token }: { token: string }) {
  const { t } = useTranslation('apps');
  const toast = useFeedback();
  const [data, setData] = useState<AdminAiModelSettings | null>(null);
  const [drafts, setDrafts] = useState<Record<string, WorkloadDraft>>({});
  const [loading, setLoading] = useState(true);
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const requestPending = useRef(false);
  const [query, setQuery] = useState('');
  const [routeFilter, setRouteFilter] = useState<RouteFilter>('all');

  const applySnapshot = useCallback((snapshot: AdminAiModelSettings) => {
    setData(snapshot);
    setDrafts(initialDrafts(snapshot));
  }, []);

  const refreshSnapshot = useCallback(async () => {
    setLoading(true);
    try {
      applySnapshot(await getAdminAiModelSettings(token));
    } catch {
      toast.error(t('admin.console.aiSecurity.modelSettings.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [applySnapshot, t, toast, token]);

  const load = useCallback(async () => {
    if (requestPending.current) return;
    requestPending.current = true;
    try {
      await refreshSnapshot();
    } finally {
      requestPending.current = false;
    }
  }, [refreshSnapshot]);

  useEffect(() => {
    void load();
  }, [load]);

  const runMutation = useCallback(
    async (key: string, mutation: () => Promise<AdminAiModelSettings>) => {
      if (requestPending.current) return;
      requestPending.current = true;
      setSavingKey(key);
      try {
        applySnapshot(await mutation());
        toast.success(t('admin.console.aiSecurity.modelSettings.saved'));
      } catch (error) {
        if (
          error instanceof AdminAiModelSettingsApiError &&
          error.status === 409
        ) {
          toast.info(t('admin.console.aiSecurity.modelSettings.conflict'));
          await refreshSnapshot();
        } else {
          toast.error(
            error instanceof AdminAiModelSettingsApiError
              ? error.message
              : t('admin.console.aiSecurity.modelSettings.saveFailed'),
          );
        }
      } finally {
        requestPending.current = false;
        setSavingKey(null);
      }
    },
    [applySnapshot, refreshSnapshot, t, toast],
  );

  const routingWorkloads = useMemo(
    () => data?.workloads.filter(isConfigurableModelRoutingWorkload) ?? [],
    [data],
  );

  const filteredWorkloads = useMemo(() => {
    if (!data) return [];
    const normalizedQuery = query.trim().toLocaleLowerCase();
    return routingWorkloads.filter((workload) => {
      const draft = drafts[`${workload.app_id}:${workload.workload_id}`];
      if (!draft) return false;
      if (routeFilter !== 'all' && draft.routeMode !== routeFilter)
        return false;
      if (!normalizedQuery) return true;
      const localizedLabel = workload.label_key
        ? t(workload.label_key, { defaultValue: workload.workload_id })
        : workload.workload_id;
      const localizedDescription = workload.description_key
        ? t(workload.description_key, {
            defaultValue: workload.description,
          })
        : workload.description;
      const searchable = [
        workload.workload_id,
        workload.task_kind,
        workload.owner_domain,
        workload.description,
        localizedLabel,
        localizedDescription,
        ...workload.app_ids,
        ...workload.app_ids.map((appId) =>
          t(`shell:apps.${appId}`, { defaultValue: appId }),
        ),
        draft.providerId,
        ...workload.resolved_routes.map((route) => route.model_key),
      ]
        .join(' ')
        .toLocaleLowerCase();
      return searchable.includes(normalizedQuery);
    });
  }, [data, drafts, query, routeFilter, routingWorkloads, t]);

  const summary = useMemo(() => {
    if (!data) return { external: 0, local: 0, needsSetup: 0 };
    return routingWorkloads.reduce(
      (counts, workload) => {
        const draft = drafts[`${workload.app_id}:${workload.workload_id}`];
        if (!draft) return counts;
        counts[draft.routeMode] += 1;
        if (!effectiveWorkloadReady(data, workload, draft))
          counts.needsSetup += 1;
        return counts;
      },
      { external: 0, local: 0, needsSetup: 0 },
    );
  }, [data, drafts, routingWorkloads]);

  if (loading && !data) {
    return (
      <EmptyPanel
        description={t(
          'admin.console.aiSecurity.modelSettings.loadingDescription',
        )}
        title={t('admin.console.aiSecurity.modelSettings.loadingTitle')}
      />
    );
  }

  if (!data) {
    return (
      <EmptyPanel
        description={t(
          'admin.console.aiSecurity.modelSettings.emptyDescription',
        )}
        title={t('admin.console.aiSecurity.modelSettings.emptyTitle')}
      />
    );
  }

  return (
    <div className="space-y-3">
      <AdminLlmDefaults
        token={token}
        data={data}
        disabled={loading || savingKey !== null}
        onSave={runMutation}
      />
      <div className="grid gap-2 rounded-md border border-app-border bg-app-surface px-2 py-2 sm:grid-cols-[minmax(0,1fr)_140px_auto] sm:items-center xl:grid-cols-[auto_minmax(240px,1fr)_140px_auto]">
        <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 px-1 sm:col-span-3 xl:col-span-1">
          <span className="app-text-caption shrink-0 whitespace-nowrap text-app-ink/65">
            {t('admin.console.aiSecurity.routingOverview.summary', {
              total: routingWorkloads.length,
              local: summary.local,
              external: summary.external,
            })}
          </span>
          {summary.needsSetup > 0 ? (
            <span className="app-text-caption shrink-0 text-app-danger-text">
              {t('admin.console.aiSecurity.routingOverview.errorCount', {
                count: summary.needsSetup,
              })}
            </span>
          ) : null}
          {query.trim() || routeFilter !== 'all' ? (
            <span className="app-text-caption shrink-0 text-app-ink/55">
              {t('admin.console.aiSecurity.routingOverview.resultCount', {
                count: filteredWorkloads.length,
              })}
            </span>
          ) : null}
        </div>
        <label className="flex min-h-8 min-w-0 items-center gap-2 rounded-md border border-app-border bg-app-bg px-2">
          <Search className="shrink-0 text-app-ink/40" size={14} />
          <input
            aria-label={t('admin.console.aiSecurity.routingOverview.search')}
            className="app-text-body-sm min-w-0 flex-1 bg-transparent py-1.5 text-app-ink outline-none"
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t('admin.console.aiSecurity.routingOverview.search')}
            value={query}
          />
        </label>
        <select
          aria-label={t('admin.console.aiSecurity.routingOverview.routeFilter')}
          className={COMPACT_SELECT_CLASS}
          onChange={(event) =>
            setRouteFilter(event.target.value as RouteFilter)
          }
          value={routeFilter}
        >
          <option value="all">
            {t('admin.console.aiSecurity.routingOverview.allRoutes')}
          </option>
          <option value="local">
            {t('admin.console.aiSecurity.modelSettings.routes.local')}
          </option>
          <option value="external">
            {t('admin.console.aiSecurity.modelSettings.routes.external')}
          </option>
        </select>
        <Button
          aria-label={t('admin.console.usage.refresh')}
          disabled={loading || savingKey !== null}
          onClick={() => void load()}
          size="icon"
          title={t('admin.console.usage.refresh')}
          variant="secondary"
        >
          <RefreshCw size={14} />
        </Button>
      </div>

      <div className="max-h-[68vh] overflow-auto rounded-md border border-app-border bg-app-surface">
        <table className="w-full table-fixed border-collapse">
          <colgroup>
            <col className="w-[12%]" />
            <col className="w-[17%]" />
            <col className="w-[22%]" />
            <col className="w-[19%]" />
            <col className="w-[19%]" />
            <col className="w-[11%]" />
          </colgroup>
          <thead className="sticky top-0 z-10 bg-app-surface-sidebar shadow-[0_1px_0_var(--color-app-border)]">
            <tr>
              {[
                'app',
                'workload',
                'route',
                'model',
                'outputCaps',
                'actions',
              ].map((column) => (
                <th
                  className="app-text-overline whitespace-nowrap px-1.5 py-2 text-left text-app-ink/55"
                  key={column}
                  scope="col"
                >
                  {t(
                    `admin.console.aiSecurity.routingOverview.columns.${column}`,
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-app-border">
            {filteredWorkloads.map((workload) => {
              const draft =
                drafts[`${workload.app_id}:${workload.workload_id}`];
              if (!draft) return null;
              const ready = effectiveWorkloadReady(data, workload, draft);
              const readinessCode = effectiveReadinessCode(
                data,
                workload,
                draft,
              );
              const providerIds = data.providers
                .filter(
                  (provider) =>
                    provider.route_mode === draft.routeMode &&
                    (workload.allowed_providers.length === 0 ||
                      workload.allowed_providers.includes(
                        provider.provider_kind,
                      )),
                )
                .map((provider) => provider.provider_id);
              const roles =
                workload.model_roles.length > 0
                  ? workload.model_roles
                  : ['default'];
              const label = workload.label_key
                ? t(workload.label_key, { defaultValue: workload.workload_id })
                : workload.workload_id;
              const description = workload.description_key
                ? t(workload.description_key, {
                    defaultValue: workload.description,
                  })
                : workload.description;
              const capsValid = outputCapsValid(workload, draft);
              return (
                <tr
                  className="align-middle hover:bg-app-surface-hover"
                  key={`${workload.app_id}:${workload.workload_id}`}
                >
                  <td className="px-1.5 py-1.5">
                    <div className="space-y-0.5">
                      {(workload.app_ids.length > 0
                        ? workload.app_ids
                        : ['platform']
                      ).map((appId) => (
                        <div
                          className="app-text-caption line-clamp-2 font-semibold leading-4 text-app-ink/75"
                          key={appId}
                          title={t(`shell:apps.${appId}`, {
                            defaultValue: appId,
                          })}
                        >
                          {t(`shell:apps.${appId}`, { defaultValue: appId })}
                        </div>
                      ))}
                    </div>
                  </td>
                  <td className="px-1.5 py-1.5">
                    <div
                      className="app-text-body-sm truncate font-medium text-app-ink"
                      title={`${description}\n${workload.workload_id} · ${workload.task_kind}\n${workload.owner_domain}`}
                    >
                      {label}
                    </div>
                  </td>
                  <td className="px-1.5 py-1.5">
                    <div className="flex w-full items-center gap-0.5">
                      <select
                        aria-label={t(
                          'admin.console.aiSecurity.routingOverview.routeFor',
                          { name: label },
                        )}
                        className={`${COMPACT_SELECT_CLASS} min-w-0 flex-1`}
                        onChange={(event) => {
                          const routeMode = event.target.value as AiModelRoute;
                          const runtimeAdapterId =
                            workload.runtime_adapters.find((adapter) =>
                              adapter.allowed_routes.includes(routeMode),
                            )?.adapter_id ?? draft.runtimeAdapterId;
                          setDrafts((current) => ({
                            ...current,
                            [`${workload.app_id}:${workload.workload_id}`]: {
                              routeMode,
                              providerId: inheritedProviderId(
                                data,
                                workload,
                                routeMode,
                              ),
                              providerExplicit: false,
                              modelIds: {},
                              localMaxOutputK: draft.localMaxOutputK,
                              externalMaxOutputK: draft.externalMaxOutputK,
                              runtimeAdapterId,
                            },
                          }));
                        }}
                        value={draft.routeMode}
                      >
                        {workload.allowed_routes.map((route) => (
                          <option key={route} value={route}>
                            {t(
                              `admin.console.aiSecurity.modelSettings.routes.${route}`,
                            )}
                          </option>
                        ))}
                      </select>
                      {
                        <select
                          aria-label={t(
                            'admin.console.aiSecurity.routingOverview.providerFor',
                            { name: label },
                          )}
                          className={`${COMPACT_SELECT_CLASS} min-w-0 flex-1`}
                          onChange={(event) =>
                            setDrafts((current) => ({
                              ...current,
                              [`${workload.app_id}:${workload.workload_id}`]: {
                                ...draft,
                                providerId:
                                  event.target.value === '__inherit__'
                                    ? inheritedProviderId(
                                        data,
                                        workload,
                                        draft.routeMode,
                                      )
                                    : event.target.value,
                                providerExplicit:
                                  event.target.value !== '__inherit__',
                                modelIds: {},
                              },
                            }))
                          }
                          value={
                            draft.providerExplicit
                              ? draft.providerId
                              : '__inherit__'
                          }
                        >
                          <option value="__inherit__">
                            {t('admin.console.aiSecurity.llmDefaults.inherit')}{' '}
                            ·{' '}
                            {data.providers.find(
                              (provider) =>
                                provider.provider_id ===
                                inheritedProviderId(
                                  data,
                                  workload,
                                  draft.routeMode,
                                ),
                            )?.display_name ?? '—'}
                          </option>
                          {providerIds.map((providerId) => (
                            <option key={providerId} value={providerId}>
                              {data.providers.find(
                                (item) => item.provider_id === providerId,
                              )?.display_name ?? providerId}
                            </option>
                          ))}
                        </select>
                      }
                    </div>
                  </td>
                  <td className="px-1.5 py-1.5">
                    <div className="space-y-1">
                      {workload.execution_kind === 'agent' ? (
                        <select
                          aria-label={t(
                            'admin.console.aiSecurity.routingOverview.runtimeFor',
                            { name: label },
                          )}
                          className={COMPACT_SELECT_CLASS}
                          onChange={(event) => {
                            const runtimeAdapterId = event.target.value;
                            const adapter = workload.runtime_adapters.find(
                              (item) => item.adapter_id === runtimeAdapterId,
                            );
                            const routeMode = adapter?.allowed_routes.includes(
                              draft.routeMode,
                            )
                              ? draft.routeMode
                              : (adapter?.allowed_routes[0] ?? draft.routeMode);
                            const providerId = inheritedProviderId(
                              data,
                              workload,
                              routeMode,
                            );
                            setDrafts((current) => ({
                              ...current,
                              [`${workload.app_id}:${workload.workload_id}`]: {
                                ...draft,
                                runtimeAdapterId,
                                routeMode,
                                providerId,
                                providerExplicit: false,
                                modelIds: {},
                              },
                            }));
                          }}
                          value={draft.runtimeAdapterId}
                        >
                          {workload.runtime_adapters.map((adapter) => (
                            <option
                              key={adapter.adapter_id}
                              value={adapter.adapter_id}
                            >
                              {adapter.display_name}
                            </option>
                          ))}
                        </select>
                      ) : null}
                      {roles.map((role) => {
                        const models = modelsForWorkload(
                          data,
                          workload,
                          draft.providerId,
                        );
                        const value = draft.modelIds[role] ?? '';
                        const resolvedRoute = workload.resolved_routes.find(
                          (route) =>
                            route.model_role === role &&
                            route.provider_id === draft.providerId,
                        );
                        if (
                          models.length === 0 &&
                          resolvedRoute &&
                          workloadSelectionUnchanged(workload, draft)
                        ) {
                          return (
                            <div className="w-full" key={role}>
                              <div
                                className="app-text-body-sm truncate font-medium text-app-ink"
                                title={resolvedRoute.model_key}
                              >
                                {resolvedRoute.model_key}
                              </div>
                            </div>
                          );
                        }
                        return (
                          <select
                            aria-label={t(
                              'admin.console.aiSecurity.routingOverview.modelFor',
                              {
                                name: label,
                                role,
                              },
                            )}
                            className={COMPACT_SELECT_CLASS}
                            key={role}
                            onChange={(event) =>
                              setDrafts((current) => ({
                                ...current,
                                [`${workload.app_id}:${workload.workload_id}`]:
                                  {
                                    ...draft,
                                    modelIds: {
                                      ...draft.modelIds,
                                      [role]: event.target.value,
                                    },
                                  },
                              }))
                            }
                            value={value}
                          >
                            <option value="">
                              {t(
                                'admin.console.aiSecurity.llmDefaults.inherit',
                              )}{' '}
                              ·{' '}
                              {models.find(
                                (model) =>
                                  model.id ===
                                  selectedModelId(
                                    data,
                                    workload,
                                    {
                                      ...draft,
                                      modelIds: {
                                        ...draft.modelIds,
                                        [role]: '',
                                      },
                                    },
                                    role,
                                  ),
                              )?.model_key ?? '—'}
                            </option>
                            {models.map((model) => (
                              <option key={model.id} value={model.id}>
                                {model.display_name} · {model.model_key}
                              </option>
                            ))}
                          </select>
                        );
                      })}
                      {workload.resolved_routes.map((resolved) => (
                        <div
                          key={resolved.model_role}
                          className="app-text-caption text-app-ink/55"
                        >
                          {resolved.model_key} ·{' '}
                          {t(
                            `admin.console.aiSecurity.llmDefaults.sources.${resolved.connection_source}`,
                          )}
                        </div>
                      ))}
                      {!ready ? (
                        <div
                          className="app-text-caption w-full truncate text-app-danger-text"
                          title={readinessCode ?? undefined}
                        >
                          {t(
                            `admin.console.aiSecurity.routingOverview.readiness.${readinessLabelKey(
                              readinessCode,
                            )}`,
                            {
                              defaultValue:
                                readinessCode ??
                                t(
                                  'admin.console.aiSecurity.routingOverview.readiness.unknown',
                                ),
                            },
                          )}
                        </div>
                      ) : null}
                    </div>
                  </td>
                  <td className="px-1.5 py-1.5">
                    <div className="flex w-full items-center gap-0.5">
                      {(
                        [
                          ['local', 'localMaxOutputK'],
                          ['external', 'externalMaxOutputK'],
                        ] as const
                      )
                        .filter(([route]) =>
                          workload.allowed_routes.includes(route),
                        )
                        .map(([route, field]) => (
                          <label
                            className="flex min-w-0 flex-1 items-center gap-0.5"
                            key={route}
                          >
                            <span
                              className="app-text-overline text-app-ink/55"
                              title={t(
                                `admin.console.aiSecurity.modelSettings.routes.${route}`,
                              )}
                            >
                              {t(
                                `admin.console.aiSecurity.routingOverview.outputCapShort.${route}`,
                              )}
                            </span>
                            <input
                              aria-invalid={parseOutputK(draft[field]) === null}
                              aria-label={t(
                                'admin.console.aiSecurity.routingOverview.outputCapFor',
                                {
                                  name: label,
                                  route: t(
                                    `admin.console.aiSecurity.modelSettings.routes.${route}`,
                                  ),
                                },
                              )}
                              className={`${fieldClassName} h-8 min-w-0 flex-1 !px-1 py-1 text-center ${
                                parseOutputK(draft[field]) === null
                                  ? 'border-app-danger-border text-app-danger-text'
                                  : ''
                              }`}
                              max={MAX_OUTPUT_K}
                              min={MIN_OUTPUT_K}
                              onChange={(event) =>
                                setDrafts((current) => ({
                                  ...current,
                                  [`${workload.app_id}:${workload.workload_id}`]:
                                    {
                                      ...draft,
                                      [field]: event.target.value,
                                    },
                                }))
                              }
                              step={1}
                              type="number"
                              value={draft[field]}
                            />
                          </label>
                        ))}
                    </div>
                    {!capsValid ? (
                      <div className="app-text-caption mt-1 text-app-danger-text">
                        {t(
                          'admin.console.aiSecurity.routingOverview.outputCapInvalid',
                        )}
                      </div>
                    ) : null}
                  </td>
                  <td className="px-0.5 py-1.5">
                    <div className="flex items-center justify-end gap-0.5">
                      {workload.override ? (
                        <Button
                          className="!size-7 !min-h-7 !min-w-7 !p-0"
                          aria-label={t(
                            'admin.console.aiSecurity.modelSettings.workloads.reset',
                          )}
                          disabled={loading || savingKey !== null}
                          onClick={() => {
                            const version = workload.override?.version;
                            if (version === undefined) return;
                            void runMutation(
                              `${workload.workload_id}:reset`,
                              () =>
                                resetAdminAiModelWorkloadRoute(
                                  token,
                                  workload.workload_id,
                                  {
                                    expected_registry_digest:
                                      data.registry_digest,
                                    expected_version: version,
                                  },
                                  workload.app_id,
                                ),
                            );
                          }}
                          size="icon"
                          title={t(
                            'admin.console.aiSecurity.modelSettings.workloads.reset',
                          )}
                          variant="secondary"
                        >
                          <RotateCcw size={13} />
                        </Button>
                      ) : null}
                      {!workloadDraftUnchanged(workload, draft) ? (
                        <Button
                          className="!size-7 !min-h-7 !min-w-7 !p-0"
                          aria-label={t('common:actions.save')}
                          disabled={
                            !ready ||
                            !capsValid ||
                            loading ||
                            savingKey !== null
                          }
                          onClick={() => {
                            void runMutation(
                              `${workload.app_id}:${workload.workload_id}`,
                              () =>
                                updateAdminAiModelWorkloadRoute(
                                  token,
                                  workload.workload_id,
                                  buildLlmWorkloadUpdate(data, workload, draft),
                                  workload.app_id,
                                ),
                            );
                          }}
                          size="icon"
                          title={t('common:actions.save')}
                          variant="primary"
                        >
                          <Save size={14} />
                        </Button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {filteredWorkloads.length === 0 ? (
          <div className="p-4">
            <EmptyPanel
              description={t(
                'admin.console.aiSecurity.routingOverview.emptyDescription',
              )}
              title={t('admin.console.aiSecurity.routingOverview.emptyTitle')}
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}
