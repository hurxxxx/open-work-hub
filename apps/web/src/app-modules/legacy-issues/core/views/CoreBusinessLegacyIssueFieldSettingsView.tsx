import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
  type ReactNode,
} from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import {
  ArrowDown,
  ArrowUp,
  Copy,
  Eye,
  EyeOff,
  GripVertical,
  Loader2,
  Pencil,
  Plus,
  RotateCcw,
  Save,
  Trash2,
  X,
} from 'lucide-react';
import { useToast } from '@open-alm/ui';

import { cn } from '@/src/lib/utils';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  createLegacyIssueModuleField,
  deleteLegacyIssueModuleField,
  fetchLegacyIssueColumnOrder,
  fetchLegacyIssueDatasetDefinition,
  fetchLegacyIssueModuleFields,
  fetchLegacyIssueSystemFields,
  reorderLegacyIssueModuleFields,
  updateLegacyIssueColumnOrder,
  updateLegacyIssueModuleField,
  updateLegacyIssueSystemField,
  type LegacyIssueColumnOrder,
  type LegacyIssueDatasetDefinition,
  type LegacyIssueDatasetField,
  type LegacyIssueModuleField,
  type LegacyIssueModuleFieldType,
  type LegacyIssueSystemField,
} from '../api/legacy-issue-api';
import {
  LEGACY_ISSUE_DEFAULT_DATASET_KEY,
  LEGACY_ISSUE_DEFAULT_VIEW_KEY,
  LEGACY_ISSUE_MODULE_VIEW_KEYS,
  LEGACY_ISSUE_VIEW_KEYS,
  LEGACY_ISSUE_VIEWS,
  type LegacyIssueViewKey,
  type LegacyIssueModuleViewKey,
} from '../legacy-issue-datasets';
import { LegacyIssuePageHeader } from './LegacyIssuePageParts';

const MODULE_FIELD_TYPES: LegacyIssueModuleFieldType[] = [
  'text',
  'longText',
  'number',
  'date',
  'select',
  'boolean',
  'user',
  'orgUnit',
];

interface FieldDraft {
  active: boolean;
  fieldType: LegacyIssueModuleFieldType;
  labelEn: string;
  labelKo: string;
  allowMultiple: boolean;
  options: string[];
  required: boolean;
}

const EMPTY_FIELD_DRAFT: FieldDraft = {
  active: true,
  fieldType: 'text',
  labelEn: '',
  labelKo: '',
  allowMultiple: false,
  options: [],
  required: false,
};

type FieldSettingsTab = 'system-fields' | 'module-fields';

