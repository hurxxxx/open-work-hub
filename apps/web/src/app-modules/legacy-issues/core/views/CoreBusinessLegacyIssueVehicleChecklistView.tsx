import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import {
  ArrowLeft,
  Boxes,
  ClipboardCheck,
  Loader2,
  RefreshCw,
} from 'lucide-react';
import { useToast } from '@ai-do/ui';

import { UserDateTime } from '@/src/components/date/UserDateTime';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { buildWorkspaceAppPath } from '@/src/platform/workspaces/workspace-utils';
import {
  fetchLegacyIssueVehicleChecklistModules,
  fetchLegacyIssueVehicleModels,
  type LegacyIssueVehicleChecklistModuleSummary,
  type LegacyIssueVehicleModel,
  type LegacyIssueVehicleStage,
} from '../api/legacy-issue-vehicle-api';
import {
  LEGACY_ISSUE_VIEWS,
  type LegacyIssueModuleViewKey,
} from '../legacy-issue-datasets';
import {
  LegacyIssuePageHeader,
  LegacyIssueToolbarButton,
} from './LegacyIssuePageParts';

type ChecklistListRouteScope = {
  stageId: string;
  vehicleModelId: string;
  workspaceSlug: string;
};

export function CoreBusinessLegacyIssueVehicleChecklistView() {
  const { workspaceSlug = '', vehicleModelId = '' } = useParams<{
    workspaceSlug: string;
    vehicleModelId?: string;
  }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const { token } = useAuth();
  const { t } = useTranslation(['apps', 'shell']);
  const toast = useToast();
  const [vehicles, setVehicles] = useState<LegacyIssueVehicleModel[]>([]);
  const [modules, setModules] = useState<
    LegacyIssueVehicleChecklistModuleSummary[]
  >([]);
  const [loadingVehicles, setLoadingVehicles] = useState(true);
  const [loadingModules, setLoadingModules] = useState(false);
  const vehicleRequestIdRef = useRef(0);
  const moduleRequestIdRef = useRef(0);
  const routeScopeRef = useRef<ChecklistListRouteScope>({
    stageId: '',
    vehicleModelId,
    workspaceSlug,
  });

  const selectedVehicle = useMemo(
    () => vehicles.find((vehicle) => vehicle.id === vehicleModelId) ?? null,
    [vehicleModelId, vehicles],
  );
  const requestedStageId = searchParams.get('stage_id');
  const selectedStage = useMemo(
    () => selectVehicleStage(selectedVehicle, requestedStageId),
    [requestedStageId, selectedVehicle],
  );
  const stageId = selectedStage?.id ?? '';
  routeScopeRef.current = { stageId, vehicleModelId, workspaceSlug };

  const selectStage = useCallback(
    (nextStageId: string) => {
      const next = new URLSearchParams(searchParams);
      next.set('stage_id', nextStageId);
      setSearchParams(next, { replace: true });
    },
    [searchParams, setSearchParams],
  );

  const loadVehicles = useCallback(async () => {
    if (!workspaceSlug || !token) return;
    const scope: ChecklistListRouteScope = {
      stageId,
      vehicleModelId,
      workspaceSlug,
    };
    const requestId = ++vehicleRequestIdRef.current;
    setLoadingVehicles(true);
    try {
      const response = await fetchLegacyIssueVehicleModels({
        token,
        workspaceSlug,
      });
      if (
        requestId !== vehicleRequestIdRef.current ||
        !sameChecklistListScope(routeScopeRef.current, scope)
      ) {
        return;
      }
      setVehicles(response.items);
    } catch (error) {
      if (
        requestId !== vehicleRequestIdRef.current ||
        !sameChecklistListScope(routeScopeRef.current, scope)
      ) {
        return;
      }
      const message = errorMessage(
        error,
        t('coreBusiness.vehicleChecklist.errors.vehicleLoadFailed'),
      );
      toast.error(message);
    } finally {
      if (
        requestId === vehicleRequestIdRef.current &&
        sameChecklistListScope(routeScopeRef.current, scope)
      ) {
        setLoadingVehicles(false);
      }
    }
  }, [stageId, t, toast, token, vehicleModelId, workspaceSlug]);

  const loadModules = useCallback(async () => {
    if (!workspaceSlug || !token || !vehicleModelId || !stageId) return;
    const scope: ChecklistListRouteScope = {
      stageId,
      vehicleModelId,
      workspaceSlug,
    };
    const requestId = ++moduleRequestIdRef.current;
    setLoadingModules(true);
    setModules([]);
    try {
      const response = await fetchLegacyIssueVehicleChecklistModules({
        stageId,
        token,
        vehicleModelId,
        workspaceSlug,
      });
      if (
        requestId !== moduleRequestIdRef.current ||
        !sameChecklistListScope(routeScopeRef.current, scope)
      ) {
        return;
      }
      setModules(response.items);
    } catch (error) {
      if (
        requestId !== moduleRequestIdRef.current ||
        !sameChecklistListScope(routeScopeRef.current, scope)
      ) {
        return;
      }
      const message = errorMessage(
        error,
        t('coreBusiness.vehicleChecklist.errors.moduleLoadFailed'),
      );
      toast.error(message);
    } finally {
      if (
        requestId === moduleRequestIdRef.current &&
        sameChecklistListScope(routeScopeRef.current, scope)
      ) {
        setLoadingModules(false);
      }
    }
  }, [stageId, t, toast, token, vehicleModelId, workspaceSlug]);

  useEffect(() => {
    vehicleRequestIdRef.current += 1;
    moduleRequestIdRef.current += 1;
    setVehicles([]);
    setModules([]);
    setLoadingVehicles(Boolean(token && workspaceSlug));
    setLoadingModules(false);
  }, [token, vehicleModelId, workspaceSlug]);

  useEffect(() => {
    void loadVehicles();
  }, [loadVehicles]);

  useEffect(() => {
    void loadModules();
  }, [loadModules]);

  useEffect(() => {
    if (
      !vehicleModelId ||
      loadingVehicles ||
      !selectedStage ||
      requestedStageId === selectedStage.id
    ) {
      return;
    }
    selectStage(selectedStage.id);
  }, [
    loadingVehicles,
    requestedStageId,
    selectStage,
    selectedStage,
    vehicleModelId,
  ]);

  if (!vehicleModelId) {
    return (
      <VehicleChecklistVehicleList
        loading={loadingVehicles}
        vehicles={vehicles}
        workspaceSlug={workspaceSlug}
        onReload={() => void loadVehicles()}
      />
    );
  }

  return (
    <VehicleChecklistModuleList
      loading={loadingVehicles || loadingModules}
      modules={modules}
      selectedStage={selectedStage}
      vehicle={selectedVehicle}
      vehicleModelId={vehicleModelId}
      workspaceSlug={workspaceSlug}
      onReload={() => {
        void loadVehicles();
        void loadModules();
      }}
      onSelectStage={selectStage}
    />
  );
}

