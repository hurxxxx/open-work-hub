import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
} from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import {
  Layers3,
  Loader2,
  Plus,
  Power,
  RefreshCw,
  Save,
  Trash2,
} from 'lucide-react';
import { Dialog, useConfirm, useToast } from '@open-alm/ui';

import { UserDateTime } from '@/src/components/date/UserDateTime';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { hasWorkspaceAdminAccess } from '@/src/platform/auth/auth-api';
import {
  createLegacyIssueVehicleModel,
  createLegacyIssueVehicleStage,
  deleteLegacyIssueVehicleModel,
  fetchLegacyIssueVehicleModels,
  permanentlyDeleteLegacyIssueVehicleModel,
  updateLegacyIssueVehicleModel,
  updateLegacyIssueVehicleStage,
  type LegacyIssueVehicleModel,
  type LegacyIssueVehicleStage,
} from '../api/legacy-issue-vehicle-api';
import {
  LegacyIssuePageHeader,
  LegacyIssueToolbarButton,
} from './LegacyIssuePageParts';

export function CoreBusinessLegacyIssueVehicleManagementView() {
  const { workspaceSlug = '' } = useParams<{ workspaceSlug: string }>();
  const { token, user } = useAuth();
  const { t } = useTranslation(['apps', 'common']);
  const toast = useToast();
  const { confirm, confirmDialog } = useConfirm();
  const canManage = hasWorkspaceAdminAccess(user, workspaceSlug);
  const [items, setItems] = useState<LegacyIssueVehicleModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [createCode, setCreateCode] = useState('');
  const [createName, setCreateName] = useState('');
  const [createNotes, setCreateNotes] = useState('');
  const [createInitialStage, setCreateInitialStage] = useState('');
  const [drafts, setDrafts] = useState<Record<string, VehicleModelDraft>>({});
  const [stageDialogVehicleId, setStageDialogVehicleId] = useState<
    string | null
  >(null);
  const [stageName, setStageName] = useState('');
  const [savingStage, setSavingStage] = useState(false);
  const [savingStageId, setSavingStageId] = useState<string | null>(null);
  const [stageNameDrafts, setStageNameDrafts] = useState<
    Record<string, string>
  >({});

  const loadItems = useCallback(async () => {
    if (!workspaceSlug || !token) return;
    setLoading(true);
    try {
      const response = await fetchLegacyIssueVehicleModels({
        includeInactive: true,
        token,
        workspaceSlug,
      });
      setItems(response.items);
      setDrafts(
        Object.fromEntries(
          response.items.map((item) => [item.id, draftFromVehicleModel(item)]),
        ),
      );
    } catch (loadError) {
      toast.error(
        errorMessage(
          loadError,
          t('coreBusiness.vehicleManagement.errors.loadFailed'),
        ),
      );
    } finally {
      setLoading(false);
    }
  }, [t, toast, token, workspaceSlug]);

  useEffect(() => {
    void loadItems();
  }, [loadItems]);

  const activeCount = useMemo(
    () => items.filter((item) => item.active).length,
    [items],
  );

  async function createItem(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const vehicleCode = createCode.trim();
    const initialStageName = createInitialStage.trim();
    if (!vehicleCode || !initialStageName || !workspaceSlug || !token) return;
    setSavingId('create');
    try {
      await createLegacyIssueVehicleModel({
        initialStageName,
        notes: nullableTrim(createNotes),
        token,
        vehicleCode,
        vehicleName: nullableTrim(createName),
        workspaceSlug,
      });
      setCreateCode('');
      setCreateName('');
      setCreateNotes('');
      setCreateInitialStage('');
      toast.success(t('coreBusiness.vehicleManagement.status.created'));
      await loadItems();
    } catch (createError) {
      toast.error(
        errorMessage(
          createError,
          t('coreBusiness.vehicleManagement.errors.saveFailed'),
        ),
      );
    } finally {
      setSavingId(null);
    }
  }

  async function addStage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = stageName.trim();
    if (
      !workspaceSlug ||
      !token ||
      !canManage ||
      !stageDialogVehicleId ||
      !name ||
      savingStage
    ) {
      return;
    }
    setSavingStage(true);
    try {
      await createLegacyIssueVehicleStage({
        name,
        token,
        vehicleModelId: stageDialogVehicleId,
        workspaceSlug,
      });
      toast.success(
        t('coreBusiness.vehicleManagement.status.stageCreated', { name }),
      );
      setStageDialogVehicleId(null);
      setStageName('');
      await loadItems();
    } catch (stageError) {
      toast.error(
        errorMessage(
          stageError,
          t('coreBusiness.vehicleManagement.errors.stageCreateFailed'),
        ),
      );
    } finally {
      setSavingStage(false);
    }
  }

  async function renameStage(stage: LegacyIssueVehicleStage) {
    const name = (stageNameDrafts[stage.id] ?? stage.name).trim();
    if (
      !workspaceSlug ||
      !token ||
      !canManage ||
      !stageDialogVehicleId ||
      !name ||
      name === stage.name ||
      isDuplicateStageName(stageDialogVehicle, name, stage.id) ||
      savingStage ||
      savingStageId
    ) {
      return;
    }
    setSavingStageId(stage.id);
    try {
      await updateLegacyIssueVehicleStage({
        name,
        stageId: stage.id,
        token,
        vehicleModelId: stageDialogVehicleId,
        workspaceSlug,
      });
      toast.success(
        t('coreBusiness.vehicleManagement.status.stageRenamed', { name }),
      );
      setStageNameDrafts((current) => ({
        ...current,
        [stage.id]: name,
      }));
      await loadItems();
    } catch (stageError) {
      toast.error(
        errorMessage(
          stageError,
          t('coreBusiness.vehicleManagement.errors.stageRenameFailed'),
        ),
      );
    } finally {
      setSavingStageId(null);
    }
  }

  function setStageDialogOpen(open: boolean) {
    if (savingStage || savingStageId) return;
    if (!open) {
      setStageDialogVehicleId(null);
      setStageName('');
      setStageNameDrafts({});
    }
  }

  async function saveItem(item: LegacyIssueVehicleModel) {
    if (!workspaceSlug || !token || !canManage) return;
    const draft = drafts[item.id] ?? draftFromVehicleModel(item);
    const vehicleCode = draft.vehicleCode.trim();
    if (!vehicleCode) return;
    setSavingId(item.id);
    try {
      await updateLegacyIssueVehicleModel({
        active: item.active,
        notes: nullableTrim(draft.notes),
        token,
        vehicleCode,
        vehicleName: nullableTrim(draft.vehicleName),
        vehicleModelId: item.id,
        workspaceSlug,
      });
      toast.success(t('coreBusiness.vehicleManagement.status.saved'));
      await loadItems();
    } catch (saveError) {
      toast.error(
        errorMessage(
          saveError,
          t('coreBusiness.vehicleManagement.errors.saveFailed'),
        ),
      );
    } finally {
      setSavingId(null);
    }
  }

  async function setActive(item: LegacyIssueVehicleModel, active: boolean) {
    if (!workspaceSlug || !token || !canManage) return;
    setSavingId(item.id);
    try {
      await updateLegacyIssueVehicleModel({
        active,
        token,
        vehicleModelId: item.id,
        workspaceSlug,
      });
      toast.success(t('coreBusiness.vehicleManagement.status.saved'));
      await loadItems();
    } catch (saveError) {
      toast.error(
        errorMessage(
          saveError,
          t('coreBusiness.vehicleManagement.errors.saveFailed'),
        ),
      );
    } finally {
      setSavingId(null);
    }
  }

  async function deleteItem(item: LegacyIssueVehicleModel) {
    if (!workspaceSlug || !token || !canManage) return;
    if (
      !window.confirm(t('coreBusiness.vehicleManagement.confirmDeactivate'))
    ) {
      return;
    }
    setSavingId(item.id);
    try {
      await deleteLegacyIssueVehicleModel({
        token,
        vehicleModelId: item.id,
        workspaceSlug,
      });
      toast.success(t('coreBusiness.vehicleManagement.status.deactivated'));
      await loadItems();
    } catch (deleteError) {
      toast.error(
        errorMessage(
          deleteError,
          t('coreBusiness.vehicleManagement.errors.deleteFailed'),
        ),
      );
    } finally {
      setSavingId(null);
    }
  }

  async function permanentlyDeleteItem(item: LegacyIssueVehicleModel) {
    if (
      !workspaceSlug ||
      !token ||
      !canManage ||
      item.generated_checklist_count !== 0
    ) {
      return;
    }
    const confirmed = await confirm({
      cancelLabel: t('common:actions.cancel'),
      confirmLabel: t(
        'coreBusiness.vehicleManagement.confirmPermanentDelete.confirm',
      ),
      description: t(
        'coreBusiness.vehicleManagement.confirmPermanentDelete.description',
        { vehicle: vehicleModelLabel(item) },
      ),
      title: t('coreBusiness.vehicleManagement.confirmPermanentDelete.title'),
      variant: 'danger',
    });
    if (!confirmed) return;
    setSavingId(item.id);
    try {
      await permanentlyDeleteLegacyIssueVehicleModel({
        token,
        vehicleModelId: item.id,
        workspaceSlug,
      });
      toast.success(
        t('coreBusiness.vehicleManagement.status.permanentlyDeleted'),
      );
      await loadItems();
    } catch (deleteError) {
      toast.error(
        errorMessage(
          deleteError,
          t('coreBusiness.vehicleManagement.errors.permanentDeleteFailed'),
        ),
      );
    } finally {
      setSavingId(null);
    }
  }

  function updateDraft(
    item: LegacyIssueVehicleModel,
    key: keyof VehicleModelDraft,
    value: string,
  ) {
    setDrafts((current) => ({
      ...current,
      [item.id]: {
        ...(current[item.id] ?? draftFromVehicleModel(item)),
        [key]: value,
      },
    }));
  }

  const stageDialogVehicle =
    items.find((item) => item.id === stageDialogVehicleId) ?? null;
  const normalizedStageName = stageName.trim().toLocaleLowerCase();
  const stageNameAlreadyExists = Boolean(
    normalizedStageName &&
      stageDialogVehicle?.stages?.some(
        (stage) =>
          stage.name.trim().toLocaleLowerCase() === normalizedStageName,
      ),
  );
  const stageDialogBusy = savingStage || Boolean(savingStageId);

  return (
    <section className="flex min-h-full flex-col bg-app-bg">
      {confirmDialog}
      <Dialog
        actions={
          <>
            <button
              className="app-control h-9 px-3"
              disabled={stageDialogBusy}
              type="button"
              onClick={() => setStageDialogOpen(false)}
            >
              {t('common:actions.cancel')}
            </button>
            <button
              className="app-control h-9 border-app-accent bg-app-accent px-3 text-app-accent-fg hover:bg-app-accent/90"
              disabled={
                stageDialogBusy || !stageName.trim() || stageNameAlreadyExists
              }
              form="legacy-issue-vehicle-stage-form"
              type="submit"
            >
              {savingStage ? (
                <Loader2 size={15} className="animate-spin" />
              ) : (
                <Plus size={15} />
              )}
              {t('coreBusiness.vehicleManagement.stageDialog.add')}
            </button>
          </>
        }
        closeLabel={t('common:actions.close')}
        description={t(
          'coreBusiness.vehicleManagement.stageDialog.description',
        )}
        open={Boolean(stageDialogVehicle)}
        title={t('coreBusiness.vehicleManagement.stageDialog.title', {
          vehicle: stageDialogVehicle
            ? vehicleModelLabel(stageDialogVehicle)
            : '',
        })}
        onOpenChange={setStageDialogOpen}
      >
        <form
          className="grid gap-4"
          id="legacy-issue-vehicle-stage-form"
          onSubmit={addStage}
        >
          <div>
            <p className="app-text-caption font-semibold text-app-ink/60">
              {t('coreBusiness.vehicleManagement.stageDialog.currentStages')}
            </p>
            <div className="mt-2 grid gap-2">
              {orderedVehicleStages(stageDialogVehicle).map((stage) => {
                const draftName = stageNameDrafts[stage.id] ?? stage.name;
                const normalizedDraftName = draftName.trim();
                const duplicate = isDuplicateStageName(
                  stageDialogVehicle,
                  normalizedDraftName,
                  stage.id,
                );
                return (
                  <div className="flex items-center gap-2" key={stage.id}>
                    <span className="min-w-8 rounded-full border border-app-border bg-app-surface-sidebar px-2 py-1 text-center app-text-caption font-medium text-app-ink">
                      {stage.sequence_no}
                    </span>
                    <label
                      className="sr-only"
                      htmlFor={`stage-name-${stage.id}`}
                    >
                      {t(
                        'coreBusiness.vehicleManagement.stageDialog.editStageLabel',
                        { name: stage.name },
                      )}
                    </label>
                    <input
                      className="app-input h-9 min-w-0 flex-1"
                      disabled={stageDialogBusy}
                      id={`stage-name-${stage.id}`}
                      value={draftName}
                      onChange={(event) =>
                        setStageNameDrafts((current) => ({
                          ...current,
                          [stage.id]: event.target.value,
                        }))
                      }
                    />
                    <button
                      className="app-control h-9 px-3"
                      disabled={
                        stageDialogBusy ||
                        !normalizedDraftName ||
                        normalizedDraftName === stage.name ||
                        duplicate
                      }
                      type="button"
                      onClick={() => void renameStage(stage)}
                    >
                      {savingStageId === stage.id ? (
                        <Loader2 size={14} className="animate-spin" />
                      ) : (
                        <Save size={14} />
                      )}
                      {t('coreBusiness.vehicleManagement.stageDialog.saveName')}
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
          <label className="grid gap-1.5" htmlFor="legacy-issue-stage-name">
            <span className="app-text-caption font-semibold text-app-ink/60">
              {t('coreBusiness.vehicleManagement.stageDialog.stageName')}
            </span>
            <input
              autoFocus
              className="app-input h-9"
              disabled={stageDialogBusy}
              id="legacy-issue-stage-name"
              placeholder={t(
                'coreBusiness.vehicleManagement.stageDialog.stageNamePlaceholder',
              )}
              value={stageName}
              onChange={(event) => setStageName(event.target.value)}
            />
          </label>
          {stageNameAlreadyExists ? (
            <p className="app-text-caption text-app-danger" role="alert">
              {t('coreBusiness.vehicleManagement.stageDialog.duplicateStage')}
            </p>
          ) : null}
        </form>
      </Dialog>
      <LegacyIssuePageHeader
        eyebrow={t('coreBusiness.vehicleManagement.eyebrow')}
        title={t('coreBusiness.vehicleManagement.title')}
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
            label={t('coreBusiness.vehicleManagement.actions.reload')}
            onClick={() => void loadItems()}
          />
        }
      />
      <div className="border-b border-app-border px-4 py-3">
        <form
          className="flex flex-wrap items-center gap-2"
          onSubmit={createItem}
        >
          <label
            className="app-text-caption font-semibold text-app-ink/60"
            htmlFor="legacy-issue-vehicle-code"
          >
            {t('coreBusiness.vehicleManagement.form.vehicleCode')}
          </label>
          <input
            id="legacy-issue-vehicle-code"
            className="app-input h-9 min-w-56"
            disabled={savingId === 'create'}
            value={createCode}
            onChange={(event) => setCreateCode(event.target.value)}
            placeholder={t(
              'coreBusiness.vehicleManagement.form.vehicleCodePlaceholder',
            )}
          />
          <label
            className="app-text-caption font-semibold text-app-ink/60"
            htmlFor="legacy-issue-vehicle-name"
          >
            {t('coreBusiness.vehicleManagement.form.vehicleName')}
          </label>
          <input
            id="legacy-issue-vehicle-name"
            className="app-input h-9 min-w-56"
            disabled={savingId === 'create'}
            value={createName}
            onChange={(event) => setCreateName(event.target.value)}
            placeholder={t(
              'coreBusiness.vehicleManagement.form.vehicleNamePlaceholder',
            )}
          />
          <label
            className="app-text-caption font-semibold text-app-ink/60"
            htmlFor="legacy-issue-vehicle-notes"
          >
            {t('coreBusiness.vehicleManagement.form.notes')}
          </label>
          <input
            id="legacy-issue-vehicle-notes"
            className="app-input h-9 min-w-64"
            disabled={savingId === 'create'}
            value={createNotes}
            onChange={(event) => setCreateNotes(event.target.value)}
            placeholder={t(
              'coreBusiness.vehicleManagement.form.notesPlaceholder',
            )}
          />
          <label
            className="app-text-caption font-semibold text-app-ink/60"
            htmlFor="legacy-issue-vehicle-initial-stage"
          >
            {t('coreBusiness.vehicleManagement.form.initialStage')}
          </label>
          <input
            id="legacy-issue-vehicle-initial-stage"
            className="app-input h-9 min-w-36"
            disabled={savingId === 'create'}
            value={createInitialStage}
            onChange={(event) => setCreateInitialStage(event.target.value)}
            placeholder={t(
              'coreBusiness.vehicleManagement.form.initialStagePlaceholder',
            )}
          />
          <LegacyIssueToolbarButton
            disabled={
              !createCode.trim() ||
              !createInitialStage.trim() ||
              savingId === 'create'
            }
            icon={
              savingId === 'create' ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Plus size={16} />
              )
            }
            label={t('coreBusiness.vehicleManagement.actions.create')}
            type="submit"
          />
        </form>
      </div>
      <div className="border-b border-app-border px-4 py-2 app-text-caption text-app-ink/55">
        {t('coreBusiness.vehicleManagement.summary', {
          active: activeCount,
          total: items.length,
        })}
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        <table className="w-full border-collapse app-text-body-sm">
          <thead className="sticky top-0 bg-app-surface-sidebar text-left app-text-caption text-app-ink/55">
            <tr className="border-b border-app-border">
              <th className="px-4 py-2 font-semibold">
                {t('coreBusiness.vehicleManagement.columns.vehicleCode')}
              </th>
              <th className="px-4 py-2 font-semibold">
                {t('coreBusiness.vehicleManagement.columns.vehicleName')}
              </th>
              <th className="px-4 py-2 font-semibold">
                {t('coreBusiness.vehicleManagement.columns.notes')}
              </th>
              <th className="px-4 py-2 font-semibold">
                {t('coreBusiness.vehicleManagement.columns.stages')}
              </th>
              <th className="px-4 py-2 font-semibold">
                {t('coreBusiness.vehicleManagement.columns.status')}
              </th>
              <th className="px-4 py-2 font-semibold">
                {t('coreBusiness.vehicleManagement.columns.updatedAt')}
              </th>
              <th className="px-4 py-2 text-right font-semibold">
                {t('coreBusiness.vehicleManagement.columns.actions')}
              </th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td className="px-4 py-6 text-app-ink/55" colSpan={7}>
                  {t('common:feedback.loading')}
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td className="px-4 py-6 text-app-ink/55" colSpan={7}>
                  {t('coreBusiness.vehicleManagement.empty')}
                </td>
              </tr>
            ) : (
              items.map((item) => (
                <tr key={item.id} className="border-b border-app-border">
                  <td className="px-4 py-2">
                    <input
                      className="app-input h-8 w-full max-w-sm"
                      disabled={!canManage || savingId === item.id}
                      value={drafts[item.id]?.vehicleCode ?? item.vehicle_code}
                      onChange={(event) =>
                        updateDraft(item, 'vehicleCode', event.target.value)
                      }
                    />
                  </td>
                  <td className="px-4 py-2">
                    <input
                      className="app-input h-8 w-full max-w-sm"
                      disabled={!canManage || savingId === item.id}
                      value={
                        drafts[item.id]?.vehicleName ?? item.vehicle_name ?? ''
                      }
                      onChange={(event) =>
                        updateDraft(item, 'vehicleName', event.target.value)
                      }
                    />
                  </td>
                  <td className="px-4 py-2">
                    <input
                      className="app-input h-8 w-full min-w-52"
                      disabled={!canManage || savingId === item.id}
                      value={drafts[item.id]?.notes ?? item.notes ?? ''}
                      onChange={(event) =>
                        updateDraft(item, 'notes', event.target.value)
                      }
                    />
                  </td>
                  <td className="px-4 py-2">
                    <div className="flex min-w-32 flex-wrap gap-1.5">
                      {orderedVehicleStages(item).map((stage) => (
                        <span
                          className="rounded-full border border-app-border bg-app-surface-sidebar px-2 py-0.5 app-text-caption font-medium text-app-ink"
                          key={stage.id}
                        >
                          {stage.name}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="px-4 py-2">
                    <span
                      className={
                        item.active
                          ? 'inline-flex rounded-full bg-app-success/10 px-2 py-1 app-text-caption font-medium text-app-success'
                          : 'inline-flex rounded-full bg-app-surface-hover px-2 py-1 app-text-caption font-medium text-app-ink/55'
                      }
                    >
                      {item.active
                        ? t('coreBusiness.vehicleManagement.status.active')
                        : t('coreBusiness.vehicleManagement.status.inactive')}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-app-ink/60">
                    <UserDateTime value={item.updated_at} display="datetime" />
                  </td>
                  <td className="px-4 py-2">
                    <div className="flex flex-col items-end gap-1">
                      <div className="flex justify-end gap-1">
                        <button
                          className="app-control h-8 px-2"
                          disabled={!canManage || savingId === item.id}
                          type="button"
                          onClick={() => void saveItem(item)}
                        >
                          {savingId === item.id ? (
                            <Loader2 size={14} className="animate-spin" />
                          ) : (
                            <Save size={14} />
                          )}
                          {t('coreBusiness.vehicleManagement.actions.save')}
                        </button>
                        <button
                          className={
                            item.active
                              ? 'app-control h-8 px-2 text-app-danger'
                              : 'app-control h-8 px-2 text-app-accent'
                          }
                          disabled={!canManage || savingId === item.id}
                          type="button"
                          onClick={() =>
                            void (item.active
                              ? deleteItem(item)
                              : setActive(item, true))
                          }
                        >
                          <Power size={14} />
                          {t(
                            item.active
                              ? 'coreBusiness.vehicleManagement.actions.deactivate'
                              : 'coreBusiness.vehicleManagement.actions.activate',
                          )}
                        </button>
                        <button
                          className="app-control h-8 px-2"
                          disabled={!canManage || savingId === item.id}
                          type="button"
                          onClick={() => {
                            setStageDialogVehicleId(item.id);
                            setStageName('');
                            setStageNameDrafts(
                              Object.fromEntries(
                                (item.stages ?? []).map((stage) => [
                                  stage.id,
                                  stage.name,
                                ]),
                              ),
                            );
                          }}
                        >
                          <Layers3 size={14} />
                          {t(
                            'coreBusiness.vehicleManagement.actions.manageStages',
                          )}
                        </button>
                        {canManage ? (
                          <button
                            className="app-control h-8 border-app-danger/35 px-2 text-app-danger"
                            disabled={
                              savingId === item.id ||
                              item.generated_checklist_count !== 0
                            }
                            title={
                              item.generated_checklist_count > 0
                                ? t(
                                    'coreBusiness.vehicleManagement.permanentDeleteBlocked',
                                    {
                                      count: item.generated_checklist_count,
                                    },
                                  )
                                : undefined
                            }
                            type="button"
                            onClick={() => void permanentlyDeleteItem(item)}
                          >
                            <Trash2 size={14} />
                            {t(
                              'coreBusiness.vehicleManagement.actions.permanentDelete',
                            )}
                          </button>
                        ) : null}
                      </div>
                      {canManage && item.generated_checklist_count > 0 ? (
                        <p className="max-w-72 text-right app-text-micro text-app-ink/55">
                          {t(
                            'coreBusiness.vehicleManagement.permanentDeleteBlocked',
                            { count: item.generated_checklist_count },
                          )}
                        </p>
                      ) : null}
                    </div>
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

type VehicleModelDraft = {
  notes: string;
  vehicleCode: string;
  vehicleName: string;
};

function draftFromVehicleModel(
  item: LegacyIssueVehicleModel,
): VehicleModelDraft {
  return {
    notes: item.notes ?? '',
    vehicleCode: item.vehicle_code,
    vehicleName: item.vehicle_name ?? '',
  };
}

function vehicleModelLabel(item: LegacyIssueVehicleModel): string {
  return item.vehicle_name
    ? `${item.vehicle_code} · ${item.vehicle_name}`
    : item.vehicle_code;
}

function orderedVehicleStages(item: LegacyIssueVehicleModel | null) {
  return [...(item?.stages ?? [])].sort(
    (left, right) => left.sequence_no - right.sequence_no,
  );
}

function isDuplicateStageName(
  item: LegacyIssueVehicleModel | null,
  name: string,
  exceptStageId?: string,
): boolean {
  const normalized = name.trim().toLocaleLowerCase();
  return Boolean(
    normalized &&
      item?.stages?.some(
        (stage) =>
          stage.id !== exceptStageId &&
          stage.name.trim().toLocaleLowerCase() === normalized,
      ),
  );
}

function nullableTrim(value: string): string | null {
  const normalized = value.trim();
  return normalized || null;
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}