export function CoreBusinessLegacyIssueFieldSettingsView() {
  const { workspaceSlug = '' } = useParams<{ workspaceSlug: string }>();
  const { token } = useAuth();
  const { t } = useTranslation(['apps', 'common', 'shell']);
  const toast = useToast();
  const [activeTab, setActiveTab] = useState<FieldSettingsTab>('system-fields');
  const [selectedModule, setSelectedModule] =
    useState<LegacyIssueModuleViewKey>('aircon');
  const [selectedOrderView, setSelectedOrderView] =
    useState<LegacyIssueViewKey>(LEGACY_ISSUE_DEFAULT_VIEW_KEY);
  const [fields, setFields] = useState<LegacyIssueModuleField[]>([]);
  const [systemFields, setSystemFields] = useState<LegacyIssueSystemField[]>(
    [],
  );
  const [orderDefinition, setOrderDefinition] =
    useState<LegacyIssueDatasetDefinition | null>(null);
  const [columnOrder, setColumnOrder] = useState<string[]>([]);
  const [hiddenColumnKeys, setHiddenColumnKeys] = useState<string[]>([]);
  const [savedColumnOrder, setSavedColumnOrder] =
    useState<LegacyIssueColumnOrder | null>(null);
  const [draft, setDraft] = useState<FieldDraft>(EMPTY_FIELD_DRAFT);
  const [editingFieldId, setEditingFieldId] = useState<string | null>(null);
  const [editingSystemFieldKey, setEditingSystemFieldKey] = useState<
    string | null
  >(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [orderLoading, setOrderLoading] = useState(false);
  const [orderApplyingAll, setOrderApplyingAll] = useState(false);
  const [orderSaving, setOrderSaving] = useState(false);

  const selectedFields = useMemo(
    () =>
      fields
        .filter((field) => field.module_key === selectedModule)
        .sort((left, right) => left.sort_order - right.sort_order),
    [fields, selectedModule],
  );
  const editingField = selectedFields.find(
    (field) => field.id === editingFieldId,
  );
  const editingSystemField = systemFields.find(
    (field) => field.key === editingSystemFieldKey,
  );

  const loadFields = useCallback(async () => {
    if (!workspaceSlug || !token) return;
    setLoading(true);
    try {
      const response = await fetchLegacyIssueModuleFields({
        includeInactive: true,
        moduleKey: selectedModule,
        token,
        workspaceSlug,
      });
      setFields((current) => [
        ...current.filter((field) => field.module_key !== selectedModule),
        ...response.items,
      ]);
    } catch (loadError) {
      toast.error(
        errorMessage(
          loadError,
          t('coreBusiness.fieldSettings.errors.loadFailed'),
        ),
      );
    } finally {
      setLoading(false);
    }
  }, [selectedModule, t, toast, token, workspaceSlug]);

  useEffect(() => {
    if (activeTab === 'module-fields') {
      void loadFields();
    }
  }, [activeTab, loadFields]);

  const loadSystemFields = useCallback(async () => {
    if (!workspaceSlug || !token) return;
    setLoading(true);
    try {
      const response = await fetchLegacyIssueSystemFields({
        datasetKey: LEGACY_ISSUE_DEFAULT_DATASET_KEY,
        token,
        workspaceSlug,
      });
      setSystemFields(response.items);
    } catch (loadError) {
      toast.error(
        errorMessage(
          loadError,
          t('coreBusiness.fieldSettings.errors.systemFieldsLoadFailed'),
        ),
      );
    } finally {
      setLoading(false);
    }
  }, [t, toast, token, workspaceSlug]);

  useEffect(() => {
    if (activeTab === 'system-fields') {
      void loadSystemFields();
    }
  }, [activeTab, loadSystemFields]);

  const loadColumnOrder = useCallback(async () => {
    if (!workspaceSlug || !token) return;
    setOrderLoading(true);
    try {
      const [definitionResponse, orderResponse] = await Promise.all([
        fetchLegacyIssueDatasetDefinition({
          datasetKey: LEGACY_ISSUE_DEFAULT_DATASET_KEY,
          token,
          viewKey: selectedOrderView,
          workspaceSlug,
        }),
        fetchLegacyIssueColumnOrder({
          token,
          viewKey: selectedOrderView,
          workspaceSlug,
        }),
      ]);
      setOrderDefinition(definitionResponse);
      setSavedColumnOrder(orderResponse);
      setColumnOrder(orderResponse.column_order);
      setHiddenColumnKeys(orderResponse.hidden_column_keys ?? []);
    } catch (loadError) {
      toast.error(
        errorMessage(
          loadError,
          t('coreBusiness.fieldSettings.errors.columnOrderLoadFailed'),
        ),
      );
    } finally {
      setOrderLoading(false);
    }
  }, [selectedOrderView, t, toast, token, workspaceSlug]);

  useEffect(() => {
    if (activeTab === 'system-fields') {
      void loadColumnOrder();
    }
  }, [activeTab, loadColumnOrder]);

  function resetDraft() {
    setDraft(EMPTY_FIELD_DRAFT);
    setEditingFieldId(null);
    setEditingSystemFieldKey(null);
  }

  function startEdit(field: LegacyIssueModuleField) {
    setEditingSystemFieldKey(null);
    setEditingFieldId(field.id);
    setDraft({
      active: field.active,
      fieldType: field.field_type,
      labelEn: field.label_en,
      labelKo: field.label_ko,
      allowMultiple: field.allow_multiple,
      options: normalizeOptions(field.options) ?? [],
      required: field.required,
    });
  }

  function startEditSystemField(field: LegacyIssueSystemField) {
    if (field.readonly) return;
    setEditingFieldId(null);
    setEditingSystemFieldKey(field.key);
    setDraft({
      active: field.active,
      fieldType: field.field_type,
      labelEn: field.label_en,
      labelKo: field.label_ko,
      allowMultiple: field.allow_multiple,
      options: normalizeOptions(field.options) ?? [],
      required: field.required,
    });
  }

  function startEditOrderedField(field: LegacyIssueDatasetField | null) {
    if (!field || field.readonly) return;
    if (field.source === 'system') {
      const systemField =
        systemFields.find((item) => item.key === field.key) ??
        ({
          id: null,
          active: field.active,
          dataset_key: LEGACY_ISSUE_DEFAULT_DATASET_KEY,
          field_id: null,
          field_type: field.field_type,
          group_key: field.group_key,
          key: field.key,
          label_en: field.label_en,
          label_ko: field.label_ko,
          module_key: null,
          allow_multiple: field.allow_multiple,
          options: field.options,
          readonly: field.readonly,
          required: field.required,
          source: 'system',
          updated_at: null,
        } satisfies LegacyIssueSystemField);
      startEditSystemField(systemField);
      return;
    }
    if (field.source === 'module' && field.field_id) {
      setEditingSystemFieldKey(null);
      setEditingFieldId(field.field_id);
      setDraft({
        active: field.active,
        fieldType: field.field_type,
        labelEn: field.label_en,
        labelKo: field.label_ko,
        allowMultiple: field.allow_multiple,
        options: normalizeOptions(field.options) ?? [],
        required: field.required,
      });
    }
  }

  async function saveField(event: FormEvent) {
    event.preventDefault();
    if (!workspaceSlug || !token || saving) return;
    const normalizedOptions =
      draft.fieldType === 'select' ? normalizeOptions(draft.options) : null;
    if (draft.fieldType === 'select' && normalizedOptions === null) {
      toast.error(t('coreBusiness.fieldSettings.errors.optionsRequired'));
      return;
    }
    setSaving(true);
    const payload = {
      field_type: draft.fieldType,
      label_en: draft.labelEn.trim() || draft.labelKo.trim(),
      label_ko: draft.labelKo.trim(),
      allow_multiple: fieldTypeSupportsMultiple(draft.fieldType)
        ? draft.allowMultiple
        : false,
      options: normalizedOptions,
      required: draft.required,
    };
    try {
      if (editingSystemFieldKey) {
        await updateLegacyIssueSystemField({
          fieldKey: editingSystemFieldKey,
          payload: {
            ...payload,
            dataset_key: LEGACY_ISSUE_DEFAULT_DATASET_KEY,
          },
          token,
          workspaceSlug,
        });
      } else if (editingFieldId) {
        await updateLegacyIssueModuleField({
          fieldId: editingFieldId,
          payload: { ...payload, active: draft.active },
          token,
          workspaceSlug,
        });
      } else {
        await createLegacyIssueModuleField({
          payload: {
            ...payload,
            module_key: selectedModule,
          },
          token,
          workspaceSlug,
        });
      }
      toast.success(t('coreBusiness.fieldSettings.status.saved'));
      resetDraft();
      if (activeTab === 'system-fields') {
        await Promise.all([loadSystemFields(), loadColumnOrder()]);
      } else {
        await loadFields();
      }
    } catch (saveError) {
      toast.error(
        errorMessage(
          saveError,
          t('coreBusiness.fieldSettings.errors.saveFailed'),
        ),
      );
    } finally {
      setSaving(false);
    }
  }

  async function deactivateField(field: LegacyIssueModuleField) {
    if (!workspaceSlug || !token) return;
    if (!window.confirm(t('coreBusiness.fieldSettings.confirmDelete'))) return;
    setSaving(true);
    try {
      await deleteLegacyIssueModuleField({
        fieldId: field.id,
        token,
        workspaceSlug,
      });
      toast.success(t('coreBusiness.fieldSettings.status.deleted'));
      if (editingFieldId === field.id) {
        resetDraft();
      }
      await loadFields();
    } catch (deleteError) {
      toast.error(
        errorMessage(
          deleteError,
          t('coreBusiness.fieldSettings.errors.deleteFailed'),
        ),
      );
    } finally {
      setSaving(false);
    }
  }

  async function restoreField(field: LegacyIssueModuleField) {
    if (!workspaceSlug || !token) return;
    setSaving(true);
    try {
      await updateLegacyIssueModuleField({
        fieldId: field.id,
        payload: { active: true },
        token,
        workspaceSlug,
      });
      toast.success(t('coreBusiness.fieldSettings.status.restored'));
      await loadFields();
    } catch (restoreError) {
      toast.error(
        errorMessage(
          restoreError,
          t('coreBusiness.fieldSettings.errors.saveFailed'),
        ),
      );
    } finally {
      setSaving(false);
    }
  }

  async function moveField(field: LegacyIssueModuleField, direction: -1 | 1) {
    if (!workspaceSlug || !token) return;
    const currentIndex = selectedFields.findIndex(
      (item) => item.id === field.id,
    );
    const nextIndex = currentIndex + direction;
    if (
      currentIndex < 0 ||
      nextIndex < 0 ||
      nextIndex >= selectedFields.length
    ) {
      return;
    }
    const nextFields = [...selectedFields];
    const [moved] = nextFields.splice(currentIndex, 1);
    nextFields.splice(nextIndex, 0, moved);
    setFields((current) => [
      ...current.filter((item) => item.module_key !== selectedModule),
      ...nextFields.map((item, index) => ({ ...item, sort_order: index })),
    ]);
    try {
      const response = await reorderLegacyIssueModuleFields({
        fieldIds: nextFields.map((item) => item.id),
        moduleKey: selectedModule,
        token,
        workspaceSlug,
      });
      setFields((current) => [
        ...current.filter((item) => item.module_key !== selectedModule),
        ...response.items,
      ]);
    } catch (reorderError) {
      toast.error(
        errorMessage(
          reorderError,
          t('coreBusiness.fieldSettings.errors.reorderFailed'),
        ),
      );
      await loadFields();
    }
  }

  function moveColumn(columnKey: string, direction: -1 | 1) {
    setColumnOrder((current) => {
      const currentIndex = current.indexOf(columnKey);
      const nextIndex = currentIndex + direction;
      if (currentIndex < 0 || nextIndex < 0 || nextIndex >= current.length) {
        return current;
      }
      const next = [...current];
      const [moved] = next.splice(currentIndex, 1);
      next.splice(nextIndex, 0, moved);
      return next;
    });
  }

  async function saveColumnOrder() {
    if (!workspaceSlug || !token) return;
    setOrderSaving(true);
    try {
      const response = await updateLegacyIssueColumnOrder({
        payload: {
          column_order: columnOrder,
          hidden_column_keys: hiddenColumnKeys,
        },
        token,
        viewKey: selectedOrderView,
        workspaceSlug,
      });
      setSavedColumnOrder(response);
      setColumnOrder(response.column_order);
      setHiddenColumnKeys(response.hidden_column_keys ?? []);
      toast.success(t('coreBusiness.fieldSettings.status.columnOrderSaved'));
    } catch (saveError) {
      toast.error(
        errorMessage(
          saveError,
          t('coreBusiness.fieldSettings.errors.columnOrderSaveFailed'),
        ),
      );
    } finally {
      setOrderSaving(false);
    }
  }

  async function applyColumnOrderToAllViews() {
    if (!workspaceSlug || !token || orderApplyingAll) return;
    if (
      !window.confirm(
        t('coreBusiness.fieldSettings.confirmApplyColumnOrderAll'),
      )
    ) {
      return;
    }
    setOrderApplyingAll(true);
    try {
      const responses = await Promise.all(
        LEGACY_ISSUE_VIEW_KEYS.map((viewKey) =>
          updateLegacyIssueColumnOrder({
            payload: {
              column_order: columnOrder,
              hidden_column_keys: hiddenColumnKeys,
            },
            token,
            viewKey,
            workspaceSlug,
          }),
        ),
      );
      const selectedResponse =
        responses.find((response) => response.view_key === selectedOrderView) ??
        responses[0];
      if (selectedResponse) {
        setSavedColumnOrder(selectedResponse);
        setColumnOrder(selectedResponse.column_order);
        setHiddenColumnKeys(selectedResponse.hidden_column_keys ?? []);
      }
      toast.success(
        t('coreBusiness.fieldSettings.status.columnOrderAppliedAll'),
      );
    } catch (applyError) {
      toast.error(
        errorMessage(
          applyError,
          t('coreBusiness.fieldSettings.errors.columnOrderApplyAllFailed'),
        ),
      );
    } finally {
      setOrderApplyingAll(false);
    }
  }

  return (
    <main className="flex h-full min-h-0 bg-app-bg text-app-ink">
      <section className="flex min-w-0 flex-1 flex-col">
        <LegacyIssuePageHeader
          actions={null}
          eyebrow={t('coreBusiness.fieldSettings.eyebrow')}
          title={t('coreBusiness.fieldSettings.title')}
        />
        <div className="border-b border-app-border bg-app-surface px-4 py-3">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <span className="app-text-micro font-semibold uppercase text-app-ink/45">
                {t('coreBusiness.fieldSettings.navigation.function')}
              </span>
              <div className="inline-flex rounded-md border border-app-border bg-app-bg p-0.5">
                <SettingsTabButton
                  active={activeTab === 'system-fields'}
                  label={t('coreBusiness.fieldSettings.tabs.systemFields')}
                  onClick={() => {
                    resetDraft();
                    setActiveTab('system-fields');
                  }}
                />
                <SettingsTabButton
                  active={activeTab === 'module-fields'}
                  label={t('coreBusiness.fieldSettings.tabs.moduleFields')}
                  onClick={() => {
                    resetDraft();
                    setActiveTab('module-fields');
                  }}
                />
              </div>
            </div>
            <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2 rounded-md border border-app-border/70 bg-app-bg px-2 py-1.5">
              <span className="app-text-micro font-semibold uppercase text-app-ink/45">
                {t('coreBusiness.fieldSettings.navigation.target')}
              </span>
              <div className="flex flex-wrap gap-1.5">
                {activeTab === 'system-fields'
                  ? LEGACY_ISSUE_VIEW_KEYS.map((viewKey) => {
                      const active = selectedOrderView === viewKey;
                      return (
                        <button
                          key={viewKey}
                          className={cn(
                            'h-7 rounded-md border px-3 app-text-caption font-medium',
                            active
                              ? 'border-app-accent bg-app-accent text-app-accent-fg'
                              : 'border-app-border bg-app-surface text-app-ink/70 hover:bg-app-surface-hover',
                          )}
                          type="button"
                          onClick={() => setSelectedOrderView(viewKey)}
                        >
                          {t(`nav.${LEGACY_ISSUE_VIEWS[viewKey].navItemId}`, {
                            ns: 'shell',
                          })}
                        </button>
                      );
                    })
                  : activeTab === 'module-fields'
                    ? LEGACY_ISSUE_MODULE_VIEW_KEYS.map((moduleKey) => {
                        const active = selectedModule === moduleKey;
                        return (
                          <button
                            key={moduleKey}
                            className={cn(
                              'h-7 rounded-md border px-3 app-text-caption font-medium',
                              active
                                ? 'border-app-accent bg-app-accent text-app-accent-fg'
                                : 'border-app-border bg-app-surface text-app-ink/70 hover:bg-app-surface-hover',
                            )}
                            type="button"
                            onClick={() => {
                              setSelectedModule(moduleKey);
                              resetDraft();
                            }}
                          >
                            {t(
                              `nav.${LEGACY_ISSUE_VIEWS[moduleKey].navItemId}`,
                              {
                                ns: 'shell',
                              },
                            )}
                          </button>
                        );
                      })
                    : null}
              </div>
            </div>
          </div>
        </div>
        {activeTab === 'system-fields' ? (
          <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_24rem] overflow-hidden">
            <section className="min-h-0 overflow-auto px-4 py-4">
              <LegacyIssueOrderedFieldSettingsList
                applyingAll={orderApplyingAll}
                columnOrder={columnOrder}
                definition={orderDefinition}
                fieldSaving={saving}
                hiddenColumnKeys={hiddenColumnKeys}
                loading={loading || orderLoading}
                orderSaving={orderSaving}
                savedColumnOrder={savedColumnOrder}
                selectedFieldKey={editingSystemFieldKey}
                selectedModuleFieldId={editingFieldId}
                selectedView={selectedOrderView}
                onMove={moveColumn}
                onApplyToAll={applyColumnOrderToAllViews}
                onEdit={startEditOrderedField}
                onReload={loadColumnOrder}
                onSave={saveColumnOrder}
                onSetHiddenColumnKeys={setHiddenColumnKeys}
                onSetOrder={setColumnOrder}
              />
            </section>
            <aside className="min-h-0 overflow-auto border-l border-app-border bg-app-surface px-4 py-4">
              {editingSystemField || editingFieldId ? (
                <LegacyIssueFieldForm
                  draft={draft}
                  editing={true}
                  saving={saving}
                  showActive={false}
                  onCancel={resetDraft}
                  onChange={setDraft}
                  onSubmit={saveField}
                />
              ) : (
                <LegacyIssueFieldEmpty
                  icon={<Pencil size={18} />}
                  label={t('coreBusiness.fieldSettings.systemFields.select')}
                />
              )}
            </aside>
          </div>
        ) : (
          <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_24rem] overflow-hidden">
            <section className="min-h-0 overflow-auto px-4 py-4">
              <LegacyIssueFieldList
                fields={selectedFields}
                loading={loading}
                saving={saving}
                selectedFieldId={editingFieldId}
                onDeactivate={deactivateField}
                onEdit={startEdit}
                onMove={moveField}
                onRestore={restoreField}
              />
            </section>
            <aside className="min-h-0 overflow-auto border-l border-app-border bg-app-surface px-4 py-4">
              <LegacyIssueFieldForm
                draft={draft}
                editing={Boolean(editingField)}
                saving={saving}
                showActive={Boolean(editingField)}
                onCancel={resetDraft}
                onChange={setDraft}
                onSubmit={saveField}
              />
            </aside>
          </div>
        )}
      </section>
    </main>
  );
}

