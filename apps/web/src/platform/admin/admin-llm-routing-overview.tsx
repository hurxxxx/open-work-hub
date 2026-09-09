import { RefreshCw, RotateCcw, Save, Search } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
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
  type AiModelProviderConfig,
  type AiModelRoute,
  type AiModelWorkload,
} from './admin-ai-model-settings-api';
import { EmptyPanel, FORM_FIELD_CLASS as fieldClassName } from './admin-shared';

interface WorkloadDraft {
  routeMode: AiModelRoute;
  providerId: string;
  modelIds: Record<string, string>;
  localMaxOutputK: string;
  externalMaxOutputK: string;
  runtimeAdapterId: string;
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

function defaultProviderId(
  workload: AiModelWorkload,
  routeMode: AiModelRoute,
  providers: AiModelProviderConfig[],
): string {
  if (routeMode === 'local') return 'local';
  const allowed = (
    workload.allowed_providers.length > 0
      ? workload.allowed_providers
      : providers.map((provider) => provider.provider_id)
  ).filter((providerId) => providerId !== 'local');
  return (
    allowed.find((providerId) =>
      providers.some(
        (provider) => provider.provider_id === providerId && provider.enabled,
      ),
    ) ??
    allowed[0] ??
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
      modelSupportsCapabilities(model, workload.required_capabilities),
  );
}

function selectedModelId(
  data: AdminAiModelSettings,
  workload: AiModelWorkload,
  draft: WorkloadDraft,
  role: string,
): string {
  const models = modelsForWorkload(data, workload, draft.providerId);
  const selected = draft.modelIds[role];
  if (selected && models.some((model) => model.id === selected)) {
    return selected;
  }
  const resolvedModel = workload.resolved_routes.find(
    (route) =>
      route.model_role === role && route.provider_id === draft.providerId,
  )?.model_key;
  const resolvedEntry = models.find(
    (model) => model.model_key === resolvedModel,
  );
  if (resolvedEntry) return resolvedEntry.id;
  const providerDefault = data.providers.find(
    (provider) => provider.provider_id === draft.providerId,
  )?.default_model_id;
  if (providerDefault && models.some((model) => model.id === providerDefault)) {
    return providerDefault;
  }
  return models[0]?.id ?? '';
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
        workload.workload_id,
        {
          routeMode,
          providerId:
            workload.override?.provider_id ??
            workload.resolved_routes[0]?.provider_id ??
            defaultProviderId(workload, routeMode, data.providers),
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
  const [query, setQuery] = useState('');
  const [routeFilter, setRouteFilter] = useState<RouteFilter>('all');

  const applySnapshot = useCallback((snapshot: AdminAiModelSettings) => {
    setData(snapshot);
    setDrafts(initialDrafts(snapshot));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      applySnapshot(await getAdminAiModelSettings(token));
    } catch {
      toast.error(t('admin.console.aiSecurity.modelSettings.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [applySnapshot, t, toast, token]);

  useEffect(() => {
    void load();
  }, [load]);

  const runMutation = useCallback(
    async (key: string, mutation: () => Promise<AdminAiModelSettings>) => {
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
          await load();
        } else {
          toast.error(
            error instanceof AdminAiModelSettingsApiError
              ? error.message
              : t('admin.console.aiSecurity.modelSettings.saveFailed'),
          );
        }
      } finally {
        setSavingKey(null);
      }
    },
    [applySnapshot, load, t, toast],
  );

  const routingWorkloads = useMemo(
    () => data?.workloads.filter(isConfigurableModelRoutingWorkload) ?? [],
    [data],
  );

  const filteredWorkloads = useMemo(() => {
    if (!data) return [];
    const normalizedQuery = query.trim().toLocaleLowerCase();
    return routingWorkloads.filter((workload) => {
      const draft = drafts[workload.workload_id];
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
        const draft = drafts[workload.workload_id];
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
              const draft = drafts[workload.workload_id];
              if (!draft) return null;
              const ready = effectiveWorkloadReady(data, workload, draft);
              const readinessCode = effectiveReadinessCode(
                data,
                workload,
                draft,
              );
              const providerIds =
                draft.routeMode === 'local'
                  ? ['local']
                  : (workload.allowed_providers.length > 0
                      ? workload.allowed_providers
                      : data.providers.map((provider) => provider.provider_id)
                    ).filter((providerId) => providerId !== 'local');
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
                  key={workload.workload_id}
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
                            [workload.workload_id]: {
                              routeMode,
                              providerId: defaultProviderId(
                                workload,
                                routeMode,
                                data.providers,
                              ),
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
                      {draft.routeMode === 'external' ? (
                        <select
                          aria-label={t(
                            'admin.console.aiSecurity.routingOverview.providerFor',
                            { name: label },
                          )}
                          className={`${COMPACT_SELECT_CLASS} min-w-0 flex-1`}
                          onChange={(event) =>
                            setDrafts((current) => ({
                              ...current,
                              [workload.workload_id]: {
                                ...draft,
                                providerId: event.target.value,
                                modelIds: {},
                              },
                            }))
                          }
                          value={draft.providerId}
                        >
                          {providerIds.map((providerId) => (
                            <option key={providerId} value={providerId}>
                              {data.providers.find(
                                (item) => item.provider_id === providerId,
                              )?.display_name ?? providerId}
                            </option>
                          ))}
                        </select>
                      ) : null}
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
                            const routeMode =
                              adapter?.allowed_routes[0] ?? draft.routeMode;
                            const providerId =
                              adapter?.allowed_providers[0] ??
                              defaultProviderId(
                                workload,
                                routeMode,
                                data.providers,
                              );
                            setDrafts((current) => ({
                              ...current,
                              [workload.workload_id]: {
                                ...draft,
                                runtimeAdapterId,
                                routeMode,
                                providerId,
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
                        const value = selectedModelId(
                          data,
                          workload,
                          draft,
                          role,
                        );
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
                                [workload.workload_id]: {
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
                                'admin.console.aiSecurity.modelSettings.models.selectModel',
                              )}
                            </option>
                            {models.map((model) => (
                              <option key={model.id} value={model.id}>
                                {model.display_name} · {model.model_key}
                              </option>
                            ))}
                          </select>
                        );
                      })}
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
                                  [workload.workload_id]: {
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
                          disabled={savingKey !== null}
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
                          disabled={!ready || !capsValid || savingKey !== null}
                          onClick={() => {
                            const modelIds = Object.fromEntries(
                              roles
                                .map((role) => [
                                  role,
                                  selectedModelId(data, workload, draft, role),
                                ])
                                .filter(([, modelId]) => Boolean(modelId)),
                            );
                            const localMaxOutputTokens = parseOutputK(
                              draft.localMaxOutputK,
                            );
                            const externalMaxOutputTokens = parseOutputK(
                              draft.externalMaxOutputK,
                            );
                            if (
                              localMaxOutputTokens === null ||
                              externalMaxOutputTokens === null
                            )
                              return;
                            void runMutation(workload.workload_id, () =>
                              updateAdminAiModelWorkloadRoute(
                                token,
                                workload.workload_id,
                                {
                                  expected_registry_digest:
                                    data.registry_digest,
                                  expected_version:
                                    workload.override?.version ?? null,
                                  route_mode: draft.routeMode,
                                  provider_id: draft.providerId || null,
                                  model_ids: modelIds,
                                  local_max_output_tokens: localMaxOutputTokens,
                                  external_max_output_tokens:
                                    externalMaxOutputTokens,
                                  runtime_adapter_id: draft.runtimeAdapterId,
                                },
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