function VehicleChecklistVehicleList({
  loading,
  onReload,
  vehicles,
  workspaceSlug,
}: {
  loading: boolean;
  onReload: () => void;
  vehicles: LegacyIssueVehicleModel[];
  workspaceSlug: string;
}) {
  const { t } = useTranslation(['apps', 'common']);
  return (
    <section className="flex min-h-full flex-col bg-app-bg">
      <LegacyIssuePageHeader
        eyebrow={t('coreBusiness.vehicleChecklist.eyebrow')}
        title={t('coreBusiness.vehicleChecklist.title')}
        actions={
          <LegacyIssueToolbarButton
            disabled={loading}
            icon={
              loading ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <RefreshCw size={16} />
              )
            }
            label={t('coreBusiness.vehicleChecklist.actions.reload')}
            onClick={onReload}
          />
        }
      />
      <div className="min-h-0 flex-1 overflow-auto">
        <table className="w-full border-collapse app-text-body-sm">
          <thead className="sticky top-0 bg-app-surface-sidebar text-left app-text-caption text-app-ink/55">
            <tr className="border-b border-app-border">
              <th className="px-4 py-2 font-semibold">
                {t('coreBusiness.vehicleChecklist.columns.vehicleCode')}
              </th>
              <th className="px-4 py-2 font-semibold">
                {t('coreBusiness.vehicleChecklist.columns.vehicleName')}
              </th>
              <th className="px-4 py-2 font-semibold">
                {t('coreBusiness.vehicleChecklist.columns.updatedAt')}
              </th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <ChecklistTableMessage
                colSpan={3}
                message={t('common:feedback.loading')}
              />
            ) : vehicles.length === 0 ? (
              <ChecklistTableMessage
                colSpan={3}
                message={t('coreBusiness.vehicleChecklist.emptyVehicles')}
              />
            ) : (
              vehicles.map((vehicle) => (
                <tr key={vehicle.id} className="border-b border-app-border">
                  <td className="px-4 py-2">
                    <Link
                      className="inline-flex items-center gap-2 font-medium text-app-accent hover:underline"
                      to={buildWorkspaceAppPath(
                        workspaceSlug,
                        'legacy-issues',
                        `/vehicle-checklists/${vehicle.id}`,
                      )}
                    >
                      <ClipboardCheck size={15} />
                      {vehicle.vehicle_code}
                    </Link>
                  </td>
                  <td className="px-4 py-2 text-app-ink/70">
                    {vehicle.vehicle_name || '-'}
                  </td>
                  <td className="px-4 py-2 text-app-ink/60">
                    <UserDateTime
                      value={vehicle.updated_at}
                      display="datetime"
                    />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function VehicleChecklistModuleList({
  loading,
  modules,
  onReload,
  onSelectStage,
  selectedStage,
  vehicle,
  vehicleModelId,
  workspaceSlug,
}: {
  loading: boolean;
  modules: LegacyIssueVehicleChecklistModuleSummary[];
  onReload: () => void;
  onSelectStage: (stageId: string) => void;
  selectedStage: LegacyIssueVehicleStage | null;
  vehicle: LegacyIssueVehicleModel | null;
  vehicleModelId: string;
  workspaceSlug: string;
}) {
  const { t } = useTranslation(['apps', 'common', 'shell']);
  return (
    <section className="flex min-h-full flex-col bg-app-bg">
      <LegacyIssuePageHeader
        eyebrow={t('coreBusiness.vehicleChecklist.modules.eyebrow')}
        title={
          vehicle
            ? formatVehicleModelTitle(vehicle)
            : t('coreBusiness.vehicleChecklist.modules.title')
        }
        actions={
          <>
            <Link
              className="app-control h-9 px-3"
              to={buildWorkspaceAppPath(
                workspaceSlug,
                'legacy-issues',
                '/vehicle-checklists',
              )}
            >
              <ArrowLeft size={16} />
              {t('coreBusiness.vehicleChecklist.actions.backToVehicles')}
            </Link>
            <LegacyIssueToolbarButton
              disabled={loading}
              icon={
                loading ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <RefreshCw size={16} />
                )
              }
              label={t('coreBusiness.vehicleChecklist.actions.reload')}
              onClick={onReload}
            />
          </>
        }
      />
      <VehicleStageTabs
        selectedStage={selectedStage}
        stages={orderedVehicleStages(vehicle)}
        onSelect={onSelectStage}
      />
      <div className="min-h-0 flex-1 overflow-auto">
        <table className="w-full border-collapse app-text-body-sm">
          <thead className="sticky top-0 bg-app-surface-sidebar text-left app-text-caption text-app-ink/55">
            <tr className="border-b border-app-border">
              <th className="px-4 py-2 font-semibold">
                {t('coreBusiness.vehicleChecklist.columns.module')}
              </th>
              <th className="px-4 py-2 font-semibold">
                {t('coreBusiness.vehicleChecklist.columns.latestMaster')}
              </th>
              <th className="px-4 py-2 font-semibold">
                {t('coreBusiness.vehicleChecklist.columns.latestChecklist')}
              </th>
              <th className="px-4 py-2 font-semibold">
                {t('coreBusiness.vehicleChecklist.columns.status')}
              </th>
              <th className="px-4 py-2 font-semibold">
                {t('coreBusiness.vehicleChecklist.columns.rowCount')}
              </th>
              <th className="px-4 py-2 font-semibold">
                {t('coreBusiness.vehicleChecklist.columns.updatedAt')}
              </th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <ChecklistTableMessage
                colSpan={6}
                message={t('common:feedback.loading')}
              />
            ) : modules.length === 0 ? (
              <ChecklistTableMessage
                colSpan={6}
                message={t('coreBusiness.vehicleChecklist.modules.empty')}
              />
            ) : (
              modules.map((module) => {
                const latestChecklist = module.latest_checklist;
                return (
                  <tr
                    key={module.module_key}
                    className="border-b border-app-border"
                  >
                    <td className="px-4 py-2">
                      <Link
                        className="inline-flex items-center gap-2 font-medium text-app-accent hover:underline"
                        to={buildWorkspaceAppPath(
                          workspaceSlug,
                          'legacy-issues',
                          vehicleChecklistModulePath({
                            moduleKey: module.module_key,
                            stageId: selectedStage?.id ?? '',
                            vehicleModelId,
                          }),
                        )}
                      >
                        <Boxes size={15} />
                        {vehicleChecklistModuleLabel(module.module_key, t)}
                      </Link>
                    </td>
                    <td className="px-4 py-2 text-app-ink/70">
                      {formatMasterRevision(
                        module.latest_master_revision?.revision_no,
                        t,
                      )}
                    </td>
                    <td className="px-4 py-2 text-app-ink/70">
                      {latestChecklist ? (
                        <Link
                          className="font-medium text-app-accent hover:underline"
                          to={buildWorkspaceAppPath(
                            workspaceSlug,
                            'legacy-issues',
                            vehicleChecklistModulePath({
                              checklistId: latestChecklist.id,
                              moduleKey: module.module_key,
                              stageId: selectedStage?.id ?? '',
                              vehicleModelId,
                            }),
                          )}
                        >
                          {formatMasterRevision(
                            latestChecklist.source_master_revision_no,
                            t,
                          )}
                        </Link>
                      ) : (
                        '-'
                      )}
                    </td>
                    <td className="px-4 py-2 text-app-ink/70">
                      {latestChecklist
                        ? t(
                            `coreBusiness.vehicleChecklist.revisionStatus.${latestChecklist.status}`,
                            { defaultValue: latestChecklist.status },
                          )
                        : '-'}
                    </td>
                    <td className="px-4 py-2 text-app-ink/70">
                      {latestChecklist?.row_count ?? '-'}
                    </td>
                    <td className="px-4 py-2 text-app-ink/60">
                      {latestChecklist ? (
                        <UserDateTime
                          value={latestChecklist.updated_at}
                          display="datetime"
                        />
                      ) : (
                        '-'
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function VehicleStageTabs({
  onSelect,
  selectedStage,
  stages,
}: {
  onSelect: (stageId: string) => void;
  selectedStage: LegacyIssueVehicleStage | null;
  stages: LegacyIssueVehicleStage[];
}) {
  const { t } = useTranslation(['apps']);
  return (
    <div className="border-b border-app-border bg-app-surface-sidebar px-4 pt-2">
      <div
        aria-label={t('coreBusiness.vehicleChecklist.stages.label')}
        className="flex flex-wrap gap-1"
        role="tablist"
      >
        {stages.map((stage) => {
          const active = stage.id === selectedStage?.id;
          return (
            <button
              aria-selected={active}
              className={
                active
                  ? 'rounded-t-md border border-b-0 border-app-border bg-app-bg px-4 py-2 app-text-body-sm font-semibold text-app-accent'
                  : 'rounded-t-md border border-transparent px-4 py-2 app-text-body-sm font-medium text-app-ink/55 hover:bg-app-surface-hover hover:text-app-ink'
              }
              key={stage.id}
              role="tab"
              type="button"
              onClick={() => onSelect(stage.id)}
            >
              {stage.name}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function ChecklistTableMessage({
  colSpan,
  message,
}: {
  colSpan: number;
  message: string;
}) {
  return (
    <tr>
      <td className="px-4 py-6 text-app-ink/55" colSpan={colSpan}>
        {message}
      </td>
    </tr>
  );
}

function sameChecklistListScope(
  current: ChecklistListRouteScope,
  expected: ChecklistListRouteScope,
): boolean {
  return (
    current.workspaceSlug === expected.workspaceSlug &&
    current.vehicleModelId === expected.vehicleModelId &&
    current.stageId === expected.stageId
  );
}

function orderedVehicleStages(
  vehicle: LegacyIssueVehicleModel | null,
): LegacyIssueVehicleStage[] {
  return [...(vehicle?.stages ?? [])].sort(
    (left, right) => left.sequence_no - right.sequence_no,
  );
}

function selectVehicleStage(
  vehicle: LegacyIssueVehicleModel | null,
  requestedStageId: string | null,
): LegacyIssueVehicleStage | null {
  const stages = orderedVehicleStages(vehicle);
  return (
    stages.find((stage) => stage.id === requestedStageId) ??
    stages.at(-1) ??
    null
  );
}

function vehicleChecklistModulePath({
  checklistId,
  moduleKey,
  stageId,
  vehicleModelId,
}: {
  checklistId?: string;
  moduleKey: string;
  stageId: string;
  vehicleModelId: string;
}): string {
  const params = new URLSearchParams();
  if (stageId) params.set('stage_id', stageId);
  if (checklistId) params.set('checklist_id', checklistId);
  const query = params.toString();
  return `/vehicle-checklists/${vehicleModelId}/${moduleKey}${
    query ? `?${query}` : ''
  }`;
}

export function formatVehicleModelTitle(
  vehicle: LegacyIssueVehicleModel,
): string {
  return vehicle.vehicle_name
    ? `${vehicle.vehicle_code} · ${vehicle.vehicle_name}`
    : vehicle.vehicle_code;
}

export function vehicleChecklistModuleLabel(
  moduleKey: string,
  t: ReturnType<typeof useTranslation>['t'],
): string {
  if (moduleKey in LEGACY_ISSUE_VIEWS) {
    const view = LEGACY_ISSUE_VIEWS[moduleKey as LegacyIssueModuleViewKey];
    const moduleLabel = t(`nav.${view.navItemId}`, { ns: 'shell' });
    const parentNavCategoryId =
      'parentNavCategoryId' in view ? view.parentNavCategoryId : null;
    return parentNavCategoryId
      ? `${t(`categories.${parentNavCategoryId}`, { ns: 'shell' })} / ${moduleLabel}`
      : moduleLabel;
  }
  return moduleKey;
}

function formatMasterRevision(
  revisionNo: number | null | undefined,
  t: ReturnType<typeof useTranslation>['t'],
): string {
  if (revisionNo == null) return '-';
  return t('coreBusiness.vehicleChecklist.summaryRevision', {
    revision: revisionNo,
  });
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}