function SettingsTabButton({
  active,
  label,
  onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      className={cn(
        'h-7 rounded px-3 app-text-caption font-semibold',
        active
          ? 'bg-app-ink text-app-bg shadow-sm'
          : 'text-app-ink/65 hover:bg-app-surface-hover',
      )}
      type="button"
      onClick={onClick}
    >
      {label}
    </button>
  );
}

interface OrderedFieldSettingsColumn {
  field: LegacyIssueDatasetField | null;
  group: string | null;
  key: string;
  title: string;
}

function LegacyIssueOrderedFieldSettingsList({
  applyingAll,
  columnOrder,
  definition,
  fieldSaving,
  hiddenColumnKeys,
  loading,
  onApplyToAll,
  onEdit,
  onMove,
  onReload,
  onSave,
  onSetHiddenColumnKeys,
  onSetOrder,
  orderSaving,
  savedColumnOrder,
  selectedFieldKey,
  selectedModuleFieldId,
}: {
  applyingAll: boolean;
  columnOrder: string[];
  definition: LegacyIssueDatasetDefinition | null;
  fieldSaving: boolean;
  hiddenColumnKeys: string[];
  loading: boolean;
  onEdit: (field: LegacyIssueDatasetField | null) => void;
  onApplyToAll: () => void;
  onMove: (columnKey: string, direction: -1 | 1) => void;
  onReload: () => void;
  onSave: () => void;
  onSetHiddenColumnKeys: (hiddenColumnKeys: string[]) => void;
  onSetOrder: (columnOrder: string[]) => void;
  orderSaving: boolean;
  savedColumnOrder: LegacyIssueColumnOrder | null;
  selectedFieldKey: string | null;
  selectedModuleFieldId: string | null;
  selectedView: LegacyIssueViewKey;
}) {
  const { i18n, t } = useTranslation(['apps', 'common']);
  const columns = useMemo<OrderedFieldSettingsColumn[]>(() => {
    const korean = i18n.language.startsWith('ko');
    const groupLabels = korean
      ? (definition?.group_labels_ko ?? {})
      : (definition?.group_labels_en ?? {});
    return [
      ...(definition?.fields ?? []).map((field) => {
        const group = field.group_key
          ? (groupLabels[field.group_key] ?? null)
          : null;
        return {
          field,
          group,
          key: field.key,
          title: displayFieldSettingsColumnLabel({
            groupLabel: group ?? undefined,
            label: korean ? field.label_ko : field.label_en,
          }),
        };
      }),
      {
        field: null,
        group: null,
        key: 'primary_attachment',
        title: t('coreBusiness.module.fields.primary_attachment'),
      },
    ];
  }, [definition, i18n.language, t]);
  const columnByKey = useMemo(
    () => new Map(columns.map((column) => [column.key, column])),
    [columns],
  );
  const orderedColumns = useMemo(() => {
    const ordered = columnOrder
      .map((key) => columnByKey.get(key))
      .filter((column): column is OrderedFieldSettingsColumn =>
        Boolean(column),
      );
    const orderedKeySet = new Set(ordered.map((column) => column.key));
    return [
      ...ordered,
      ...columns.filter((column) => !orderedKeySet.has(column.key)),
    ];
  }, [columnByKey, columnOrder, columns]);
  const orderedColumnKeys = useMemo(
    () => orderedColumns.map((column) => column.key),
    [orderedColumns],
  );
  const dragSensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 4,
      },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );
  const reorderDisabled = orderSaving || applyingAll;
  const hiddenColumnKeySet = useMemo(
    () => new Set(hiddenColumnKeys),
    [hiddenColumnKeys],
  );
  const visibleColumnCount = orderedColumns.filter(
    (column) => !hiddenColumnKeySet.has(column.key),
  ).length;

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const activeIndex = orderedColumnKeys.indexOf(String(active.id));
    const overIndex = orderedColumnKeys.indexOf(String(over.id));
    if (activeIndex < 0 || overIndex < 0) return;
    onSetOrder(arrayMove(orderedColumnKeys, activeIndex, overIndex));
  }

  if (loading) {
    return (
      <LegacyIssueFieldEmpty
        icon={<Loader2 size={18} className="animate-spin" />}
        label={t('common:feedback.loading')}
      />
    );
  }
  if (!definition || orderedColumns.length === 0) {
    return (
      <LegacyIssueFieldEmpty
        icon={<ArrowDown size={18} />}
        label={t('coreBusiness.fieldSettings.columnOrder.empty')}
      />
    );
  }

  return (
    <div className="overflow-auto rounded-md border border-app-border bg-app-surface">
      <div className="flex items-center justify-between gap-3 border-b border-app-border px-3 py-2">
        <div className="min-w-0">
          <div className="app-text-caption font-semibold text-app-ink">
            {t('coreBusiness.fieldSettings.columnOrder.title')}
          </div>
          <div className="truncate app-text-micro text-app-ink/45">
            {savedColumnOrder?.updated_at
              ? t('coreBusiness.fieldSettings.columnOrder.updatedAt', {
                  date: savedColumnOrder.updated_at,
                })
              : t('coreBusiness.fieldSettings.columnOrder.notSaved')}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <IconButton
            disabled={orderSaving || applyingAll}
            label={t('coreBusiness.fieldSettings.columnOrder.reload')}
            onClick={onReload}
          >
            <RotateCcw size={14} />
          </IconButton>
          <button
            className="inline-flex h-8 items-center justify-center gap-1.5 rounded-md border border-app-border bg-app-bg px-3 app-text-caption font-medium text-app-ink/70 hover:bg-app-surface-hover disabled:opacity-40"
            disabled={orderSaving || applyingAll}
            type="button"
            onClick={() => {
              onSetOrder(columns.map((column) => column.key));
              onSetHiddenColumnKeys([]);
            }}
          >
            {t('coreBusiness.fieldSettings.columnOrder.reset')}
          </button>
          <button
            className="inline-flex h-8 items-center justify-center gap-1.5 rounded-md border border-app-border bg-app-bg px-3 app-text-caption font-medium text-app-ink/70 hover:bg-app-surface-hover disabled:opacity-40"
            disabled={orderSaving || applyingAll}
            type="button"
            onClick={onApplyToAll}
          >
            {applyingAll ? (
              <Loader2 size={15} className="animate-spin" />
            ) : (
              <Copy size={15} />
            )}
            {t('coreBusiness.fieldSettings.columnOrder.applyAll')}
          </button>
          <button
            className="inline-flex h-8 items-center justify-center gap-1.5 rounded-md bg-app-accent px-3 app-text-caption font-medium text-app-accent-fg hover:bg-app-accent/90 disabled:opacity-50"
            disabled={orderSaving || applyingAll}
            type="button"
            onClick={onSave}
          >
            {orderSaving ? (
              <Loader2 size={15} className="animate-spin" />
            ) : (
              <Save size={15} />
            )}
            {t('common:actions.save')}
          </button>
        </div>
      </div>
      <DndContext
        collisionDetection={closestCenter}
        sensors={dragSensors}
        onDragEnd={handleDragEnd}
      >
        <SortableContext
          items={orderedColumnKeys}
          strategy={verticalListSortingStrategy}
        >
          <table className="w-full min-w-[56rem] table-fixed border-collapse app-text-caption">
            <thead className="bg-app-bg text-left text-app-ink/55">
              <tr>
                <th className="w-16 px-3 py-2 font-medium">
                  {t('coreBusiness.fieldSettings.columns.order')}
                </th>
                <th className="px-3 py-2 font-medium">
                  {t('coreBusiness.fieldSettings.columns.label')}
                </th>
                <th className="w-36 px-3 py-2 font-medium">
                  {t('coreBusiness.fieldSettings.columnOrder.group')}
                </th>
                <th className="w-28 px-3 py-2 font-medium">
                  {t('coreBusiness.fieldSettings.columns.type')}
                </th>
                <th className="w-20 px-3 py-2 font-medium">
                  {t('coreBusiness.fieldSettings.columns.required')}
                </th>
                <th className="w-24 px-3 py-2 font-medium">
                  {t('coreBusiness.fieldSettings.columns.status')}
                </th>
                <th className="w-28 px-3 py-2 font-medium">
                  {t('coreBusiness.fieldSettings.columns.visibility')}
                </th>
                <th className="w-20 px-3 py-2 text-right font-medium">
                  {t('coreBusiness.fieldSettings.columns.actions')}
                </th>
              </tr>
            </thead>
            <tbody>
              {orderedColumns.map((column, index) => (
                <SortableOrderedFieldSettingsRow
                  key={column.key}
                  column={column}
                  disabled={reorderDisabled}
                  dragLabel={t('coreBusiness.fieldSettings.columnOrder.drag', {
                    column: column.title,
                  })}
                  groupFallback={t('common:empty.none')}
                  hidden={hiddenColumnKeySet.has(column.key)}
                  index={index}
                  moveDownLabel={t(
                    'coreBusiness.fieldSettings.actions.moveDown',
                  )}
                  moveUpLabel={t('coreBusiness.fieldSettings.actions.moveUp')}
                  selected={isOrderedFieldSettingsColumnSelected({
                    column,
                    selectedFieldKey,
                    selectedModuleFieldId,
                  })}
                  totalCount={orderedColumns.length}
                  visibleColumnCount={visibleColumnCount}
                  fieldSaving={fieldSaving}
                  onEdit={onEdit}
                  onMove={onMove}
                  onToggleVisibility={(columnKey) =>
                    onSetHiddenColumnKeys(
                      hiddenColumnKeySet.has(columnKey)
                        ? hiddenColumnKeys.filter((key) => key !== columnKey)
                        : [...hiddenColumnKeys, columnKey],
                    )
                  }
                />
              ))}
            </tbody>
          </table>
        </SortableContext>
      </DndContext>
    </div>
  );
}

function SortableOrderedFieldSettingsRow({
  column,
  disabled,
  dragLabel,
  fieldSaving,
  groupFallback,
  hidden,
  index,
  moveDownLabel,
  moveUpLabel,
  onEdit,
  onMove,
  onToggleVisibility,
  selected,
  totalCount,
  visibleColumnCount,
}: {
  column: OrderedFieldSettingsColumn;
  disabled: boolean;
  dragLabel: string;
  fieldSaving: boolean;
  groupFallback: string;
  hidden: boolean;
  index: number;
  moveDownLabel: string;
  moveUpLabel: string;
  onEdit: (field: LegacyIssueDatasetField | null) => void;
  onMove: (columnKey: string, direction: -1 | 1) => void;
  onToggleVisibility: (columnKey: string) => void;
  selected: boolean;
  totalCount: number;
  visibleColumnCount: number;
}) {
  const { t } = useTranslation(['apps', 'common']);
  const {
    attributes,
    isDragging,
    listeners,
    setNodeRef,
    transform,
    transition,
  } = useSortable({
    id: column.key,
    disabled,
  });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };
  return (
    <tr
      ref={setNodeRef}
      className={cn(
        'border-t border-app-border bg-app-surface',
        selected && 'bg-app-accent/5',
        hidden && 'text-app-ink/45',
        column.field && !column.field.active && 'text-app-ink/45',
        isDragging && 'relative z-10 opacity-50 shadow-sm',
      )}
      style={style}
    >
      <td className="px-3 py-2">
        <div className="flex items-center gap-1">
          <button
            className="inline-flex size-7 cursor-grab items-center justify-center rounded text-app-ink/35 hover:bg-app-surface-hover hover:text-app-ink/70 disabled:cursor-not-allowed disabled:opacity-30"
            disabled={disabled}
            type="button"
            aria-label={dragLabel}
            {...attributes}
            {...listeners}
          >
            <GripVertical size={14} />
          </button>
          <IconButton
            disabled={disabled || index === 0}
            label={moveUpLabel}
            onClick={() => onMove(column.key, -1)}
          >
            <ArrowUp size={14} />
          </IconButton>
          <IconButton
            disabled={disabled || index === totalCount - 1}
            label={moveDownLabel}
            onClick={() => onMove(column.key, 1)}
          >
            <ArrowDown size={14} />
          </IconButton>
        </div>
      </td>
      <td className="truncate px-3 py-2">
        <div className="truncate font-medium">{column.title}</div>
        <div className="truncate app-text-micro text-app-ink/45">
          {column.key}
        </div>
      </td>
      <td className="truncate px-3 py-2 text-app-ink/60">
        {column.group ?? groupFallback}
      </td>
      <td className="truncate px-3 py-2 text-app-ink/65">
        {column.field ? fieldSettingsTypeLabel(column.field, t) : groupFallback}
      </td>
      <td className="px-3 py-2 text-app-ink/65">
        {column.field?.required
          ? t('common:actions.done')
          : t('common:empty.none')}
      </td>
      <td className="px-3 py-2 text-app-ink/65">
        {orderedFieldSettingsStatusLabel(column.field, t)}
      </td>
      <td className="px-3 py-2">
        <button
          className="inline-flex h-7 items-center gap-1.5 rounded-md border border-app-border bg-app-bg px-2 app-text-micro font-medium text-app-ink/70 hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-40"
          disabled={disabled || (!hidden && visibleColumnCount <= 1)}
          type="button"
          aria-label={t(
            hidden
              ? 'coreBusiness.fieldSettings.actions.showColumn'
              : 'coreBusiness.fieldSettings.actions.hideColumn',
            { column: column.title },
          )}
          onClick={() => onToggleVisibility(column.key)}
        >
          {hidden ? <EyeOff size={13} /> : <Eye size={13} />}
          {t(
            hidden
              ? 'coreBusiness.fieldSettings.visibility.hidden'
              : 'coreBusiness.fieldSettings.visibility.visible',
          )}
        </button>
      </td>
      <td className="px-3 py-2">
        <div className="flex justify-end gap-1">
          <IconButton
            disabled={
              fieldSaving || !isOrderedFieldSettingsEditable(column.field)
            }
            label={t('common:actions.edit')}
            onClick={() => onEdit(column.field)}
          >
            <Pencil size={14} />
          </IconButton>
        </div>
      </td>
    </tr>
  );
}

function isOrderedFieldSettingsColumnSelected({
  column,
  selectedFieldKey,
  selectedModuleFieldId,
}: {
  column: OrderedFieldSettingsColumn;
  selectedFieldKey: string | null;
  selectedModuleFieldId: string | null;
}) {
  if (!column.field) return false;
  if (column.field.source === 'system') {
    return selectedFieldKey === column.field.key;
  }
  if (column.field.source === 'module') {
    return selectedModuleFieldId === column.field.field_id;
  }
  return false;
}

function orderedFieldSettingsStatusLabel(
  field: LegacyIssueDatasetField | null,
  t: (key: string) => string,
) {
  if (!field) {
    return t('coreBusiness.fieldSettings.status.readonly');
  }
  if (!field.active) {
    return t('coreBusiness.fieldSettings.status.inactive');
  }
  if (field.readonly) {
    return t('coreBusiness.fieldSettings.status.readonly');
  }
  return t('coreBusiness.fieldSettings.status.editable');
}

function isOrderedFieldSettingsEditable(field: LegacyIssueDatasetField | null) {
  if (!field || field.readonly) return false;
  if (field.source === 'system') return true;
  if (field.source === 'module') return Boolean(field.field_id);
  return false;
}

function LegacyIssueFieldList({
  fields,
  loading,
  onDeactivate,
  onEdit,
  onMove,
  onRestore,
  saving,
  selectedFieldId,
}: {
  fields: LegacyIssueModuleField[];
  loading: boolean;
  onDeactivate: (field: LegacyIssueModuleField) => void;
  onEdit: (field: LegacyIssueModuleField) => void;
  onMove: (field: LegacyIssueModuleField, direction: -1 | 1) => void;
  onRestore: (field: LegacyIssueModuleField) => void;
  saving: boolean;
  selectedFieldId: string | null;
}) {
  const { t } = useTranslation(['apps', 'common']);
  if (loading) {
    return (
      <LegacyIssueFieldEmpty
        icon={<Loader2 size={18} className="animate-spin" />}
        label={t('common:feedback.loading')}
      />
    );
  }
  if (fields.length === 0) {
    return (
      <LegacyIssueFieldEmpty
        icon={<Plus size={18} />}
        label={t('coreBusiness.fieldSettings.empty')}
      />
    );
  }
  return (
    <div className="overflow-hidden rounded-md border border-app-border bg-app-surface">
      <table className="w-full table-fixed border-collapse app-text-caption">
        <thead className="bg-app-bg text-left text-app-ink/55">
          <tr>
            <th className="w-16 px-3 py-2 font-medium">
              {t('coreBusiness.fieldSettings.columns.order')}
            </th>
            <th className="px-3 py-2 font-medium">
              {t('coreBusiness.fieldSettings.columns.label')}
            </th>
            <th className="w-32 px-3 py-2 font-medium">
              {t('coreBusiness.fieldSettings.columns.type')}
            </th>
            <th className="w-24 px-3 py-2 font-medium">
              {t('coreBusiness.fieldSettings.columns.required')}
            </th>
            <th className="w-24 px-3 py-2 font-medium">
              {t('coreBusiness.fieldSettings.columns.status')}
            </th>
            <th className="w-44 px-3 py-2 text-right font-medium">
              {t('coreBusiness.fieldSettings.columns.actions')}
            </th>
          </tr>
        </thead>
        <tbody>
          {fields.map((field, index) => (
            <tr
              key={field.id}
              className={cn(
                'border-t border-app-border',
                selectedFieldId === field.id && 'bg-app-accent/5',
                !field.active && 'text-app-ink/45',
              )}
            >
              <td className="px-3 py-2">
                <div className="flex items-center gap-1">
                  <IconButton
                    disabled={saving || index === 0}
                    label={t('coreBusiness.fieldSettings.actions.moveUp')}
                    onClick={() => onMove(field, -1)}
                  >
                    <ArrowUp size={14} />
                  </IconButton>
                  <IconButton
                    disabled={saving || index === fields.length - 1}
                    label={t('coreBusiness.fieldSettings.actions.moveDown')}
                    onClick={() => onMove(field, 1)}
                  >
                    <ArrowDown size={14} />
                  </IconButton>
                </div>
              </td>
              <td className="truncate px-3 py-2">
                <div className="truncate font-medium">{field.label_ko}</div>
                <div className="truncate app-text-micro text-app-ink/45">
                  {field.label_en}
                </div>
              </td>
              <td className="px-3 py-2">{fieldSettingsTypeLabel(field, t)}</td>
              <td className="px-3 py-2">
                {field.required
                  ? t('common:actions.done')
                  : t('common:empty.none')}
              </td>
              <td className="px-3 py-2">
                {field.active
                  ? t('coreBusiness.fieldSettings.status.active')
                  : t('coreBusiness.fieldSettings.status.inactive')}
              </td>
              <td className="px-3 py-2">
                <div className="flex justify-end gap-1">
                  <IconButton
                    disabled={saving}
                    label={t('common:actions.edit')}
                    onClick={() => onEdit(field)}
                  >
                    <Pencil size={14} />
                  </IconButton>
                  {field.active ? (
                    <IconButton
                      disabled={saving}
                      label={t('common:actions.delete')}
                      onClick={() => onDeactivate(field)}
                    >
                      <Trash2 size={14} />
                    </IconButton>
                  ) : (
                    <IconButton
                      disabled={saving}
                      label={t('coreBusiness.fieldSettings.actions.restore')}
                      onClick={() => onRestore(field)}
                    >
                      <RotateCcw size={14} />
                    </IconButton>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function LegacyIssueFieldForm({
  draft,
  editing,
  onCancel,
  onChange,
  onSubmit,
  saving,
  showActive = editing,
}: {
  draft: FieldDraft;
  editing: boolean;
  onCancel: () => void;
  onChange: (draft: FieldDraft) => void;
  onSubmit: (event: FormEvent) => void;
  saving: boolean;
  showActive?: boolean;
}) {
  const { t } = useTranslation(['apps', 'common']);
  const [optionValue, setOptionValue] = useState('');
  const requiresOptions = draft.fieldType === 'select';
  const supportsMultiple = fieldTypeSupportsMultiple(draft.fieldType);
  const optionCanAdd = splitOptionText(optionValue).some(
    (option) => !draft.options.includes(option),
  );
  const saveDisabled =
    saving || (requiresOptions && normalizeOptions(draft.options) === null);

  useEffect(() => {
    setOptionValue('');
  }, [draft.fieldType, draft.options]);

  function addOption(rawValue = optionValue) {
    const nextOptions = mergeOptions(draft.options, splitOptionText(rawValue));
    if (nextOptions.length !== draft.options.length) {
      onChange({ ...draft, options: nextOptions });
    }
    setOptionValue('');
  }

  function removeOption(option: string) {
    onChange({
      ...draft,
      options: draft.options.filter((item) => item !== option),
    });
  }

  return (
    <form className="space-y-4" onSubmit={onSubmit}>
      <div className="flex items-center justify-between gap-3">
        <h2 className="app-text-body-sm font-semibold">
          {editing
            ? t('coreBusiness.fieldSettings.form.editTitle')
            : t('coreBusiness.fieldSettings.form.createTitle')}
        </h2>
        {editing ? (
          <button
            aria-label={t('common:actions.cancel')}
            className="flex size-8 items-center justify-center rounded-md border border-app-border text-app-ink/55 hover:bg-app-surface-hover"
            type="button"
            onClick={onCancel}
          >
            <X size={15} />
          </button>
        ) : null}
      </div>
      <FieldLabel label={t('coreBusiness.fieldSettings.form.labelKo')}>
        <input
          className="app-field-input-sm"
          required
          value={draft.labelKo}
          onChange={(event) =>
            onChange({ ...draft, labelKo: event.target.value })
          }
        />
      </FieldLabel>
      <FieldLabel label={t('coreBusiness.fieldSettings.form.labelEn')}>
        <input
          className="app-field-input-sm"
          value={draft.labelEn}
          onChange={(event) =>
            onChange({ ...draft, labelEn: event.target.value })
          }
        />
      </FieldLabel>
      <FieldLabel label={t('coreBusiness.fieldSettings.form.type')}>
        <select
          className="app-field-input-sm"
          value={draft.fieldType}
          onChange={(event) => {
            const fieldType = event.target.value as LegacyIssueModuleFieldType;
            onChange({
              ...draft,
              fieldType,
              allowMultiple: fieldTypeSupportsMultiple(fieldType)
                ? draft.allowMultiple
                : false,
            });
          }}
        >
          {MODULE_FIELD_TYPES.map((fieldType) => (
            <option key={fieldType} value={fieldType}>
              {t(`coreBusiness.fieldSettings.types.${fieldType}`)}
            </option>
          ))}
        </select>
      </FieldLabel>
      {supportsMultiple ? (
        <label className="flex items-center gap-2 rounded-md border border-app-border bg-app-bg px-3 py-2 app-text-caption text-app-ink/70">
          <input
            checked={draft.allowMultiple}
            className="size-4 rounded border-app-border"
            type="checkbox"
            onChange={(event) =>
              onChange({ ...draft, allowMultiple: event.target.checked })
            }
          />
          {t('coreBusiness.fieldSettings.form.allowMultiple')}
        </label>
      ) : null}
      {requiresOptions ? (
        <div className="space-y-2">
          <FieldLabel label={t('coreBusiness.fieldSettings.form.options')}>
            <div className="flex gap-2">
              <input
                className="app-field-input-sm h-8 min-w-0 flex-1"
                placeholder={t(
                  'coreBusiness.fieldSettings.form.optionsPlaceholder',
                )}
                value={optionValue}
                onChange={(event) => setOptionValue(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault();
                    addOption();
                  }
                }}
                onPaste={(event) => {
                  const pastedText = event.clipboardData.getData('text');
                  if (/[\n,]/.test(pastedText)) {
                    event.preventDefault();
                    addOption(pastedText);
                  }
                }}
              />
              <button
                className="inline-flex h-8 shrink-0 items-center justify-center gap-1 rounded-md border border-app-border bg-app-bg px-3 app-text-caption font-medium text-app-ink/70 hover:bg-app-surface-hover disabled:opacity-40"
                disabled={!optionCanAdd}
                type="button"
                onClick={() => addOption()}
              >
                <Plus size={14} />
                {t('common:actions.add')}
              </button>
            </div>
          </FieldLabel>
          {draft.options.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {draft.options.map((option) => (
                <span
                  key={option}
                  className="inline-flex h-7 max-w-full items-center gap-1 rounded-md border border-app-border bg-app-bg px-2 app-text-caption text-app-ink/75"
                >
                  <span className="truncate">{option}</span>
                  <button
                    aria-label={t(
                      'coreBusiness.fieldSettings.form.removeOption',
                      { option },
                    )}
                    className="inline-flex size-4 shrink-0 items-center justify-center rounded text-app-ink/45 hover:bg-app-surface-hover hover:text-app-ink"
                    type="button"
                    onClick={() => removeOption(option)}
                  >
                    <X size={12} />
                  </button>
                </span>
              ))}
            </div>
          ) : (
            <div className="rounded-md border border-dashed border-app-border bg-app-bg px-3 py-3 app-text-caption text-app-ink/45">
              {t('coreBusiness.fieldSettings.form.optionsEmpty')}
            </div>
          )}
        </div>
      ) : null}
      <label className="flex items-center gap-2 app-text-caption text-app-ink/70">
        <input
          checked={draft.required}
          className="size-4 rounded border-app-border"
          type="checkbox"
          onChange={(event) =>
            onChange({ ...draft, required: event.target.checked })
          }
        />
        {t('coreBusiness.fieldSettings.form.required')}
      </label>
      {showActive ? (
        <label className="flex items-center gap-2 app-text-caption text-app-ink/70">
          <input
            checked={draft.active}
            className="size-4 rounded border-app-border"
            type="checkbox"
            onChange={(event) =>
              onChange({ ...draft, active: event.target.checked })
            }
          />
          {t('coreBusiness.fieldSettings.form.active')}
        </label>
      ) : null}
      <button
        className="inline-flex h-8 w-full items-center justify-center gap-2 rounded-md bg-app-accent px-3 app-text-caption font-medium text-app-accent-fg hover:bg-app-accent/90 disabled:opacity-50"
        disabled={saveDisabled}
        type="submit"
      >
        {saving ? (
          <Loader2 size={15} className="animate-spin" />
        ) : (
          <Save size={15} />
        )}
        {t('common:actions.save')}
      </button>
    </form>
  );
}

function FieldLabel({
  children,
  label,
}: {
  children: ReactNode;
  label: string;
}) {
  return (
    <label className="block space-y-1">
      <span className="block app-text-micro font-medium text-app-ink/55">
        {label}
      </span>
      {children}
    </label>
  );
}

function IconButton({
  children,
  disabled,
  label,
  onClick,
}: {
  children: ReactNode;
  disabled?: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      aria-label={label}
      className="inline-flex size-7 items-center justify-center rounded-md border border-app-border text-app-ink/55 hover:bg-app-surface-hover disabled:opacity-40"
      disabled={disabled}
      title={label}
      type="button"
      onClick={onClick}
    >
      {children}
    </button>
  );
}

function LegacyIssueFieldEmpty({
  icon,
  label,
}: {
  icon: ReactNode;
  label: string;
}) {
  return (
    <div className="flex min-h-48 flex-col items-center justify-center gap-2 rounded-md border border-dashed border-app-border bg-app-surface px-4 text-center app-text-caption text-app-ink/50">
      {icon}
      <span>{label}</span>
    </div>
  );
}

function splitOptionText(value: string): string[] {
  return value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function mergeOptions(currentOptions: string[], incomingOptions: string[]) {
  return Array.from(new Set([...currentOptions, ...incomingOptions]));
}

function normalizeOptions(value: string[]): string[] | null {
  const options = Array.from(
    new Set(value.map((item) => item.trim()).filter(Boolean)),
  );
  return options.length > 0 ? options : null;
}

function fieldTypeSupportsMultiple(fieldType: LegacyIssueModuleFieldType) {
  return (
    fieldType === 'select' || fieldType === 'user' || fieldType === 'orgUnit'
  );
}

function fieldSettingsTypeLabel(
  field: Pick<LegacyIssueDatasetField, 'allow_multiple' | 'field_type'>,
  t: (key: string) => string,
) {
  const label = t(`coreBusiness.fieldSettings.types.${field.field_type}`);
  if (!field.allow_multiple) return label;
  return `${label} (${t('coreBusiness.fieldSettings.types.multipleSuffix')})`;
}

function displayFieldSettingsColumnLabel({
  groupLabel,
  label,
}: {
  groupLabel: string | undefined;
  label: string;
}) {
  if (!groupLabel) return label.trim();
  const normalizedGroup = groupLabel.trim();
  const normalizedLabel = label.trim();
  for (const separator of [' - ', '-', ' / ', '/']) {
    const prefix = `${normalizedGroup}${separator}`;
    if (normalizedLabel.startsWith(prefix)) {
      return normalizedLabel.slice(prefix.length).trim() || normalizedLabel;
    }
  }
  return normalizedLabel;
}

function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}
