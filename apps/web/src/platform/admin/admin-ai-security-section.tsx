import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Play,
  Plus,
  RefreshCw,
  Save,
  Search,
  ShieldCheck,
  Trash2,
  X,
} from 'lucide-react';

import {
  BarChartCard,
  Button,
  InlineNotice,
  Tabs,
  TabsList,
  TabsTrigger,
  useToast,
} from '@open-alm/ui';

import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  formatDateTime,
  normalizeTimeZone,
} from '@/src/platform/time/time-utils';
import {
  createAdminAiSecurityExternalTransferException,
  createAdminAiSecurityRule,
  deleteAdminAiSecurityExternalTransferException,
  deleteAdminAiSecurityRule,
  getAdminAiSecurityDetectedValueDetails,
  getAdminAiSecurityDetectedValueGroups,
  getAdminAiSecurityMonitoring,
  getAdminAiSecuritySummary,
  listOrgUnits,
  listWorkspaces,
  simulateAdminAiSecurityPolicy,
  updateAdminAiSecurityExternalTransferException,
  updateAdminAiSecurityDataProtection,
  updateAdminAiSecurityEnforcement,
  updateAdminAiSecurityRule,
  type AiSecurityDataProtectionAction,
  type AiSecurityDetectedValueDetailsResponse,
  type AiSecurityDetectedValueGroup,
  type AiSecurityDetectedValueGroupsResponse,
  type AiSecurityDetectedValueStat,
  type AiSecurityExternalAppAction,
  type AiSecurityExternalAppCandidate,
  type AiSecurityExternalTransferBlocker,
  type AiSecurityExternalTransferExceptionPayload,
  type AiSecurityMonitoring,
  type AiSecurityPolicyEffect,
  type AiSecurityRulePayload,
  type AiSecuritySimulationPayload,
  type AiSecuritySimulationResult,
  type AiSecuritySummary,
  type OrgUnitItem,
  type WorkspaceItem,
} from './admin-api';
import { AuditLogList } from './admin-audit-section';
import {
  Badge,
  BodyCell,
  EmptyPanel,
  EmptyRow,
  FORM_FIELD_CLASS as fieldClassName,
  HeadCell,
  SurfaceCard,
  getErrorMessage,
} from './admin-shared';
import {
  buildUsageDateRangePreset,
  DEFAULT_USAGE_PERIOD_PRESET,
  getKstDateInputValue,
  getUsagePeriodPresetOptions,
  normalizeUsageDateRange,
  type UsageDateRange,
  type UsagePeriodPreset,
} from './admin-usage-period-model';
import { formatUsageNumber } from './admin-usage-format';
import {
  AiSecurityAppPicker,
  AiSecurityConditionInput,
  AiSecurityFieldLabel,
  AiSecurityFormSection,
  AiSecurityGuidance,
  AiSecurityOrgUnitPicker,
  AiSecurityTaskKindPicker,
  AiSecurityTermsTagInput,
  AiSecurityUserPicker,
  AiSecurityWorkspacePicker,
  aiSecuritySelectedUserFromException,
  aiSecuritySelectedUserFromRule,
  type AiSecuritySelectedUser,
} from './admin-ai-security-fields';
import {
  AiSecurityDetectedValueDetailsDialog,
  AiSecurityDetectedValueGroupTable,
  AiSecurityDetectedValueGroupsDialog,
  AiSecurityMetric,
  AiSecurityMonitoringBreakdownList,
  AiSecurityMonitoringUserTable,
  buildAiSecurityDetectionDetectorChart,
  buildAiSecurityDetectionEntityChart,
  buildAiSecurityMonitoringTrendChart,
  aiSecurityMonitoringEntityLabel,
  aiSecurityMonitoringReasonLabel,
} from './admin-ai-security-monitoring';
import {
  AI_SECURITY_DATA_ACTIONS,
  AI_SECURITY_DETECTED_VALUE_PAGE_SIZE,
  AI_SECURITY_EFFECTS,
  AI_SECURITY_EXCEPTION_BLOCKERS,
  AI_SECURITY_EXTERNAL_APP_ACTIONS,
  AI_SECURITY_TABS,
  aiSecurityBadgeTone,
  aiSecurityConditionOptions,
  aiSecurityDataProtectionAction,
  aiSecurityDefaultExternalAppActions,
  aiSecurityExceptionDraftFromException,
  aiSecurityExceptionExpiryState,
  aiSecurityExternalAppAction,
  aiSecurityIsoFromDateTimeLocal,
  aiSecurityPresent,
  aiSecurityRequestSummary,
  aiSecurityRuleDraftFromRule,
  aiSecuritySubjectSummary,
  aiSecurityTaskKindsFromScope,
  aiSecurityTermsText,
  aiSecurityTranslatedTaskDescription,
  emptyAiSecurityExceptionDraft,
  emptyAiSecurityRuleDraft,
  formatAiSecurityDateTimeLocal,
  parseAiSecurityTerms,
  resolveAiSecurityTab,
  withAiSecurityTab,
  type AiSecurityAppOption,
  type AiSecurityConditionOption,
  type AiSecurityExternalAppActions,
  type AiSecurityTab,
} from './admin-ai-security-model';

export function AiSecuritySection({ token }: { token: string }) {
  const { t, i18n } = useTranslation('apps');
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const toast = useToast();
  const { user } = useAuth();
  const locale = i18n.resolvedLanguage ?? i18n.language;
  const timeZone = normalizeTimeZone(user?.time_zone);
  const todayDate = useMemo(() => getKstDateInputValue(), []);
  const tab = resolveAiSecurityTab(searchParams.get('tab'));
  const requestedTabRef = useRef<AiSecurityTab>(tab);
  useEffect(() => {
    requestedTabRef.current = tab;
  }, [tab]);
  const setTab = (nextTab: AiSecurityTab) => {
    if (requestedTabRef.current === nextTab) return;
    requestedTabRef.current = nextTab;
    setSearchParams(withAiSecurityTab(searchParams, nextTab), {
      replace: false,
    });
  };
  const [summary, setSummary] = useState<AiSecuritySummary | null>(null);
  const [monitoringPeriodPreset, setMonitoringPeriodPreset] = useState<
    UsagePeriodPreset | 'custom'
  >(DEFAULT_USAGE_PERIOD_PRESET);
  const [monitoringDateRange, setMonitoringDateRange] =
    useState<UsageDateRange>(() =>
      buildUsageDateRangePreset(DEFAULT_USAGE_PERIOD_PRESET, todayDate),
    );
  const [monitoringDraftDateRange, setMonitoringDraftDateRange] =
    useState<UsageDateRange>(() =>
      buildUsageDateRangePreset(DEFAULT_USAGE_PERIOD_PRESET, todayDate),
    );
  const [monitoring, setMonitoring] = useState<AiSecurityMonitoring | null>(
    null,
  );
  const [monitoringView, setMonitoringView] = useState<
    'overview' | 'detections' | 'users' | 'events'
  >('overview');
  const [orgUnits, setOrgUnits] = useState<OrgUnitItem[]>([]);
  const [workspaces, setWorkspaces] = useState<WorkspaceItem[]>([]);
  const [dataTermsText, setDataTermsText] = useState('');
  const [dataBlockerActions, setDataBlockerActions] = useState<
    Partial<
      Record<AiSecurityExternalTransferBlocker, AiSecurityDataProtectionAction>
    >
  >({});
  const [externalAppActions, setExternalAppActions] =
    useState<AiSecurityExternalAppActions>({});
  const [ruleDraft, setRuleDraft] = useState<AiSecurityRulePayload>(() =>
    emptyAiSecurityRuleDraft(),
  );
  const [ruleSelectedUser, setRuleSelectedUser] =
    useState<AiSecuritySelectedUser | null>(null);
  const [ruleTermsText, setRuleTermsText] = useState('');
  const [editingRuleId, setEditingRuleId] = useState<string | null>(null);
  const [ruleEditorOpen, setRuleEditorOpen] = useState(false);
  const [ruleQuery, setRuleQuery] = useState('');
  const [exceptionDraft, setExceptionDraft] =
    useState<AiSecurityExternalTransferExceptionPayload>(() =>
      emptyAiSecurityExceptionDraft(),
    );
  const [exceptionSelectedUser, setExceptionSelectedUser] =
    useState<AiSecuritySelectedUser | null>(null);
  const [editingExceptionId, setEditingExceptionId] = useState<string | null>(
    null,
  );
  const [exceptionEditorOpen, setExceptionEditorOpen] = useState(false);
  const [exceptionQuery, setExceptionQuery] = useState('');
  const [simulationDraft, setSimulationDraft] =
    useState<AiSecuritySimulationPayload>({
      workspace_id: null,
      actor_user_id: null,
      org_unit_id: null,
      app_id: null,
      task_kind: null,
      capability: 'llm',
      provider: null,
      content_origin: 'user_prompt',
      source_kinds: [],
      sensitivity_labels: [],
      sample_text: '',
    });
  const [simulationSelectedUser, setSimulationSelectedUser] =
    useState<AiSecuritySelectedUser | null>(null);
  const [simulation, setSimulation] =
    useState<AiSecuritySimulationResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [monitoringLoading, setMonitoringLoading] = useState(false);
  const [detectedValueGroupMode, setDetectedValueGroupMode] = useState<
    'stored' | 'privacy' | null
  >(null);
  const [detectedValueGroups, setDetectedValueGroups] = useState<
    AiSecurityDetectedValueGroup[]
  >([]);
  const [detectedValueGroupTotal, setDetectedValueGroupTotal] = useState(0);
  const [detectedValueGroupOffset, setDetectedValueGroupOffset] = useState(0);
  const [detectedValueGroupQuery, setDetectedValueGroupQuery] = useState('');
  const [appliedDetectedValueGroupQuery, setAppliedDetectedValueGroupQuery] =
    useState('');
  const [detectedValueGroupLoading, setDetectedValueGroupLoading] =
    useState(false);
  const [detectedValueGroupError, setDetectedValueGroupError] = useState<
    string | null
  >(null);
  const [detectedValueDetailGroup, setDetectedValueDetailGroup] =
    useState<AiSecurityDetectedValueGroup | null>(null);
  const [detectedValueDetails, setDetectedValueDetails] = useState<
    AiSecurityDetectedValueStat[]
  >([]);
  const [detectedValueDetailTotal, setDetectedValueDetailTotal] = useState(0);
  const [detectedValueDetailOffset, setDetectedValueDetailOffset] = useState(0);
  const [detectedValueDetailQuery, setDetectedValueDetailQuery] = useState('');
  const [appliedDetectedValueDetailQuery, setAppliedDetectedValueDetailQuery] =
    useState('');
  const [detectedValueDetailLoading, setDetectedValueDetailLoading] =
    useState(false);
  const [detectedValueDetailError, setDetectedValueDetailError] = useState<
    string | null
  >(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [nextSummary, nextOrgUnits, nextWorkspaces] = await Promise.all([
        getAdminAiSecuritySummary(token),
        listOrgUnits(token, { includeInactive: true }),
        listWorkspaces(token, { includeArchived: true }),
      ]);
      setSummary(nextSummary);
      setOrgUnits(nextOrgUnits);
      setWorkspaces(nextWorkspaces);
      setDataTermsText(
        aiSecurityTermsText(nextSummary.data_protection.custom_block_terms),
      );
      setDataBlockerActions(nextSummary.data_protection.blocker_actions ?? {});
      setExternalAppActions(
        nextSummary.data_protection.external_app_actions ?? {},
      );
    } catch (caughtError) {
      toast.error(
        getErrorMessage(caughtError, t('admin.console.aiSecurity.loadFailed')),
      );
    } finally {
      setLoading(false);
    }
  }, [t, toast, token]);

  const loadMonitoring = useCallback(async () => {
    setMonitoringLoading(true);
    try {
      const response = await getAdminAiSecurityMonitoring(token, {
        from_date: monitoringDateRange.fromDate,
        to_date: monitoringDateRange.toDate,
        limit: 50,
      });
      setMonitoring(response);
    } catch (caughtError) {
      toast.error(
        getErrorMessage(
          caughtError,
          t('admin.console.aiSecurity.monitoring.loadFailed'),
        ),
      );
    } finally {
      setMonitoringLoading(false);
    }
  }, [
    monitoringDateRange.fromDate,
    monitoringDateRange.toDate,
    t,
    toast,
    token,
  ]);

  const loadDetectedValueGroups = useCallback(async () => {
    if (!detectedValueGroupMode) {
      return;
    }
    setDetectedValueGroupLoading(true);
    setDetectedValueGroupError(null);
    try {
      const response: AiSecurityDetectedValueGroupsResponse =
        await getAdminAiSecurityDetectedValueGroups(token, {
          from_date: monitoringDateRange.fromDate,
          limit: AI_SECURITY_DETECTED_VALUE_PAGE_SIZE,
          offset: detectedValueGroupOffset,
          privacy_filter: detectedValueGroupMode === 'privacy',
          q: appliedDetectedValueGroupQuery,
          to_date: monitoringDateRange.toDate,
        });
      setDetectedValueGroups(response.items);
      setDetectedValueGroupTotal(response.total);
    } catch (caughtError) {
      setDetectedValueGroupError(
        getErrorMessage(
          caughtError,
          t('admin.console.aiSecurity.monitoring.detectedValues.loadFailed'),
        ),
      );
    } finally {
      setDetectedValueGroupLoading(false);
    }
  }, [
    appliedDetectedValueGroupQuery,
    detectedValueGroupMode,
    detectedValueGroupOffset,
    monitoringDateRange.fromDate,
    monitoringDateRange.toDate,
    t,
    token,
  ]);

  const loadDetectedValueDetails = useCallback(async () => {
    if (!detectedValueDetailGroup) {
      return;
    }
    setDetectedValueDetailLoading(true);
    setDetectedValueDetailError(null);
    try {
      const response: AiSecurityDetectedValueDetailsResponse =
        await getAdminAiSecurityDetectedValueDetails(token, {
          blocker_type: detectedValueDetailGroup.blocker_type,
          detector: detectedValueDetailGroup.detector,
          entity_type: detectedValueDetailGroup.entity_type,
          from_date: monitoringDateRange.fromDate,
          limit: AI_SECURITY_DETECTED_VALUE_PAGE_SIZE,
          offset: detectedValueDetailOffset,
          q: appliedDetectedValueDetailQuery,
          to_date: monitoringDateRange.toDate,
        });
      setDetectedValueDetails(response.items);
      setDetectedValueDetailTotal(response.total);
    } catch (caughtError) {
      setDetectedValueDetailError(
        getErrorMessage(
          caughtError,
          t(
            'admin.console.aiSecurity.monitoring.detectedValues.detailLoadFailed',
          ),
        ),
      );
    } finally {
      setDetectedValueDetailLoading(false);
    }
  }, [
    appliedDetectedValueDetailQuery,
    detectedValueDetailGroup,
    detectedValueDetailOffset,
    monitoringDateRange.fromDate,
    monitoringDateRange.toDate,
    t,
    token,
  ]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (tab === 'monitoring') {
      void loadMonitoring();
    }
  }, [loadMonitoring, tab]);

  useEffect(() => {
    if (detectedValueGroupMode) {
      void loadDetectedValueGroups();
    }
  }, [detectedValueGroupMode, loadDetectedValueGroups]);

  useEffect(() => {
    if (detectedValueDetailGroup) {
      void loadDetectedValueDetails();
    }
  }, [detectedValueDetailGroup, loadDetectedValueDetails]);

  const resetRuleDraft = () => {
    setEditingRuleId(null);
    setRuleEditorOpen(false);
    setRuleDraft(emptyAiSecurityRuleDraft());
    setRuleSelectedUser(null);
    setRuleTermsText('');
  };

  const resetExceptionDraft = () => {
    setEditingExceptionId(null);
    setExceptionEditorOpen(false);
    setExceptionDraft(emptyAiSecurityExceptionDraft());
    setExceptionSelectedUser(null);
  };

  const openNewRuleEditor = () => {
    resetRuleDraft();
    setRuleEditorOpen(true);
  };

  const openNewExceptionEditor = () => {
    resetExceptionDraft();
    setExceptionEditorOpen(true);
  };

  const saveDataProtection = async () => {
    setSaving(true);
    try {
      const nextData = await updateAdminAiSecurityDataProtection(token, {
        custom_block_terms: parseAiSecurityTerms(dataTermsText),
        blocker_actions: dataBlockerActions,
        external_app_actions: externalAppActions,
      });
      setSummary((current) =>
        current ? { ...current, data_protection: nextData } : current,
      );
      setDataTermsText(aiSecurityTermsText(nextData.custom_block_terms));
      setDataBlockerActions(nextData.blocker_actions ?? {});
      setExternalAppActions(nextData.external_app_actions ?? {});
      toast.success(t('admin.console.aiSecurity.data.saved'));
    } catch (caughtError) {
      toast.error(
        getErrorMessage(
          caughtError,
          t('admin.console.aiSecurity.data.saveFailed'),
        ),
      );
    } finally {
      setSaving(false);
    }
  };

  const toggleAiSecurityEnforcement = async (enabled: boolean) => {
    setSaving(true);
    try {
      const nextData = await updateAdminAiSecurityEnforcement(token, {
        enforcement_enabled: enabled,
        enforcement_disabled_reason: enabled
          ? ''
          : t('admin.console.aiSecurity.enforcement.defaultDisabledReason'),
      });
      setSummary((current) =>
        current ? { ...current, data_protection: nextData } : current,
      );
      setDataTermsText(aiSecurityTermsText(nextData.custom_block_terms));
      setDataBlockerActions(nextData.blocker_actions ?? {});
      setExternalAppActions(nextData.external_app_actions ?? {});
      toast.success(
        t(
          enabled
            ? 'admin.console.aiSecurity.enforcement.enabledToast'
            : 'admin.console.aiSecurity.enforcement.disabledToast',
        ),
      );
    } catch (caughtError) {
      toast.error(
        getErrorMessage(
          caughtError,
          t('admin.console.aiSecurity.enforcement.saveFailed'),
        ),
      );
    } finally {
      setSaving(false);
    }
  };

  const saveRule = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    const taskKinds = aiSecurityTaskKindsFromScope(ruleDraft);
    const payload: AiSecurityRulePayload = {
      ...ruleDraft,
      name: ruleDraft.name.trim(),
      description: ruleDraft.description.trim(),
      user_id: ruleDraft.user_id ? ruleDraft.user_id.trim() : null,
      org_unit_id: ruleDraft.org_unit_id || null,
      workspace_id: ruleDraft.workspace_id || null,
      app_id: ruleDraft.app_id ? ruleDraft.app_id.trim() : null,
      task_kind: taskKinds.length === 1 ? taskKinds[0] : null,
      task_kinds: taskKinds,
      capability: ruleDraft.capability ? ruleDraft.capability.trim() : null,
      provider: ruleDraft.provider ? ruleDraft.provider.trim() : null,
      custom_block_terms: parseAiSecurityTerms(ruleTermsText),
    };
    try {
      if (editingRuleId) {
        await updateAdminAiSecurityRule(token, editingRuleId, payload);
        toast.success(t('admin.console.aiSecurity.rules.updated'));
      } else {
        await createAdminAiSecurityRule(token, payload);
        toast.success(t('admin.console.aiSecurity.rules.created'));
      }
      resetRuleDraft();
      await load();
    } catch (caughtError) {
      toast.error(
        getErrorMessage(
          caughtError,
          t('admin.console.aiSecurity.rules.saveFailed'),
        ),
      );
    } finally {
      setSaving(false);
    }
  };

  const deleteRule = async (ruleId: string) => {
    setSaving(true);
    try {
      await deleteAdminAiSecurityRule(token, ruleId);
      if (editingRuleId === ruleId) {
        resetRuleDraft();
      }
      toast.success(t('admin.console.aiSecurity.rules.deleted'));
      await load();
    } catch (caughtError) {
      toast.error(
        getErrorMessage(
          caughtError,
          t('admin.console.aiSecurity.rules.deleteFailed'),
        ),
      );
    } finally {
      setSaving(false);
    }
  };

  const saveException = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    const taskKinds = aiSecurityTaskKindsFromScope(exceptionDraft);
    const payload: AiSecurityExternalTransferExceptionPayload = {
      ...exceptionDraft,
      name: exceptionDraft.name.trim(),
      description: exceptionDraft.description.trim(),
      user_id: exceptionDraft.user_id ? exceptionDraft.user_id.trim() : null,
      org_unit_id: exceptionDraft.org_unit_id || null,
      workspace_id: exceptionDraft.workspace_id || null,
      app_id: exceptionDraft.app_id ? exceptionDraft.app_id.trim() : null,
      task_kind: taskKinds.length === 1 ? taskKinds[0] : null,
      task_kinds: taskKinds,
      capability: exceptionDraft.capability
        ? exceptionDraft.capability.trim()
        : null,
      provider: exceptionDraft.provider ? exceptionDraft.provider.trim() : null,
      allowed_blocker_types: exceptionDraft.allowed_blocker_types.filter(
        (item) => AI_SECURITY_EXCEPTION_BLOCKERS.includes(item),
      ),
      reason: exceptionDraft.reason.trim(),
      expires_at: aiSecurityIsoFromDateTimeLocal(exceptionDraft.expires_at),
    };
    try {
      if (editingExceptionId) {
        await updateAdminAiSecurityExternalTransferException(
          token,
          editingExceptionId,
          payload,
        );
        toast.success(t('admin.console.aiSecurity.exceptions.updated'));
      } else {
        await createAdminAiSecurityExternalTransferException(token, payload);
        toast.success(t('admin.console.aiSecurity.exceptions.created'));
      }
      resetExceptionDraft();
      await load();
    } catch (caughtError) {
      toast.error(
        getErrorMessage(
          caughtError,
          t('admin.console.aiSecurity.exceptions.saveFailed'),
        ),
      );
    } finally {
      setSaving(false);
    }
  };

  const deleteException = async (exceptionId: string) => {
    setSaving(true);
    try {
      await deleteAdminAiSecurityExternalTransferException(token, exceptionId);
      if (editingExceptionId === exceptionId) {
        resetExceptionDraft();
      }
      toast.success(t('admin.console.aiSecurity.exceptions.deleted'));
      await load();
    } catch (caughtError) {
      toast.error(
        getErrorMessage(
          caughtError,
          t('admin.console.aiSecurity.exceptions.deleteFailed'),
        ),
      );
    } finally {
      setSaving(false);
    }
  };

  const executeSimulation = useCallback(async () => {
    setSaving(true);
    try {
      const result = await simulateAdminAiSecurityPolicy(token, {
        ...simulationDraft,
        workspace_id: simulationDraft.workspace_id || null,
        actor_user_id: simulationDraft.actor_user_id || null,
        org_unit_id: simulationDraft.org_unit_id || null,
        app_id: simulationDraft.app_id || null,
        task_kind: simulationDraft.task_kind || null,
        capability: simulationDraft.capability || null,
        provider: simulationDraft.provider || null,
        content_origin: simulationDraft.content_origin || null,
      });
      setSimulation(result);
    } catch (caughtError) {
      toast.error(
        getErrorMessage(
          caughtError,
          t('admin.console.aiSecurity.simulator.failed'),
        ),
      );
    } finally {
      setSaving(false);
    }
  }, [simulationDraft, t, toast, token]);

  const runSimulation = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void executeSimulation();
  };

  const rules = useMemo(() => summary?.rules ?? [], [summary?.rules]);
  const exceptions = useMemo(
    () => summary?.exceptions ?? [],
    [summary?.exceptions],
  );
  const filteredRules = useMemo(() => {
    const normalized = ruleQuery.trim().toLocaleLowerCase();
    if (!normalized) return rules;
    return rules.filter((rule) =>
      [
        rule.name,
        rule.description,
        rule.app_id,
        ...aiSecurityTaskKindsFromScope(rule),
        rule.capability,
        rule.provider,
        rule.user_name,
        rule.org_unit_name,
        rule.workspace_name,
      ]
        .filter(aiSecurityPresent)
        .join(' ')
        .toLocaleLowerCase()
        .includes(normalized),
    );
  }, [ruleQuery, rules]);
  const filteredExceptions = useMemo(() => {
    const normalized = exceptionQuery.trim().toLocaleLowerCase();
    if (!normalized) return exceptions;
    return exceptions.filter((exception) =>
      [
        exception.name,
        exception.description,
        exception.reason,
        exception.app_id,
        ...aiSecurityTaskKindsFromScope(exception),
        exception.capability,
        exception.provider,
        exception.user_name,
        exception.org_unit_name,
        exception.workspace_name,
        ...exception.allowed_blocker_types,
      ]
        .filter(aiSecurityPresent)
        .join(' ')
        .toLocaleLowerCase()
        .includes(normalized),
    );
  }, [exceptionQuery, exceptions]);
  const dataProtection = summary?.data_protection;
  const aiSecurityEnforcementEnabled =
    dataProtection?.enforcement_enabled ?? false;
  const privacyFilterReady =
    dataProtection?.privacy_filter_ready ??
    dataProtection?.privacy_filter_enabled ??
    false;
  const dataHasMaskAction =
    Object.values(dataBlockerActions).some(
      (action) => action === 'mask_and_send',
    ) ||
    Object.values(externalAppActions).some((actions) =>
      Object.values(actions ?? {}).some((action) => action === 'mask_and_send'),
    );
  const conditionOptions = summary?.condition_options;
  const aiSecurityExternalAppCandidates = useMemo<
    AiSecurityExternalAppCandidate[]
  >(
    () => summary?.external_app_candidates ?? [],
    [summary?.external_app_candidates],
  );
  const aiSecurityAppOptions = useMemo<AiSecurityAppOption[]>(() => {
    const byValue = new Map<string, AiSecurityAppOption>();
    const addOption = (
      value: string | null | undefined,
      next: Omit<AiSecurityAppOption, 'value'> = {},
    ) => {
      const normalized = value?.trim();
      if (!normalized) return;
      const current = byValue.get(normalized);
      byValue.set(normalized, {
        ...current,
        ...next,
        description: next.description ?? current?.description ?? null,
        label:
          next.label ??
          current?.label ??
          t(`shell:apps.${normalized}`, { defaultValue: normalized }),
        value: normalized,
      });
    };

    for (const option of conditionOptions?.apps ?? []) {
      addOption(option.value, {
        label: t(`shell:apps.${option.value}`, {
          defaultValue: option.label ?? option.value,
        }),
      });
    }
    for (const option of conditionOptions?.external_apps ?? []) {
      addOption(option.value, {
        label: t(`shell:apps.${option.value}`, {
          defaultValue: option.label ?? option.value,
        }),
      });
    }
    for (const candidate of aiSecurityExternalAppCandidates) {
      addOption(candidate.app_id, {
        description: candidate.description,
        label: t(`shell:apps.${candidate.app_id}`, {
          defaultValue: candidate.app_label ?? candidate.app_id,
        }),
      });
    }
    for (const appId of Object.keys(externalAppActions)) {
      addOption(appId);
    }
    for (const appId of rules.map((rule) => rule.app_id)) {
      addOption(appId);
    }
    for (const appId of exceptions.map((exception) => exception.app_id)) {
      addOption(appId);
    }

    return Array.from(byValue.values()).sort((a, b) =>
      (a.label ?? a.value).localeCompare(b.label ?? b.value),
    );
  }, [
    aiSecurityExternalAppCandidates,
    conditionOptions?.apps,
    conditionOptions?.external_apps,
    exceptions,
    externalAppActions,
    rules,
    t,
  ]);
  const aiSecurityTaskOptions = useMemo(
    () =>
      aiSecurityConditionOptions(
        (conditionOptions?.task_kinds ?? []).map((option) => ({
          value: option.value,
          label: aiSecurityTranslatedTaskDescription(
            t,
            option.value,
            option.label ?? option.value,
          ),
        })),
        rules.flatMap((rule) => aiSecurityTaskKindsFromScope(rule)),
        exceptions.flatMap((exception) =>
          aiSecurityTaskKindsFromScope(exception),
        ),
      ),
    [conditionOptions?.task_kinds, exceptions, rules, t],
  );
  const aiSecurityTaskOptionsByApp = useMemo(() => {
    const byApp = new Map<string, AiSecurityConditionOption[]>();
    for (const candidate of aiSecurityExternalAppCandidates) {
      byApp.set(
        candidate.app_id,
        aiSecurityConditionOptions(byApp.get(candidate.app_id) ?? [], [
          {
            value: candidate.task_kind,
            label: aiSecurityTranslatedTaskDescription(
              t,
              candidate.task_kind,
              candidate.description ?? candidate.task_kind,
            ),
          },
        ]),
      );
    }
    return byApp;
  }, [aiSecurityExternalAppCandidates, t]);
  const aiSecurityTaskOptionsForApp = useCallback(
    (
      appId: string | null | undefined,
      selectedTaskKinds?: readonly string[] | string | null,
    ) => {
      const appOptions = appId
        ? (aiSecurityTaskOptionsByApp.get(appId) ?? aiSecurityTaskOptions)
        : aiSecurityTaskOptions;
      const selectedValues = Array.isArray(selectedTaskKinds)
        ? selectedTaskKinds
        : selectedTaskKinds
          ? [selectedTaskKinds]
          : [];
      return aiSecurityConditionOptions(appOptions, selectedValues);
    },
    [aiSecurityTaskOptions, aiSecurityTaskOptionsByApp],
  );
  const aiSecurityTaskBelongsToApp = useCallback(
    (appId: string | null | undefined, taskKind: string | null | undefined) => {
      if (!appId || !taskKind) return true;
      const appOptions = aiSecurityTaskOptionsByApp.get(appId);
      return (
        !appOptions || appOptions.some((option) => option.value === taskKind)
      );
    },
    [aiSecurityTaskOptionsByApp],
  );
  const aiSecurityCapabilityOptions = useMemo(
    () =>
      aiSecurityConditionOptions(
        conditionOptions?.capabilities ?? [],
        rules.map((rule) => rule.capability).filter(aiSecurityPresent),
        exceptions
          .map((exception) => exception.capability)
          .filter(aiSecurityPresent),
      ),
    [conditionOptions?.capabilities, exceptions, rules],
  );
  const aiSecurityProviderOptions = useMemo(
    () =>
      aiSecurityConditionOptions(
        conditionOptions?.providers ?? [],
        rules.map((rule) => rule.provider).filter(aiSecurityPresent),
        exceptions
          .map((exception) => exception.provider)
          .filter(aiSecurityPresent),
      ),
    [conditionOptions?.providers, exceptions, rules],
  );
  const aiSecurityContentOriginOptions = useMemo(
    () => aiSecurityConditionOptions(conditionOptions?.content_origins ?? []),
    [conditionOptions?.content_origins],
  );
  const externalRequiredSelectableAppOptions = useMemo(
    () =>
      aiSecurityAppOptions.filter(
        (option) => externalAppActions[option.value] == null,
      ),
    [aiSecurityAppOptions, externalAppActions],
  );
  const externalRequiredApps = useMemo(
    () =>
      Object.keys(externalAppActions)
        .map((appId) => {
          const option = aiSecurityAppOptions.find(
            (item) => item.value === appId,
          );
          return {
            appId,
            label:
              option?.label ??
              t(`shell:apps.${appId}`, { defaultValue: appId }),
          };
        })
        .sort((a, b) => a.label.localeCompare(b.label)),
    [aiSecurityAppOptions, externalAppActions, t],
  );
  const addExternalRequiredApp = useCallback(
    (appId: string | null) => {
      if (!appId) return;
      setExternalAppActions((current) => ({
        ...current,
        [appId]:
          current[appId] ??
          aiSecurityDefaultExternalAppActions(
            dataProtection?.mask_eligible_blockers ?? [],
          ),
      }));
    },
    [dataProtection?.mask_eligible_blockers],
  );
  const removeExternalRequiredApp = useCallback((appId: string) => {
    setExternalAppActions((current) => {
      const next = { ...current };
      delete next[appId];
      return next;
    });
  }, []);
  const monitoringPeriodPresetOptions = useMemo(
    () =>
      getUsagePeriodPresetOptions(t).filter((option) =>
        ['day', 'week', 'month'].includes(option.value),
      ),
    [t],
  );
  const monitoringTrendChart = useMemo(
    () =>
      monitoring ? buildAiSecurityMonitoringTrendChart(monitoring, t) : null,
    [monitoring, t],
  );
  const monitoringDetectorChart = useMemo(
    () =>
      monitoring ? buildAiSecurityDetectionDetectorChart(monitoring, t) : null,
    [monitoring, t],
  );
  const monitoringDetectionEntityChart = useMemo(
    () =>
      monitoring ? buildAiSecurityDetectionEntityChart(monitoring, t) : null,
    [monitoring, t],
  );
  const monitoringGeneratedAt = monitoring
    ? formatDateTime(monitoring.generated_at, {
        dateStyle: 'medium',
        locale,
        timeStyle: 'short',
        timeZone,
      })
    : null;
  const monitoringDateRangeLabel = monitoring
    ? t('admin.console.usage.dateRangeLabel', {
        from: monitoring.from_date,
        to: monitoring.to_date,
      })
    : t('admin.console.usage.dateRangeLabel', {
        from: monitoringDateRange.fromDate,
        to: monitoringDateRange.toDate,
      });

  const applyMonitoringDateRange = (nextRange: UsageDateRange) => {
    const normalizedRange = normalizeUsageDateRange(nextRange, todayDate);
    setMonitoringDraftDateRange(normalizedRange);
    setMonitoringDateRange(normalizedRange);
  };

  const handleMonitoringPresetChange = (preset: UsagePeriodPreset) => {
    setMonitoringPeriodPreset(preset);
    applyMonitoringDateRange(buildUsageDateRangePreset(preset, todayDate));
  };

  const handleMonitoringDateRangeSubmit = (
    event: React.FormEvent<HTMLFormElement>,
  ) => {
    event.preventDefault();
    setMonitoringPeriodPreset('custom');
    applyMonitoringDateRange(monitoringDraftDateRange);
  };

  const openDetectedValueGroupsDialog = (mode: 'stored' | 'privacy') => {
    setDetectedValueGroupMode(mode);
    setDetectedValueGroups([]);
    setDetectedValueGroupTotal(0);
    setDetectedValueGroupOffset(0);
    setDetectedValueGroupQuery('');
    setAppliedDetectedValueGroupQuery('');
    setDetectedValueGroupError(null);
  };

  const closeDetectedValueGroupsDialog = () => {
    setDetectedValueGroupMode(null);
    setDetectedValueGroupError(null);
  };

  const applyDetectedValueGroupSearch = (
    event: React.FormEvent<HTMLFormElement>,
  ) => {
    event.preventDefault();
    setDetectedValueGroupOffset(0);
    setAppliedDetectedValueGroupQuery(detectedValueGroupQuery.trim());
  };

  const openDetectedValueDetailsDialog = (
    group: AiSecurityDetectedValueGroup,
  ) => {
    if (!group.detail_available || group.detector === 'privacy_filter') {
      return;
    }
    setDetectedValueDetailGroup(group);
    setDetectedValueDetails([]);
    setDetectedValueDetailTotal(0);
    setDetectedValueDetailOffset(0);
    setDetectedValueDetailQuery('');
    setAppliedDetectedValueDetailQuery('');
    setDetectedValueDetailError(null);
  };

  const closeDetectedValueDetailsDialog = () => {
    setDetectedValueDetailGroup(null);
    setDetectedValueDetailError(null);
  };

  const applyDetectedValueDetailSearch = (
    event: React.FormEvent<HTMLFormElement>,
  ) => {
    event.preventDefault();
    setDetectedValueDetailOffset(0);
    setAppliedDetectedValueDetailQuery(detectedValueDetailQuery.trim());
  };

  return (
    <div className="space-y-3">
      <div className="flex min-w-0 items-start gap-2">
        <Tabs
          className="min-w-0 flex-1"
          value={tab}
          onValueChange={(value) => setTab(value as AiSecurityTab)}
        >
          <TabsList className="grid h-auto w-full grid-cols-3 gap-1 lg:grid-cols-6">
            {AI_SECURITY_TABS.map((item) => (
              <TabsTrigger
                className="min-w-0 justify-center whitespace-nowrap px-2"
                key={item}
                value={item}
              >
                {t(`admin.console.aiSecurity.tabs.${item}`)}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        <Button
          className="shrink-0"
          aria-label={t('admin.console.usage.refresh')}
          disabled={
            loading || saving || (tab === 'monitoring' && monitoringLoading)
          }
          onClick={() =>
            tab === 'monitoring' ? void loadMonitoring() : void load()
          }
          size="icon"
          title={t('admin.console.usage.refresh')}
          variant="secondary"
        >
          <RefreshCw size={16} />
        </Button>
      </div>

      <div
        className={`rounded-md border px-3 py-2 ${
          aiSecurityEnforcementEnabled
            ? 'border-app-success-border bg-app-success-bg text-app-success-text dark:border-app-success/30 dark:bg-app-success/10 dark:text-app-success-text'
            : 'border-app-warning-border bg-app-warning-bg text-app-warning-text dark:border-app-warning-border dark:bg-app-warning/10 dark:text-app-warning-text'
        }`}
      >
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 items-center gap-2">
            <ShieldCheck
              className={`shrink-0 ${
                aiSecurityEnforcementEnabled
                  ? 'text-app-success-text dark:text-app-success-text'
                  : 'text-app-warning-text dark:text-app-warning-text'
              }`}
              size={16}
            />
            <span className="app-text-body-sm whitespace-nowrap font-semibold text-current">
              {t('admin.console.aiSecurity.enforcement.title')}
            </span>
            <span className="shrink-0 whitespace-nowrap">
              <Badge tone={aiSecurityEnforcementEnabled ? 'green' : 'amber'}>
                {t(
                  aiSecurityEnforcementEnabled
                    ? 'admin.console.aiSecurity.enforcement.statusEnabled'
                    : 'admin.console.aiSecurity.enforcement.statusDisabled',
                )}
              </Badge>
            </span>
            <span className="sr-only">
              {t(
                aiSecurityEnforcementEnabled
                  ? 'admin.console.aiSecurity.enforcement.enabledDescription'
                  : 'admin.console.aiSecurity.enforcement.disabledDescription',
              )}
            </span>
          </div>
          <label className="inline-flex shrink-0 items-center gap-2 rounded-md border border-app-border bg-app-surface px-2.5 py-1.5">
            <input
              checked={aiSecurityEnforcementEnabled}
              disabled={loading || saving || !dataProtection}
              onChange={(event) =>
                void toggleAiSecurityEnforcement(event.target.checked)
              }
              role="switch"
              type="checkbox"
            />
            <span className="app-text-caption font-medium text-app-ink">
              {t('admin.console.aiSecurity.enforcement.switchLabel')}
            </span>
          </label>
        </div>
      </div>

      {tab === 'overview' ? (
        <div className="space-y-4">
          <SurfaceCard
            description={t('admin.console.aiSecurity.overview.description')}
            title={t('admin.console.aiSecurity.overview.title')}
          >
            {loading && !summary ? (
              <EmptyPanel
                description={t('admin.console.aiSecurity.loadingDescription')}
                title={t('admin.console.aiSecurity.loadingTitle')}
              />
            ) : (
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                <AiSecurityMetric
                  onClick={() => setTab('rules')}
                  label={t('admin.console.aiSecurity.metrics.activeRules')}
                  value={summary?.active_rule_count ?? 0}
                  detail={t('admin.console.aiSecurity.metrics.totalRules', {
                    count: rules.length,
                  })}
                />
                <AiSecurityMetric
                  onClick={() => setTab('exceptions')}
                  label={t('admin.console.aiSecurity.metrics.activeExceptions')}
                  value={summary?.active_exception_count ?? 0}
                  detail={t(
                    'admin.console.aiSecurity.metrics.totalExceptions',
                    {
                      count: exceptions.length,
                    },
                  )}
                />
                <AiSecurityMetric
                  onClick={() => setTab('data')}
                  label={t('admin.console.aiSecurity.metrics.blockTerms')}
                  value={dataProtection?.custom_block_terms.length ?? 0}
                  detail={t('admin.console.aiSecurity.metrics.mandatory', {
                    count: dataProtection?.mandatory_blockers.length ?? 0,
                  })}
                />
                <AiSecurityMetric
                  onClick={() => navigate('/admin/audit?scope=ai-security')}
                  label={t('admin.console.aiSecurity.metrics.audit24h')}
                  value={summary?.audit_log_count_24h ?? 0}
                  detail={t('admin.console.aiSecurity.metrics.auditDetail')}
                />
              </div>
            )}
          </SurfaceCard>
          <details className="rounded-md border border-app-border bg-app-surface">
            <summary className="app-text-body-sm cursor-pointer px-3 py-2 font-medium text-app-ink">
              {t('admin.console.aiSecurity.overview.howItWorks')}
            </summary>
            <div className="grid gap-2 border-t border-app-border p-3 lg:grid-cols-3">
              <AiSecurityGuidance
                description={t(
                  'admin.console.aiSecurity.overview.guidance.routing',
                )}
                title={t(
                  'admin.console.aiSecurity.overview.guidance.routingTitle',
                )}
              />
              <AiSecurityGuidance
                description={t(
                  'admin.console.aiSecurity.overview.guidance.protection',
                )}
                title={t(
                  'admin.console.aiSecurity.overview.guidance.protectionTitle',
                )}
              />
              <AiSecurityGuidance
                description={t(
                  'admin.console.aiSecurity.overview.guidance.audit',
                )}
                title={t(
                  'admin.console.aiSecurity.overview.guidance.auditTitle',
                )}
              />
            </div>
          </details>
        </div>
      ) : null}

      {tab === 'monitoring' ? (
        <div className="space-y-4">
          <SurfaceCard
            description={t('admin.console.aiSecurity.monitoring.description')}
            title={t('admin.console.aiSecurity.monitoring.title')}
          >
            <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
              <div
                aria-label={t(
                  'admin.console.aiSecurity.monitoring.periodInputLabel',
                )}
                className="flex flex-wrap gap-1"
                role="group"
              >
                {monitoringPeriodPresetOptions.map((option) => (
                  <Button
                    key={option.value}
                    onClick={() => handleMonitoringPresetChange(option.value)}
                    size="dense"
                    variant={
                      monitoringPeriodPreset === option.value
                        ? 'primary'
                        : 'secondary'
                    }
                  >
                    {option.label}
                  </Button>
                ))}
              </div>
              <form
                className="flex flex-col gap-2 sm:flex-row sm:items-center"
                onSubmit={handleMonitoringDateRangeSubmit}
              >
                <label className="flex items-center gap-2">
                  <span className="app-text-overline shrink-0 text-app-ink/55">
                    {t('admin.console.usage.fromDateLabel')}
                  </span>
                  <input
                    className={`${fieldClassName} h-9 w-full sm:w-36`}
                    max={monitoringDraftDateRange.toDate || todayDate}
                    onChange={(event) => {
                      setMonitoringPeriodPreset('custom');
                      setMonitoringDraftDateRange((current) => ({
                        ...current,
                        fromDate: event.target.value,
                      }));
                    }}
                    type="date"
                    value={monitoringDraftDateRange.fromDate}
                  />
                </label>
                <label className="flex items-center gap-2">
                  <span className="app-text-overline shrink-0 text-app-ink/55">
                    {t('admin.console.usage.toDateLabel')}
                  </span>
                  <input
                    className={`${fieldClassName} h-9 w-full sm:w-36`}
                    max={todayDate}
                    min={monitoringDraftDateRange.fromDate}
                    onChange={(event) => {
                      setMonitoringPeriodPreset('custom');
                      setMonitoringDraftDateRange((current) => ({
                        ...current,
                        toDate: event.target.value,
                      }));
                    }}
                    type="date"
                    value={monitoringDraftDateRange.toDate}
                  />
                </label>
                <Button
                  disabled={monitoringLoading}
                  size="dense"
                  type="submit"
                  variant="secondary"
                >
                  {t('admin.console.usage.applyDateRange')}
                </Button>
              </form>
            </div>
          </SurfaceCard>

          <div
            aria-label={t('admin.console.aiSecurity.monitoring.views.label')}
            className="flex gap-1 overflow-x-auto rounded-md border border-app-border bg-app-surface p-1"
            role="tablist"
          >
            {(['overview', 'detections', 'users', 'events'] as const).map(
              (view) => (
                <Button
                  aria-selected={monitoringView === view}
                  key={view}
                  onClick={() => setMonitoringView(view)}
                  role="tab"
                  size="dense"
                  variant={monitoringView === view ? 'primary' : 'ghost'}
                >
                  {t(`admin.console.aiSecurity.monitoring.views.${view}`)}
                </Button>
              ),
            )}
          </div>

          {monitoringLoading && !monitoring ? (
            <EmptyPanel
              description={t('admin.console.aiSecurity.monitoring.loading')}
              title={t('admin.console.aiSecurity.monitoring.loadingTitle')}
            />
          ) : monitoring ? (
            <>
              <SurfaceCard
                description={
                  monitoringGeneratedAt
                    ? t('admin.console.aiSecurity.monitoring.generatedAt', {
                        generatedAt: monitoringGeneratedAt,
                        range: monitoringDateRangeLabel,
                      })
                    : t(
                        'admin.console.aiSecurity.monitoring.summaryDescription',
                      )
                }
                title={t('admin.console.aiSecurity.monitoring.summaryTitle')}
              >
                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
                  <AiSecurityMetric
                    detail={monitoringDateRangeLabel}
                    label={t(
                      'admin.console.aiSecurity.monitoring.metrics.securityEvents',
                    )}
                    value={formatUsageNumber(
                      monitoring.totals.security_event_count,
                      locale,
                    )}
                  />
                  <AiSecurityMetric
                    detail={t(
                      'admin.console.aiSecurity.monitoring.metrics.hardBlockerDetail',
                      {
                        count: formatUsageNumber(
                          monitoring.totals.hard_blocker_count,
                          locale,
                        ),
                      },
                    )}
                    label={t(
                      'admin.console.aiSecurity.monitoring.metrics.blockedEvents',
                    )}
                    value={formatUsageNumber(
                      monitoring.totals.blocked_event_count,
                      locale,
                    )}
                  />
                  <AiSecurityMetric
                    detail={t(
                      'admin.console.aiSecurity.monitoring.metrics.maskedDetail',
                    )}
                    label={t(
                      'admin.console.aiSecurity.monitoring.metrics.maskedEvents',
                    )}
                    value={formatUsageNumber(
                      monitoring.totals.masked_event_count,
                      locale,
                    )}
                  />
                  <AiSecurityMetric
                    detail={t(
                      'admin.console.aiSecurity.monitoring.metrics.exceptionDetail',
                    )}
                    label={t(
                      'admin.console.aiSecurity.monitoring.metrics.exceptions',
                    )}
                    value={formatUsageNumber(
                      monitoring.totals.external_exception_count,
                      locale,
                    )}
                  />
                  <AiSecurityMetric
                    detail={t(
                      'admin.console.aiSecurity.monitoring.metrics.actorDetail',
                    )}
                    label={t(
                      'admin.console.aiSecurity.monitoring.metrics.actors',
                    )}
                    value={formatUsageNumber(
                      monitoring.totals.unique_actor_count,
                      locale,
                    )}
                  />
                </div>
              </SurfaceCard>

              {monitoringView === 'overview' ? (
                <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(300px,1fr)]">
                  <div className="min-w-0 space-y-4">
                    {monitoringTrendChart ? (
                      <BarChartCard
                        categories={monitoringTrendChart.categories}
                        emptyState={t(
                          'admin.console.aiSecurity.monitoring.charts.empty',
                        )}
                        series={monitoringTrendChart.series}
                        status={
                          monitoringTrendChart.categories.length > 0
                            ? 'ready'
                            : 'empty'
                        }
                        title={t(
                          'admin.console.aiSecurity.monitoring.charts.dailyTitle',
                        )}
                      />
                    ) : null}
                    <div className="grid gap-4 2xl:grid-cols-2">
                      {monitoringDetectorChart ? (
                        <BarChartCard
                          categories={monitoringDetectorChart.categories}
                          emptyState={t(
                            'admin.console.aiSecurity.monitoring.charts.empty',
                          )}
                          series={monitoringDetectorChart.series}
                          status={
                            monitoringDetectorChart.categories.length > 0
                              ? 'ready'
                              : 'empty'
                          }
                          title={t(
                            'admin.console.aiSecurity.monitoring.charts.detectorsTitle',
                          )}
                        />
                      ) : null}
                      {monitoringDetectionEntityChart ? (
                        <BarChartCard
                          categories={monitoringDetectionEntityChart.categories}
                          emptyState={t(
                            'admin.console.aiSecurity.monitoring.charts.empty',
                          )}
                          series={monitoringDetectionEntityChart.series}
                          status={
                            monitoringDetectionEntityChart.categories.length > 0
                              ? 'ready'
                              : 'empty'
                          }
                          title={t(
                            'admin.console.aiSecurity.monitoring.charts.detectedEntitiesTitle',
                          )}
                        />
                      ) : null}
                    </div>
                  </div>
                  <div className="space-y-4">
                    <AiSecurityMonitoringBreakdownList
                      emptyLabel={t(
                        'admin.console.aiSecurity.monitoring.breakdowns.empty',
                      )}
                      items={monitoring.blocked_by_reason}
                      labelFor={(key) =>
                        aiSecurityMonitoringReasonLabel(t, key)
                      }
                      locale={locale}
                      title={t(
                        'admin.console.aiSecurity.monitoring.breakdowns.reasons',
                      )}
                    />
                    <AiSecurityMonitoringBreakdownList
                      emptyLabel={t(
                        'admin.console.aiSecurity.monitoring.breakdowns.empty',
                      )}
                      items={monitoring.blocked_by_entity_type}
                      labelFor={(key) =>
                        aiSecurityMonitoringEntityLabel(t, key)
                      }
                      locale={locale}
                      title={t(
                        'admin.console.aiSecurity.monitoring.breakdowns.entities',
                      )}
                    />
                  </div>
                </div>
              ) : null}

              {monitoringView === 'detections' ? (
                <div className="grid gap-4 xl:grid-cols-2">
                  <SurfaceCard
                    description={t(
                      'admin.console.aiSecurity.monitoring.detectedValues.description',
                    )}
                    title={t(
                      'admin.console.aiSecurity.monitoring.detectedValues.title',
                    )}
                    actions={
                      <Button
                        onClick={() => openDetectedValueGroupsDialog('stored')}
                        size="dense"
                        type="button"
                        variant="secondary"
                      >
                        {t('admin.console.aiSecurity.monitoring.viewMore')}
                      </Button>
                    }
                  >
                    <AiSecurityDetectedValueGroupTable
                      emptyDescription={t(
                        'admin.console.aiSecurity.monitoring.detectedValues.emptyDescription',
                      )}
                      emptyTitle={t(
                        'admin.console.aiSecurity.monitoring.detectedValues.emptyTitle',
                      )}
                      items={monitoring.detected_value_groups}
                      locale={locale}
                      onSelect={openDetectedValueDetailsDialog}
                      t={t}
                      timeZone={timeZone}
                    />
                  </SurfaceCard>
                  <SurfaceCard
                    description={t(
                      'admin.console.aiSecurity.monitoring.privacyFilter.description',
                    )}
                    title={t(
                      'admin.console.aiSecurity.monitoring.privacyFilter.title',
                    )}
                    actions={
                      <Button
                        onClick={() => openDetectedValueGroupsDialog('privacy')}
                        size="dense"
                        type="button"
                        variant="secondary"
                      >
                        {t('admin.console.aiSecurity.monitoring.viewMore')}
                      </Button>
                    }
                  >
                    <AiSecurityDetectedValueGroupTable
                      emptyDescription={t(
                        'admin.console.aiSecurity.monitoring.privacyFilter.emptyDescription',
                      )}
                      emptyTitle={t(
                        'admin.console.aiSecurity.monitoring.privacyFilter.emptyTitle',
                      )}
                      items={monitoring.privacy_filter_groups}
                      locale={locale}
                      privacyFilterOnly
                      t={t}
                      timeZone={timeZone}
                    />
                  </SurfaceCard>
                </div>
              ) : null}

              {monitoringView === 'users' ? (
                <SurfaceCard
                  description={t(
                    'admin.console.aiSecurity.monitoring.userTable.description',
                  )}
                  title={t(
                    'admin.console.aiSecurity.monitoring.userTable.title',
                  )}
                >
                  <AiSecurityMonitoringUserTable
                    items={monitoring.blocked_by_user}
                    loading={monitoringLoading}
                    locale={locale}
                    t={t}
                    timeZone={timeZone}
                  />
                </SurfaceCard>
              ) : null}

              {monitoringView === 'events' ? (
                <SurfaceCard
                  description={t(
                    'admin.console.aiSecurity.monitoring.recent.description',
                  )}
                  title={t('admin.console.aiSecurity.monitoring.recent.title')}
                >
                  <AuditLogList
                    emptyDescription={t(
                      'admin.console.aiSecurity.monitoring.recent.emptyDescription',
                    )}
                    emptyTitle={t(
                      'admin.console.aiSecurity.monitoring.recent.emptyTitle',
                    )}
                    items={monitoring.blocked_events}
                    loading={monitoringLoading}
                    loadingDescription={t(
                      'admin.console.aiSecurity.monitoring.loading',
                    )}
                    loadingTitle={t(
                      'admin.console.aiSecurity.monitoring.loadingTitle',
                    )}
                    locale={locale}
                    timeZone={timeZone}
                  />
                </SurfaceCard>
              ) : null}
            </>
          ) : (
            <EmptyPanel
              description={t(
                'admin.console.aiSecurity.monitoring.emptyDescription',
              )}
              title={t('admin.console.aiSecurity.monitoring.emptyTitle')}
            />
          )}
        </div>
      ) : null}

      {tab === 'data' ? (
        <SurfaceCard
          description={t('admin.console.aiSecurity.data.description')}
          title={t('admin.console.aiSecurity.data.title')}
          actions={
            <Button
              disabled={saving || loading}
              onClick={() => void saveDataProtection()}
              variant="primary"
            >
              <Save size={16} />
              {t('common:actions.save')}
            </Button>
          }
        >
          <div className="space-y-4">
            <details className="rounded-md border border-app-border bg-app-surface">
              <summary className="app-text-body-sm cursor-pointer px-3 py-2 font-medium text-app-ink">
                {t('admin.console.aiSecurity.data.guidanceTitle')}
              </summary>
              <div className="grid gap-2 border-t border-app-border p-3 lg:grid-cols-3">
                <AiSecurityGuidance
                  description={t(
                    'admin.console.aiSecurity.data.guidance.blockBeforeExternal',
                  )}
                  title={t('admin.console.aiSecurity.data.guidance.blockTitle')}
                />
                <AiSecurityGuidance
                  description={t(
                    'admin.console.aiSecurity.data.guidance.auditSafe',
                  )}
                  title={t('admin.console.aiSecurity.data.guidance.auditTitle')}
                />
                <AiSecurityGuidance
                  description={t(
                    'admin.console.aiSecurity.data.guidance.customTerms',
                  )}
                  title={t('admin.console.aiSecurity.data.guidance.termsTitle')}
                />
              </div>
            </details>
            <details className="rounded-md border border-app-border bg-app-surface">
              <summary className="app-text-body-sm cursor-pointer px-3 py-2 font-medium text-app-ink">
                <span className="ml-1 inline-flex flex-wrap items-center gap-2">
                  {t('admin.console.aiSecurity.data.masking.title')}
                  <Badge tone={privacyFilterReady ? 'green' : 'amber'}>
                    {t(
                      privacyFilterReady
                        ? 'admin.console.aiSecurity.data.privacyFilterStates.enabled'
                        : 'admin.console.aiSecurity.data.privacyFilterStates.disabled',
                      {
                        device:
                          dataProtection?.privacy_filter_device ??
                          t('common:empty.none'),
                      },
                    )}
                  </Badge>
                </span>
              </summary>
              <div className="space-y-3 border-t border-app-border p-3">
                <p className="app-text-body-sm text-app-ink/65">
                  {t('admin.console.aiSecurity.data.masking.description')}
                </p>
                {!privacyFilterReady ? (
                  <p className="app-text-caption text-app-warning-text">
                    {t(
                      'admin.console.aiSecurity.data.privacyFilterStates.detail',
                      {
                        status:
                          dataProtection?.privacy_filter_status ??
                          t('common:empty.none'),
                        detail:
                          dataProtection?.privacy_filter_detail ??
                          dataProtection?.privacy_filter_checkpoint ??
                          t('common:empty.none'),
                      },
                    )}
                  </p>
                ) : null}
                <div className="flex flex-wrap gap-2">
                  {(dataProtection?.mask_eligible_blockers ?? []).map(
                    (blocker) => (
                      <Badge key={blocker} tone="purple">
                        {t(`admin.console.aiSecurity.blockers.${blocker}`)}
                      </Badge>
                    ),
                  )}
                </div>
                <p className="app-text-body-sm text-app-ink/65">
                  {t('admin.console.aiSecurity.data.masking.failClosed')}
                </p>
              </div>
            </details>
            {dataHasMaskAction && !privacyFilterReady ? (
              <div className="app-text-body-sm rounded-md border border-app-warning-border bg-app-warning-bg p-2 text-app-warning-text">
                {t(
                  'admin.console.aiSecurity.data.masking.privacyFilterWarning',
                )}
              </div>
            ) : null}
            <div className="space-y-2">
              <p className="app-text-body-sm text-app-ink/65">
                {t('admin.console.aiSecurity.data.customTermsBehavior')}
              </p>
              <AiSecurityTermsTagInput
                emptyLabel={t('admin.console.aiSecurity.data.customTermsEmpty')}
                help={t('admin.console.aiSecurity.data.customTermsHelp')}
                label={t('admin.console.aiSecurity.data.customTerms')}
                onChange={setDataTermsText}
                placeholder={t(
                  'admin.console.aiSecurity.data.customTermsPlaceholder',
                )}
                removeLabel={t(
                  'admin.console.aiSecurity.data.customTermsRemove',
                )}
                summaryLabel={t(
                  'admin.console.aiSecurity.data.customTermsCount',
                  {
                    count: parseAiSecurityTerms(dataTermsText).length,
                  },
                )}
                value={dataTermsText}
              />
            </div>
            <div className="space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div className="app-text-control text-app-ink">
                    {t('admin.console.aiSecurity.data.externalApps.title')}
                  </div>
                  <p className="app-text-body-sm mt-1 text-app-ink/60">
                    {t(
                      'admin.console.aiSecurity.data.externalApps.description',
                    )}
                  </p>
                </div>
                <Badge
                  tone={externalRequiredApps.length > 0 ? 'amber' : 'default'}
                >
                  {t('admin.console.aiSecurity.routing.externalRequiredCount', {
                    count: externalRequiredApps.length,
                  })}
                </Badge>
              </div>
              <div className="max-w-xl">
                <AiSecurityAppPicker
                  allLabel={t(
                    'admin.console.aiSecurity.data.externalApps.addApp',
                  )}
                  clearLabel={t('admin.console.aiSecurity.rules.clearApp')}
                  help={t('admin.console.aiSecurity.data.externalApps.addHelp')}
                  label={t('admin.console.aiSecurity.data.externalApps.addApp')}
                  noResultsLabel={t(
                    'admin.console.aiSecurity.rules.noAppResults',
                  )}
                  onChange={addExternalRequiredApp}
                  options={externalRequiredSelectableAppOptions}
                  searchPlaceholder={t(
                    'admin.console.aiSecurity.rules.appSearchPlaceholder',
                  )}
                  value={null}
                />
              </div>
              {externalRequiredApps.length > 0 ? (
                <div className="overflow-x-auto rounded-md border border-app-border">
                  <table className="w-full min-w-[860px] border-collapse">
                    <thead className="bg-app-surface-sidebar">
                      <tr>
                        <HeadCell dense>
                          {t(
                            'admin.console.aiSecurity.routingOverview.columns.app',
                          )}
                        </HeadCell>
                        {(dataProtection?.mask_eligible_blockers ?? []).map(
                          (blocker) => (
                            <HeadCell dense key={blocker}>
                              {t(
                                `admin.console.aiSecurity.blockers.${blocker}`,
                              )}
                            </HeadCell>
                          ),
                        )}
                      </tr>
                    </thead>
                    <tbody>
                      {externalRequiredApps.map((app) => {
                        const actions =
                          externalAppActions[app.appId] ??
                          aiSecurityDefaultExternalAppActions(
                            dataProtection?.mask_eligible_blockers ?? [],
                          );
                        return (
                          <tr key={app.appId}>
                            <BodyCell dense>
                              <div className="flex items-center gap-1">
                                <div className="app-text-body-sm min-w-0 flex-1 truncate font-medium text-app-ink">
                                  {app.label}
                                </div>
                                <button
                                  aria-label={t(
                                    'admin.console.aiSecurity.data.externalApps.removeApp',
                                    { name: app.label },
                                  )}
                                  className="shrink-0 text-app-ink/40 hover:text-app-danger-text"
                                  onClick={() =>
                                    removeExternalRequiredApp(app.appId)
                                  }
                                  type="button"
                                >
                                  <X size={13} />
                                </button>
                              </div>
                              <div className="app-text-caption text-app-ink/45">
                                {app.appId}
                              </div>
                            </BodyCell>
                            {(dataProtection?.mask_eligible_blockers ?? []).map(
                              (blocker) => {
                                const action = aiSecurityExternalAppAction(
                                  actions,
                                  blocker,
                                );
                                return (
                                  <BodyCell dense key={blocker}>
                                    <select
                                      aria-label={`${app.label} ${t(
                                        `admin.console.aiSecurity.blockers.${blocker}`,
                                      )}`}
                                      className="app-field-input-sm"
                                      onChange={(event) =>
                                        setExternalAppActions((current) => ({
                                          ...current,
                                          [app.appId]: {
                                            ...(current[app.appId] ??
                                              aiSecurityDefaultExternalAppActions(
                                                dataProtection?.mask_eligible_blockers ??
                                                  [],
                                              )),
                                            [blocker]: event.target
                                              .value as AiSecurityExternalAppAction,
                                          },
                                        }))
                                      }
                                      value={action}
                                    >
                                      {AI_SECURITY_EXTERNAL_APP_ACTIONS.map(
                                        (itemAction) => (
                                          <option
                                            key={itemAction}
                                            value={itemAction}
                                          >
                                            {t(
                                              `admin.console.aiSecurity.externalCapabilities.actions.${itemAction}`,
                                            )}
                                          </option>
                                        ),
                                      )}
                                    </select>
                                  </BodyCell>
                                );
                              },
                            )}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <EmptyPanel
                  description={t(
                    'admin.console.aiSecurity.data.externalApps.emptyDescription',
                  )}
                  title={t(
                    'admin.console.aiSecurity.data.externalApps.emptyTitle',
                  )}
                />
              )}
            </div>
            <details className="rounded-md border border-app-border bg-app-surface">
              <summary
                className="app-text-body-sm cursor-pointer px-3 py-2 font-medium text-app-ink"
                title={t('admin.console.aiSecurity.data.mandatoryHelp')}
              >
                {t('admin.console.aiSecurity.data.mandatoryBlockers')} ·{' '}
                {dataProtection?.mandatory_blockers.length ?? 0}
              </summary>
              <div className="space-y-2 border-t border-app-border p-3">
                <p className="app-text-body-sm text-app-ink/65">
                  {t('admin.console.aiSecurity.data.mandatoryDescription')}
                </p>
                <div className="overflow-x-auto rounded-md border border-app-border">
                  <table className="w-full min-w-[760px] table-fixed border-collapse">
                    <thead>
                      <tr className="bg-app-surface-sidebar">
                        <HeadCell className="w-[22%]" dense>
                          {t(
                            'admin.console.aiSecurity.data.blockerColumns.item',
                          )}
                        </HeadCell>
                        <HeadCell className="w-[22%]" dense>
                          {t(
                            'admin.console.aiSecurity.data.blockerColumns.defaultAction',
                          )}
                        </HeadCell>
                        <HeadCell className="w-[56%]" dense>
                          {t(
                            'admin.console.aiSecurity.data.blockerColumns.what',
                          )}
                        </HeadCell>
                      </tr>
                    </thead>
                    <tbody>
                      {(dataProtection?.mandatory_blockers ?? []).map(
                        (item) => {
                          const blocker =
                            item as AiSecurityExternalTransferBlocker;
                          const isHardBlocker =
                            dataProtection?.hard_blockers.includes(blocker) ??
                            false;
                          const isMaskEligible =
                            dataProtection?.mask_eligible_blockers.includes(
                              blocker,
                            ) ?? false;
                          const action = aiSecurityDataProtectionAction(
                            dataBlockerActions,
                            blocker,
                          );
                          return (
                            <tr key={item}>
                              <BodyCell dense>
                                <div className="flex flex-col gap-1">
                                  <div className="flex items-center gap-2">
                                    <ShieldCheck
                                      className="shrink-0 text-app-success-text"
                                      size={15}
                                    />
                                    <span className="font-medium">
                                      {t(
                                        `admin.console.aiSecurity.blockers.${item}`,
                                      )}
                                    </span>
                                  </div>
                                  <Badge
                                    tone={isHardBlocker ? 'amber' : 'green'}
                                  >
                                    {t(
                                      isHardBlocker
                                        ? 'admin.console.aiSecurity.data.hardNeverBypass'
                                        : 'admin.console.aiSecurity.data.exceptionEligible',
                                    )}
                                  </Badge>
                                </div>
                              </BodyCell>
                              <BodyCell dense>
                                {isMaskEligible ? (
                                  <select
                                    className="app-field-input-sm"
                                    onChange={(event) =>
                                      setDataBlockerActions((current) => ({
                                        ...current,
                                        [blocker]: event.target
                                          .value as AiSecurityDataProtectionAction,
                                      }))
                                    }
                                    value={action}
                                  >
                                    {AI_SECURITY_DATA_ACTIONS.map(
                                      (itemAction) => (
                                        <option
                                          key={itemAction}
                                          value={itemAction}
                                        >
                                          {t(
                                            `admin.console.aiSecurity.data.actions.${itemAction}`,
                                          )}
                                        </option>
                                      ),
                                    )}
                                  </select>
                                ) : (
                                  <Badge
                                    tone={isHardBlocker ? 'amber' : 'default'}
                                  >
                                    {t(
                                      isHardBlocker
                                        ? 'admin.console.aiSecurity.data.actions.neverBypass'
                                        : 'admin.console.aiSecurity.data.actions.fixedBlock',
                                    )}
                                  </Badge>
                                )}
                              </BodyCell>
                              <BodyCell dense>
                                <div>
                                  {t(
                                    `admin.console.aiSecurity.blockerDetails.${item}.description`,
                                  )}
                                </div>
                                <details className="mt-1">
                                  <summary className="app-text-caption cursor-pointer text-app-accent">
                                    {t(
                                      'admin.console.aiSecurity.data.blockerColumns.details',
                                    )}
                                  </summary>
                                  <div className="app-text-caption mt-1 space-y-1 text-app-ink/55">
                                    <div>
                                      {t(
                                        `admin.console.aiSecurity.blockerDetails.${item}.patterns`,
                                      )}
                                    </div>
                                    <div>
                                      {t(
                                        `admin.console.aiSecurity.blockerDetails.${item}.examples`,
                                      )}
                                    </div>
                                  </div>
                                </details>
                              </BodyCell>
                            </tr>
                          );
                        },
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </details>
          </div>
        </SurfaceCard>
      ) : null}

      {tab === 'rules' ? (
        <div
          className={
            ruleEditorOpen
              ? 'grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_420px] 2xl:grid-cols-[minmax(0,1.15fr)_460px]'
              : 'space-y-3'
          }
        >
          <SurfaceCard
            description={t('admin.console.aiSecurity.rules.description')}
            title={t('admin.console.aiSecurity.rules.title')}
            actions={
              <Button onClick={openNewRuleEditor} variant="primary">
                <Plus size={15} />
                {t('admin.console.aiSecurity.rules.createTitle')}
              </Button>
            }
          >
            <div className="space-y-3">
              <label className="flex min-h-9 items-center gap-2 rounded-md border border-app-border bg-app-bg px-3">
                <Search className="shrink-0 text-app-ink/40" size={15} />
                <input
                  aria-label={t('admin.console.aiSecurity.rules.search')}
                  className="app-text-body-sm min-w-0 flex-1 bg-transparent py-2 text-app-ink outline-none"
                  onChange={(event) => setRuleQuery(event.target.value)}
                  placeholder={t('admin.console.aiSecurity.rules.search')}
                  value={ruleQuery}
                />
                <span className="app-text-caption shrink-0 text-app-ink/45">
                  {filteredRules.length}/{rules.length}
                </span>
              </label>
              <details className="rounded-md border border-app-border bg-app-surface">
                <summary className="app-text-body-sm cursor-pointer px-3 py-2 font-medium text-app-ink">
                  {t('admin.console.aiSecurity.rules.guidanceTitle')}
                </summary>
                <div className="grid gap-2 border-t border-app-border p-3 lg:grid-cols-3">
                  <AiSecurityGuidance
                    description={t(
                      'admin.console.aiSecurity.rules.guidance.scopePriorityDescription',
                    )}
                    title={t(
                      'admin.console.aiSecurity.rules.guidance.scopePriorityTitle',
                    )}
                  />
                  <AiSecurityGuidance
                    description={t(
                      'admin.console.aiSecurity.rules.guidance.effectDescription',
                    )}
                    title={t(
                      'admin.console.aiSecurity.rules.guidance.effectTitle',
                    )}
                  />
                  <AiSecurityGuidance
                    description={t(
                      'admin.console.aiSecurity.rules.guidance.noTeamDescription',
                    )}
                    title={t(
                      'admin.console.aiSecurity.rules.guidance.noTeamTitle',
                    )}
                  />
                </div>
              </details>
              <div className="overflow-hidden rounded-md border border-app-border">
                <div className="overflow-x-auto">
                  <table
                    className={`w-full ${
                      rules.length === 0 ? 'min-w-full' : 'min-w-[820px]'
                    } table-fixed border-collapse`}
                  >
                    <thead>
                      <tr className="bg-app-surface-sidebar">
                        <HeadCell className="w-[22%]" dense>
                          {t('admin.console.aiSecurity.rules.columns.name')}
                        </HeadCell>
                        <HeadCell className="w-[15%]" dense>
                          {t('admin.console.aiSecurity.rules.columns.effect')}
                        </HeadCell>
                        <HeadCell className="w-[23%]" dense>
                          {t('admin.console.aiSecurity.rules.columns.scope')}
                        </HeadCell>
                        <HeadCell className="w-[20%]" dense>
                          {t('admin.console.aiSecurity.rules.columns.target')}
                        </HeadCell>
                        <HeadCell className="w-[10%] whitespace-nowrap" dense>
                          {t('admin.console.aiSecurity.rules.columns.terms')}
                        </HeadCell>
                        <HeadCell
                          className="w-[10%] whitespace-nowrap text-right"
                          dense
                        >
                          {t('admin.console.batches.columns.actions')}
                        </HeadCell>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredRules.length === 0 ? (
                        <EmptyRow
                          colSpan={6}
                          description={t(
                            'admin.console.aiSecurity.rules.emptyDescription',
                          )}
                          title={t('admin.console.aiSecurity.rules.emptyTitle')}
                        />
                      ) : (
                        filteredRules.map((rule) => (
                          <tr key={rule.id}>
                            <BodyCell dense>
                              <div className="min-w-0">
                                <div className="truncate font-medium">
                                  {rule.name}
                                </div>
                                <div className="truncate app-text-caption text-app-ink/55">
                                  {rule.enabled
                                    ? t(
                                        'admin.console.aiSecurity.rules.enabled',
                                      )
                                    : t(
                                        'admin.console.aiSecurity.rules.disabled',
                                      )}
                                </div>
                              </div>
                            </BodyCell>
                            <BodyCell dense>
                              <Badge tone={aiSecurityBadgeTone(rule.effect)}>
                                {t(
                                  `admin.console.aiSecurity.effects.${rule.effect}`,
                                )}
                              </Badge>
                            </BodyCell>
                            <BodyCell dense>
                              <span className="block truncate">
                                {aiSecuritySubjectSummary(t, rule)}
                              </span>
                            </BodyCell>
                            <BodyCell dense>
                              <span className="block truncate">
                                {aiSecurityRequestSummary(t, rule)}
                              </span>
                            </BodyCell>
                            <BodyCell dense>
                              {rule.custom_block_terms.length}
                            </BodyCell>
                            <BodyCell className="text-right" dense>
                              <div className="flex justify-end gap-1">
                                <Button
                                  onClick={() => {
                                    setRuleEditorOpen(true);
                                    setEditingRuleId(rule.id);
                                    setRuleDraft(
                                      aiSecurityRuleDraftFromRule(rule),
                                    );
                                    setRuleSelectedUser(
                                      aiSecuritySelectedUserFromRule(rule),
                                    );
                                    setRuleTermsText(
                                      aiSecurityTermsText(
                                        rule.custom_block_terms,
                                      ),
                                    );
                                  }}
                                  size="dense"
                                  variant="secondary"
                                >
                                  {t('common:actions.edit')}
                                </Button>
                                <Button
                                  disabled={saving}
                                  onClick={() => {
                                    if (
                                      window.confirm(
                                        t(
                                          'admin.console.aiSecurity.rules.deleteConfirm',
                                          { name: rule.name },
                                        ),
                                      )
                                    ) {
                                      void deleteRule(rule.id);
                                    }
                                  }}
                                  size="icon"
                                  variant="secondary"
                                >
                                  <Trash2 size={14} />
                                </Button>
                              </div>
                            </BodyCell>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </SurfaceCard>

          {ruleEditorOpen ? (
            <div className="xl:sticky xl:top-4">
              <SurfaceCard
                description={t(
                  'admin.console.aiSecurity.rules.formDescription',
                )}
                title={
                  editingRuleId
                    ? t('admin.console.aiSecurity.rules.editTitle')
                    : t('admin.console.aiSecurity.rules.createTitle')
                }
              >
                <form className="space-y-4" onSubmit={saveRule}>
                  <label className="space-y-1">
                    <AiSecurityFieldLabel
                      help={t('admin.console.aiSecurity.rules.help.name')}
                      label={t('admin.console.aiSecurity.rules.fields.name')}
                    />
                    <input
                      className={fieldClassName}
                      onChange={(event) =>
                        setRuleDraft((current) => ({
                          ...current,
                          name: event.target.value,
                        }))
                      }
                      required
                      value={ruleDraft.name}
                    />
                  </label>
                  <div className="grid gap-2 sm:grid-cols-2">
                    <label className="space-y-1">
                      <AiSecurityFieldLabel
                        help={t('admin.console.aiSecurity.rules.help.effect')}
                        label={t(
                          'admin.console.aiSecurity.rules.fields.effect',
                        )}
                      />
                      <select
                        className="app-field-input"
                        onChange={(event) =>
                          setRuleDraft((current) => ({
                            ...current,
                            effect: event.target
                              .value as AiSecurityPolicyEffect,
                          }))
                        }
                        value={ruleDraft.effect}
                      >
                        {AI_SECURITY_EFFECTS.map((effect) => (
                          <option key={effect} value={effect}>
                            {t(
                              `admin.console.aiSecurity.effectOptions.${effect}`,
                            )}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="flex h-10 items-center gap-2 self-end rounded-md border border-app-border px-3">
                      <input
                        checked={ruleDraft.enabled}
                        onChange={(event) =>
                          setRuleDraft((current) => ({
                            ...current,
                            enabled: event.target.checked,
                          }))
                        }
                        type="checkbox"
                      />
                      <span className="app-text-body-sm text-app-ink">
                        {t('admin.console.aiSecurity.rules.fields.enabled')}
                      </span>
                    </label>
                  </div>
                  <label className="space-y-1">
                    <AiSecurityFieldLabel
                      help={t(
                        'admin.console.aiSecurity.rules.help.description',
                      )}
                      label={t(
                        'admin.console.aiSecurity.rules.fields.description',
                      )}
                    />
                    <input
                      className={fieldClassName}
                      onChange={(event) =>
                        setRuleDraft((current) => ({
                          ...current,
                          description: event.target.value,
                        }))
                      }
                      value={ruleDraft.description}
                    />
                  </label>
                  <AiSecurityFormSection
                    description={t(
                      'admin.console.aiSecurity.rules.sections.subjectDescription',
                    )}
                    title={t('admin.console.aiSecurity.rules.sections.subject')}
                  >
                    <div className="grid gap-3 sm:grid-cols-2">
                      <AiSecurityUserPicker
                        help={t('admin.console.aiSecurity.rules.help.user')}
                        label={t('admin.console.aiSecurity.rules.fields.user')}
                        onChange={(userId, selectedUser) => {
                          setRuleDraft((current) => ({
                            ...current,
                            user_id: userId,
                          }));
                          setRuleSelectedUser(selectedUser);
                        }}
                        selectedUser={ruleSelectedUser}
                        token={token}
                        value={ruleDraft.user_id ?? null}
                      />
                      <AiSecurityOrgUnitPicker
                        allLabel={t(
                          'admin.console.aiSecurity.rules.allOrgUnits',
                        )}
                        clearLabel={t(
                          'admin.console.aiSecurity.rules.clearOrgUnit',
                        )}
                        help={t('admin.console.aiSecurity.rules.help.orgUnit')}
                        label={t(
                          'admin.console.aiSecurity.rules.fields.orgUnit',
                        )}
                        noResultsLabel={t(
                          'admin.console.aiSecurity.rules.noOrgResults',
                        )}
                        onChange={(orgUnitId) =>
                          setRuleDraft((current) => ({
                            ...current,
                            org_unit_id: orgUnitId,
                          }))
                        }
                        orgUnits={orgUnits}
                        searchPlaceholder={t(
                          'admin.console.aiSecurity.rules.orgSearchPlaceholder',
                        )}
                        value={ruleDraft.org_unit_id ?? null}
                      />
                      <AiSecurityWorkspacePicker
                        allLabel={t(
                          'admin.console.aiSecurity.rules.allWorkspaces',
                        )}
                        clearLabel={t(
                          'admin.console.aiSecurity.rules.clearWorkspace',
                        )}
                        help={t(
                          'admin.console.aiSecurity.rules.help.workspace',
                        )}
                        label={t(
                          'admin.console.aiSecurity.rules.fields.workspace',
                        )}
                        noResultsLabel={t(
                          'admin.console.aiSecurity.rules.noWorkspaceResults',
                        )}
                        onChange={(workspaceId) =>
                          setRuleDraft((current) => ({
                            ...current,
                            workspace_id: workspaceId,
                          }))
                        }
                        searchPlaceholder={t(
                          'admin.console.aiSecurity.rules.workspaceSearchPlaceholder',
                        )}
                        value={ruleDraft.workspace_id ?? null}
                        workspaces={workspaces}
                      />
                    </div>
                  </AiSecurityFormSection>

                  <AiSecurityFormSection
                    description={t(
                      'admin.console.aiSecurity.rules.sections.requestDescription',
                    )}
                    title={t('admin.console.aiSecurity.rules.sections.request')}
                  >
                    <div className="grid gap-3 sm:grid-cols-2">
                      <AiSecurityAppPicker
                        allLabel={t('admin.console.aiSecurity.rules.allApps')}
                        clearLabel={t(
                          'admin.console.aiSecurity.rules.clearApp',
                        )}
                        help={t('admin.console.aiSecurity.rules.help.appId')}
                        label={t('admin.console.aiSecurity.rules.fields.appId')}
                        noResultsLabel={t(
                          'admin.console.aiSecurity.rules.noAppResults',
                        )}
                        onChange={(value) =>
                          setRuleDraft((current) => {
                            const taskKinds = aiSecurityTaskKindsFromScope(
                              current,
                            ).filter((taskKind) =>
                              aiSecurityTaskBelongsToApp(value, taskKind),
                            );
                            return {
                              ...current,
                              app_id: value,
                              task_kind:
                                taskKinds.length === 1 ? taskKinds[0] : null,
                              task_kinds: taskKinds,
                            };
                          })
                        }
                        options={aiSecurityAppOptions}
                        searchPlaceholder={t(
                          'admin.console.aiSecurity.rules.appSearchPlaceholder',
                        )}
                        value={ruleDraft.app_id ?? null}
                      />
                      <AiSecurityTaskKindPicker
                        allLabel={t('admin.console.aiSecurity.rules.allTasks')}
                        clearLabel={t(
                          'admin.console.aiSecurity.rules.clearTaskKind',
                        )}
                        help={t('admin.console.aiSecurity.rules.help.taskKind')}
                        label={t(
                          'admin.console.aiSecurity.rules.fields.taskKind',
                        )}
                        noResultsLabel={t(
                          'admin.console.aiSecurity.rules.noTaskResults',
                        )}
                        onChange={(taskKinds) =>
                          setRuleDraft((current) => ({
                            ...current,
                            task_kind:
                              taskKinds.length === 1 ? taskKinds[0] : null,
                            task_kinds: taskKinds,
                          }))
                        }
                        options={aiSecurityTaskOptionsForApp(
                          ruleDraft.app_id,
                          aiSecurityTaskKindsFromScope(ruleDraft),
                        )}
                        searchPlaceholder={t(
                          'admin.console.aiSecurity.rules.taskSearchPlaceholder',
                        )}
                        value={aiSecurityTaskKindsFromScope(ruleDraft)}
                      />
                      <AiSecurityConditionInput
                        help={t(
                          'admin.console.aiSecurity.rules.help.capability',
                        )}
                        label={t(
                          'admin.console.aiSecurity.rules.fields.capability',
                        )}
                        listId="ai-security-rule-capability-options"
                        onChange={(value) =>
                          setRuleDraft((current) => ({
                            ...current,
                            capability: value,
                          }))
                        }
                        options={aiSecurityCapabilityOptions}
                        placeholder={t(
                          'admin.console.aiSecurity.rules.placeholders.capability',
                        )}
                        value={ruleDraft.capability}
                      />
                      <AiSecurityConditionInput
                        help={t('admin.console.aiSecurity.rules.help.provider')}
                        label={t(
                          'admin.console.aiSecurity.rules.fields.provider',
                        )}
                        listId="ai-security-rule-provider-options"
                        onChange={(value) =>
                          setRuleDraft((current) => ({
                            ...current,
                            provider: value,
                          }))
                        }
                        options={aiSecurityProviderOptions}
                        placeholder={t(
                          'admin.console.aiSecurity.rules.placeholders.provider',
                        )}
                        value={ruleDraft.provider}
                      />
                    </div>
                  </AiSecurityFormSection>
                  <AiSecurityFormSection
                    description={t(
                      'admin.console.aiSecurity.rules.sections.termsDescription',
                    )}
                    title={t(
                      'admin.console.aiSecurity.rules.fields.customTerms',
                    )}
                  >
                    <AiSecurityTermsTagInput
                      emptyLabel={t(
                        'admin.console.aiSecurity.data.customTermsEmpty',
                      )}
                      onChange={setRuleTermsText}
                      placeholder={t(
                        'admin.console.aiSecurity.data.customTermsPlaceholder',
                      )}
                      removeLabel={t(
                        'admin.console.aiSecurity.data.customTermsRemove',
                      )}
                      summaryLabel={t(
                        'admin.console.aiSecurity.data.customTermsCount',
                        {
                          count: parseAiSecurityTerms(ruleTermsText).length,
                        },
                      )}
                      value={ruleTermsText}
                    />
                  </AiSecurityFormSection>
                  <div className="flex justify-end gap-2 border-t border-app-border pt-4">
                    <Button
                      onClick={resetRuleDraft}
                      type="button"
                      variant="secondary"
                    >
                      {t('common:actions.cancel')}
                    </Button>
                    <Button
                      disabled={saving || !ruleDraft.name.trim()}
                      type="submit"
                      variant="primary"
                    >
                      <Save size={16} />
                      {t('common:actions.save')}
                    </Button>
                  </div>
                </form>
              </SurfaceCard>
            </div>
          ) : null}
        </div>
      ) : null}

      {tab === 'exceptions' ? (
        <div
          className={
            exceptionEditorOpen
              ? 'grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_420px] 2xl:grid-cols-[minmax(0,1.15fr)_460px]'
              : 'space-y-3'
          }
        >
          <SurfaceCard
            description={t('admin.console.aiSecurity.exceptions.description')}
            title={t('admin.console.aiSecurity.exceptions.title')}
            actions={
              <Button onClick={openNewExceptionEditor} variant="primary">
                <Plus size={15} />
                {t('admin.console.aiSecurity.exceptions.createTitle')}
              </Button>
            }
          >
            <div className="space-y-3">
              <label className="flex min-h-9 items-center gap-2 rounded-md border border-app-border bg-app-bg px-3">
                <Search className="shrink-0 text-app-ink/40" size={15} />
                <input
                  aria-label={t('admin.console.aiSecurity.exceptions.search')}
                  className="app-text-body-sm min-w-0 flex-1 bg-transparent py-2 text-app-ink outline-none"
                  onChange={(event) => setExceptionQuery(event.target.value)}
                  placeholder={t('admin.console.aiSecurity.exceptions.search')}
                  value={exceptionQuery}
                />
                <span className="app-text-caption shrink-0 text-app-ink/45">
                  {filteredExceptions.length}/{exceptions.length}
                </span>
              </label>
              <details className="rounded-md border border-app-border bg-app-surface">
                <summary className="app-text-body-sm cursor-pointer px-3 py-2 font-medium text-app-ink">
                  {t('admin.console.aiSecurity.exceptions.guidanceTitle')}
                </summary>
                <div className="grid gap-2 border-t border-app-border p-3 lg:grid-cols-3">
                  <AiSecurityGuidance
                    description={t(
                      'admin.console.aiSecurity.exceptions.guidance.softDescription',
                    )}
                    title={t(
                      'admin.console.aiSecurity.exceptions.guidance.softTitle',
                    )}
                  />
                  <AiSecurityGuidance
                    description={t(
                      'admin.console.aiSecurity.exceptions.guidance.hardDescription',
                    )}
                    title={t(
                      'admin.console.aiSecurity.exceptions.guidance.hardTitle',
                    )}
                  />
                  <AiSecurityGuidance
                    description={t(
                      'admin.console.aiSecurity.exceptions.guidance.expiryDescription',
                    )}
                    title={t(
                      'admin.console.aiSecurity.exceptions.guidance.expiryTitle',
                    )}
                  />
                </div>
              </details>
              <div className="overflow-hidden rounded-md border border-app-border">
                <div className="overflow-x-auto">
                  <table
                    className={`w-full ${
                      exceptions.length === 0 ? 'min-w-full' : 'min-w-[860px]'
                    } table-fixed border-collapse`}
                  >
                    <thead>
                      <tr className="bg-app-surface-sidebar">
                        <HeadCell className="w-[21%]" dense>
                          {t(
                            'admin.console.aiSecurity.exceptions.columns.name',
                          )}
                        </HeadCell>
                        <HeadCell className="w-[22%]" dense>
                          {t(
                            'admin.console.aiSecurity.exceptions.columns.blockers',
                          )}
                        </HeadCell>
                        <HeadCell className="w-[22%]" dense>
                          {t(
                            'admin.console.aiSecurity.exceptions.columns.scope',
                          )}
                        </HeadCell>
                        <HeadCell className="w-[17%]" dense>
                          {t(
                            'admin.console.aiSecurity.exceptions.columns.target',
                          )}
                        </HeadCell>
                        <HeadCell className="w-[9%] whitespace-nowrap" dense>
                          {t(
                            'admin.console.aiSecurity.exceptions.columns.expires',
                          )}
                        </HeadCell>
                        <HeadCell
                          className="w-[8%] whitespace-nowrap text-right"
                          dense
                        >
                          {t('admin.console.batches.columns.actions')}
                        </HeadCell>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredExceptions.length === 0 ? (
                        <EmptyRow
                          colSpan={6}
                          description={t(
                            'admin.console.aiSecurity.exceptions.emptyDescription',
                          )}
                          title={t(
                            'admin.console.aiSecurity.exceptions.emptyTitle',
                          )}
                        />
                      ) : (
                        filteredExceptions.map((exception) => (
                          <tr key={exception.id}>
                            <BodyCell dense>
                              <div className="min-w-0">
                                <div className="truncate font-medium">
                                  {exception.name}
                                </div>
                                <div className="truncate app-text-caption text-app-ink/55">
                                  {exception.enabled
                                    ? t(
                                        'admin.console.aiSecurity.exceptions.enabled',
                                      )
                                    : t(
                                        'admin.console.aiSecurity.exceptions.disabled',
                                      )}
                                </div>
                              </div>
                            </BodyCell>
                            <BodyCell dense>
                              <div className="flex flex-wrap gap-1">
                                {exception.allowed_blocker_types.map(
                                  (blocker) => (
                                    <Badge key={blocker} tone="green">
                                      {t(
                                        `admin.console.aiSecurity.blockers.${blocker}`,
                                      )}
                                    </Badge>
                                  ),
                                )}
                              </div>
                            </BodyCell>
                            <BodyCell dense>
                              <span className="block truncate">
                                {aiSecuritySubjectSummary(t, exception)}
                              </span>
                            </BodyCell>
                            <BodyCell dense>
                              <span className="block truncate">
                                {aiSecurityRequestSummary(t, exception)}
                              </span>
                            </BodyCell>
                            <BodyCell dense>
                              <div className="flex flex-col items-start gap-1">
                                <Badge
                                  tone={
                                    aiSecurityExceptionExpiryState(
                                      exception.expires_at,
                                    ) === 'active'
                                      ? 'green'
                                      : 'amber'
                                  }
                                >
                                  {t(
                                    `admin.console.aiSecurity.exceptions.expiryStates.${aiSecurityExceptionExpiryState(
                                      exception.expires_at,
                                    )}`,
                                  )}
                                </Badge>
                                <span className="app-text-caption text-app-ink/55">
                                  {exception.expires_at
                                    ? formatDateTime(exception.expires_at, {
                                        dateStyle: 'short',
                                        locale,
                                        timeStyle: 'short',
                                        timeZone,
                                      })
                                    : t('common:empty.none')}
                                </span>
                              </div>
                            </BodyCell>
                            <BodyCell className="text-right" dense>
                              <div className="flex justify-end gap-1">
                                <Button
                                  onClick={() => {
                                    setExceptionEditorOpen(true);
                                    setEditingExceptionId(exception.id);
                                    setExceptionDraft(
                                      aiSecurityExceptionDraftFromException(
                                        exception,
                                      ),
                                    );
                                    setExceptionSelectedUser(
                                      aiSecuritySelectedUserFromException(
                                        exception,
                                      ),
                                    );
                                  }}
                                  size="dense"
                                  variant="secondary"
                                >
                                  {t('common:actions.edit')}
                                </Button>
                                <Button
                                  disabled={saving}
                                  onClick={() => {
                                    if (
                                      window.confirm(
                                        t(
                                          'admin.console.aiSecurity.exceptions.deleteConfirm',
                                          { name: exception.name },
                                        ),
                                      )
                                    ) {
                                      void deleteException(exception.id);
                                    }
                                  }}
                                  size="icon"
                                  variant="secondary"
                                >
                                  <Trash2 size={14} />
                                </Button>
                              </div>
                            </BodyCell>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </SurfaceCard>

          {exceptionEditorOpen ? (
            <div className="xl:sticky xl:top-4">
              <SurfaceCard
                description={t(
                  'admin.console.aiSecurity.exceptions.formDescription',
                )}
                title={
                  editingExceptionId
                    ? t('admin.console.aiSecurity.exceptions.editTitle')
                    : t('admin.console.aiSecurity.exceptions.createTitle')
                }
              >
                <form className="space-y-4" onSubmit={saveException}>
                  <label className="space-y-1">
                    <AiSecurityFieldLabel
                      help={t('admin.console.aiSecurity.exceptions.help.name')}
                      label={t(
                        'admin.console.aiSecurity.exceptions.fields.name',
                      )}
                    />
                    <input
                      className={fieldClassName}
                      onChange={(event) =>
                        setExceptionDraft((current) => ({
                          ...current,
                          name: event.target.value,
                        }))
                      }
                      required
                      value={exceptionDraft.name}
                    />
                  </label>
                  <div className="grid gap-2 sm:grid-cols-2">
                    <label className="space-y-1">
                      <AiSecurityFieldLabel
                        help={t(
                          'admin.console.aiSecurity.exceptions.help.expiresAt',
                        )}
                        label={t(
                          'admin.console.aiSecurity.exceptions.fields.expiresAt',
                        )}
                      />
                      <input
                        className={fieldClassName}
                        min={formatAiSecurityDateTimeLocal(new Date())}
                        onChange={(event) =>
                          setExceptionDraft((current) => ({
                            ...current,
                            expires_at: event.target.value,
                          }))
                        }
                        required
                        type="datetime-local"
                        value={exceptionDraft.expires_at}
                      />
                    </label>
                    <label className="flex h-10 items-center gap-2 self-end rounded-md border border-app-border px-3">
                      <input
                        checked={exceptionDraft.enabled}
                        onChange={(event) =>
                          setExceptionDraft((current) => ({
                            ...current,
                            enabled: event.target.checked,
                          }))
                        }
                        type="checkbox"
                      />
                      <span className="app-text-body-sm text-app-ink">
                        {t(
                          'admin.console.aiSecurity.exceptions.fields.enabled',
                        )}
                      </span>
                    </label>
                  </div>
                  <label className="space-y-1">
                    <AiSecurityFieldLabel
                      help={t(
                        'admin.console.aiSecurity.exceptions.help.description',
                      )}
                      label={t(
                        'admin.console.aiSecurity.exceptions.fields.description',
                      )}
                    />
                    <input
                      className={fieldClassName}
                      onChange={(event) =>
                        setExceptionDraft((current) => ({
                          ...current,
                          description: event.target.value,
                        }))
                      }
                      value={exceptionDraft.description}
                    />
                  </label>
                  <AiSecurityFormSection
                    description={t(
                      'admin.console.aiSecurity.exceptions.help.blockers',
                    )}
                    title={t(
                      'admin.console.aiSecurity.exceptions.fields.blockers',
                    )}
                  >
                    <div className="grid gap-2 sm:grid-cols-2">
                      {(
                        dataProtection?.exception_eligible_blockers ??
                        AI_SECURITY_EXCEPTION_BLOCKERS
                      ).map((blocker) => (
                        <label
                          className="flex items-start gap-2 rounded-md border border-app-border px-3 py-2"
                          key={blocker}
                        >
                          <input
                            checked={exceptionDraft.allowed_blocker_types.includes(
                              blocker,
                            )}
                            onChange={(event) =>
                              setExceptionDraft((current) => {
                                const next = event.target.checked
                                  ? [...current.allowed_blocker_types, blocker]
                                  : current.allowed_blocker_types.filter(
                                      (item) => item !== blocker,
                                    );
                                return {
                                  ...current,
                                  allowed_blocker_types: Array.from(
                                    new Set(next),
                                  ),
                                };
                              })
                            }
                            type="checkbox"
                          />
                          <span className="min-w-0">
                            <span className="block app-text-body-sm font-medium text-app-ink">
                              {t(
                                `admin.console.aiSecurity.blockers.${blocker}`,
                              )}
                            </span>
                            <span className="block app-text-caption text-app-ink/55">
                              {t(
                                `admin.console.aiSecurity.exceptionBlockerHelp.${blocker}`,
                              )}
                            </span>
                          </span>
                        </label>
                      ))}
                    </div>
                    <p className="app-text-caption text-app-warning-text">
                      {t('admin.console.aiSecurity.exceptions.hardBlockerNote')}
                    </p>
                  </AiSecurityFormSection>

                  <AiSecurityFormSection
                    description={t(
                      'admin.console.aiSecurity.exceptions.sections.subjectDescription',
                    )}
                    title={t('admin.console.aiSecurity.rules.sections.subject')}
                  >
                    <div className="grid gap-3 sm:grid-cols-2">
                      <AiSecurityUserPicker
                        help={t('admin.console.aiSecurity.rules.help.user')}
                        label={t('admin.console.aiSecurity.rules.fields.user')}
                        onChange={(userId, selectedUser) => {
                          setExceptionDraft((current) => ({
                            ...current,
                            user_id: userId,
                          }));
                          setExceptionSelectedUser(selectedUser);
                        }}
                        selectedUser={exceptionSelectedUser}
                        token={token}
                        value={exceptionDraft.user_id ?? null}
                      />
                      <AiSecurityOrgUnitPicker
                        allLabel={t(
                          'admin.console.aiSecurity.rules.allOrgUnits',
                        )}
                        clearLabel={t(
                          'admin.console.aiSecurity.rules.clearOrgUnit',
                        )}
                        help={t('admin.console.aiSecurity.rules.help.orgUnit')}
                        label={t(
                          'admin.console.aiSecurity.rules.fields.orgUnit',
                        )}
                        noResultsLabel={t(
                          'admin.console.aiSecurity.rules.noOrgResults',
                        )}
                        onChange={(orgUnitId) =>
                          setExceptionDraft((current) => ({
                            ...current,
                            org_unit_id: orgUnitId,
                          }))
                        }
                        orgUnits={orgUnits}
                        searchPlaceholder={t(
                          'admin.console.aiSecurity.rules.orgSearchPlaceholder',
                        )}
                        value={exceptionDraft.org_unit_id ?? null}
                      />
                      <AiSecurityWorkspacePicker
                        allLabel={t(
                          'admin.console.aiSecurity.rules.allWorkspaces',
                        )}
                        clearLabel={t(
                          'admin.console.aiSecurity.rules.clearWorkspace',
                        )}
                        help={t(
                          'admin.console.aiSecurity.rules.help.workspace',
                        )}
                        label={t(
                          'admin.console.aiSecurity.rules.fields.workspace',
                        )}
                        noResultsLabel={t(
                          'admin.console.aiSecurity.rules.noWorkspaceResults',
                        )}
                        onChange={(workspaceId) =>
                          setExceptionDraft((current) => ({
                            ...current,
                            workspace_id: workspaceId,
                          }))
                        }
                        searchPlaceholder={t(
                          'admin.console.aiSecurity.rules.workspaceSearchPlaceholder',
                        )}
                        value={exceptionDraft.workspace_id ?? null}
                        workspaces={workspaces}
                      />
                    </div>
                  </AiSecurityFormSection>

                  <AiSecurityFormSection
                    description={t(
                      'admin.console.aiSecurity.exceptions.sections.requestDescription',
                    )}
                    title={t('admin.console.aiSecurity.rules.sections.request')}
                  >
                    <div className="grid gap-3 sm:grid-cols-2">
                      <AiSecurityAppPicker
                        allLabel={t('admin.console.aiSecurity.rules.allApps')}
                        clearLabel={t(
                          'admin.console.aiSecurity.rules.clearApp',
                        )}
                        help={t('admin.console.aiSecurity.rules.help.appId')}
                        label={t('admin.console.aiSecurity.rules.fields.appId')}
                        noResultsLabel={t(
                          'admin.console.aiSecurity.rules.noAppResults',
                        )}
                        onChange={(value) =>
                          setExceptionDraft((current) => {
                            const taskKinds = aiSecurityTaskKindsFromScope(
                              current,
                            ).filter((taskKind) =>
                              aiSecurityTaskBelongsToApp(value, taskKind),
                            );
                            return {
                              ...current,
                              app_id: value,
                              task_kind:
                                taskKinds.length === 1 ? taskKinds[0] : null,
                              task_kinds: taskKinds,
                            };
                          })
                        }
                        options={aiSecurityAppOptions}
                        searchPlaceholder={t(
                          'admin.console.aiSecurity.rules.appSearchPlaceholder',
                        )}
                        value={exceptionDraft.app_id ?? null}
                      />
                      <AiSecurityTaskKindPicker
                        allLabel={t('admin.console.aiSecurity.rules.allTasks')}
                        clearLabel={t(
                          'admin.console.aiSecurity.rules.clearTaskKind',
                        )}
                        help={t('admin.console.aiSecurity.rules.help.taskKind')}
                        label={t(
                          'admin.console.aiSecurity.rules.fields.taskKind',
                        )}
                        noResultsLabel={t(
                          'admin.console.aiSecurity.rules.noTaskResults',
                        )}
                        onChange={(taskKinds) =>
                          setExceptionDraft((current) => ({
                            ...current,
                            task_kind:
                              taskKinds.length === 1 ? taskKinds[0] : null,
                            task_kinds: taskKinds,
                          }))
                        }
                        options={aiSecurityTaskOptionsForApp(
                          exceptionDraft.app_id,
                          aiSecurityTaskKindsFromScope(exceptionDraft),
                        )}
                        searchPlaceholder={t(
                          'admin.console.aiSecurity.rules.taskSearchPlaceholder',
                        )}
                        value={aiSecurityTaskKindsFromScope(exceptionDraft)}
                      />
                      <AiSecurityConditionInput
                        help={t(
                          'admin.console.aiSecurity.rules.help.capability',
                        )}
                        label={t(
                          'admin.console.aiSecurity.rules.fields.capability',
                        )}
                        listId="ai-security-exception-capability-options"
                        onChange={(value) =>
                          setExceptionDraft((current) => ({
                            ...current,
                            capability: value,
                          }))
                        }
                        options={aiSecurityCapabilityOptions}
                        placeholder={t(
                          'admin.console.aiSecurity.rules.placeholders.capability',
                        )}
                        value={exceptionDraft.capability}
                      />
                      <AiSecurityConditionInput
                        help={t('admin.console.aiSecurity.rules.help.provider')}
                        label={t(
                          'admin.console.aiSecurity.rules.fields.provider',
                        )}
                        listId="ai-security-exception-provider-options"
                        onChange={(value) =>
                          setExceptionDraft((current) => ({
                            ...current,
                            provider: value,
                          }))
                        }
                        options={aiSecurityProviderOptions}
                        placeholder={t(
                          'admin.console.aiSecurity.rules.placeholders.provider',
                        )}
                        value={exceptionDraft.provider}
                      />
                    </div>
                  </AiSecurityFormSection>

                  <AiSecurityFormSection
                    description={t(
                      'admin.console.aiSecurity.exceptions.help.reason',
                    )}
                    title={t(
                      'admin.console.aiSecurity.exceptions.fields.reason',
                    )}
                  >
                    <textarea
                      className={`${fieldClassName} min-h-24`}
                      onChange={(event) =>
                        setExceptionDraft((current) => ({
                          ...current,
                          reason: event.target.value,
                        }))
                      }
                      required
                      value={exceptionDraft.reason}
                    />
                  </AiSecurityFormSection>
                  <div className="flex justify-end gap-2 border-t border-app-border pt-4">
                    <Button
                      onClick={resetExceptionDraft}
                      type="button"
                      variant="secondary"
                    >
                      {t('common:actions.cancel')}
                    </Button>
                    <Button
                      disabled={
                        saving ||
                        !exceptionDraft.name.trim() ||
                        !exceptionDraft.reason.trim() ||
                        exceptionDraft.allowed_blocker_types.length === 0 ||
                        !exceptionDraft.expires_at
                      }
                      type="submit"
                      variant="primary"
                    >
                      <Save size={16} />
                      {t('common:actions.save')}
                    </Button>
                  </div>
                </form>
              </SurfaceCard>
            </div>
          ) : null}
        </div>
      ) : null}

      {tab === 'simulator' ? (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px]">
          <SurfaceCard
            description={t('admin.console.aiSecurity.simulator.description')}
            title={t('admin.console.aiSecurity.simulator.title')}
          >
            <form className="space-y-3" onSubmit={runSimulation}>
              {!aiSecurityEnforcementEnabled ? (
                <InlineNotice tone="warning">
                  {t('admin.console.aiSecurity.simulator.enforcementDisabled')}
                </InlineNotice>
              ) : null}
              <details className="rounded-md border border-app-border bg-app-surface">
                <summary className="app-text-body-sm cursor-pointer px-3 py-2 font-medium text-app-ink">
                  {t('admin.console.aiSecurity.simulator.guidanceTitle')}
                </summary>
                <div className="grid gap-2 border-t border-app-border p-3 lg:grid-cols-2">
                  <AiSecurityGuidance
                    description={t(
                      'admin.console.aiSecurity.simulator.guidance.sameResolverDescription',
                    )}
                    title={t(
                      'admin.console.aiSecurity.simulator.guidance.sameResolverTitle',
                    )}
                  />
                  <AiSecurityGuidance
                    description={t(
                      'admin.console.aiSecurity.simulator.guidance.noRawSaveDescription',
                    )}
                    title={t(
                      'admin.console.aiSecurity.simulator.guidance.noRawSaveTitle',
                    )}
                  />
                </div>
              </details>
              <div className="rounded-md border border-app-border p-3">
                <div className="mb-3">
                  <div className="app-text-control text-app-ink">
                    {t('admin.console.aiSecurity.simulator.sections.subject')}
                  </div>
                  <p className="app-text-body-sm mt-1 text-app-ink/60">
                    {t(
                      'admin.console.aiSecurity.simulator.sections.subjectDescription',
                    )}
                  </p>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <AiSecurityUserPicker
                    help={t('admin.console.aiSecurity.simulator.help.user')}
                    label={t(
                      'admin.console.aiSecurity.simulator.fields.actor_user_id',
                    )}
                    onChange={(userId, selectedUser) => {
                      setSimulationDraft((current) => ({
                        ...current,
                        actor_user_id: userId,
                      }));
                      setSimulationSelectedUser(selectedUser);
                    }}
                    selectedUser={simulationSelectedUser}
                    token={token}
                    value={simulationDraft.actor_user_id ?? null}
                  />
                  <AiSecurityOrgUnitPicker
                    allLabel={t('admin.console.aiSecurity.simulator.orgAny')}
                    clearLabel={t(
                      'admin.console.aiSecurity.simulator.clearOrgUnit',
                    )}
                    help={t('admin.console.aiSecurity.simulator.help.orgUnit')}
                    label={t(
                      'admin.console.aiSecurity.simulator.fields.org_unit_id',
                    )}
                    noResultsLabel={t(
                      'admin.console.aiSecurity.rules.noOrgResults',
                    )}
                    onChange={(orgUnitId) =>
                      setSimulationDraft((current) => ({
                        ...current,
                        org_unit_id: orgUnitId,
                      }))
                    }
                    orgUnits={orgUnits}
                    searchPlaceholder={t(
                      'admin.console.aiSecurity.rules.orgSearchPlaceholder',
                    )}
                    value={simulationDraft.org_unit_id ?? null}
                  />
                  <AiSecurityWorkspacePicker
                    allLabel={t(
                      'admin.console.aiSecurity.simulator.workspaceAny',
                    )}
                    clearLabel={t(
                      'admin.console.aiSecurity.rules.clearWorkspace',
                    )}
                    help={t(
                      'admin.console.aiSecurity.simulator.help.workspace',
                    )}
                    label={t(
                      'admin.console.aiSecurity.simulator.fields.workspace_id',
                    )}
                    noResultsLabel={t(
                      'admin.console.aiSecurity.rules.noWorkspaceResults',
                    )}
                    onChange={(workspaceId) =>
                      setSimulationDraft((current) => ({
                        ...current,
                        workspace_id: workspaceId,
                      }))
                    }
                    searchPlaceholder={t(
                      'admin.console.aiSecurity.rules.workspaceSearchPlaceholder',
                    )}
                    value={simulationDraft.workspace_id ?? null}
                    workspaces={workspaces}
                  />
                </div>
              </div>

              <div className="rounded-md border border-app-border p-3">
                <div className="mb-3">
                  <div className="app-text-control text-app-ink">
                    {t('admin.console.aiSecurity.simulator.sections.request')}
                  </div>
                  <p className="app-text-body-sm mt-1 text-app-ink/60">
                    {t(
                      'admin.console.aiSecurity.simulator.sections.requestDescription',
                    )}
                  </p>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <AiSecurityAppPicker
                    allLabel={t('admin.console.aiSecurity.rules.allApps')}
                    clearLabel={t('admin.console.aiSecurity.rules.clearApp')}
                    help={t('admin.console.aiSecurity.simulator.help.app_id')}
                    label={t(
                      'admin.console.aiSecurity.simulator.fields.app_id',
                    )}
                    noResultsLabel={t(
                      'admin.console.aiSecurity.rules.noAppResults',
                    )}
                    onChange={(value) =>
                      setSimulationDraft((current) => ({
                        ...current,
                        app_id: value,
                        task_kind: aiSecurityTaskBelongsToApp(
                          value,
                          current.task_kind,
                        )
                          ? current.task_kind
                          : null,
                      }))
                    }
                    options={aiSecurityAppOptions}
                    searchPlaceholder={t(
                      'admin.console.aiSecurity.rules.appSearchPlaceholder',
                    )}
                    value={simulationDraft.app_id ?? null}
                  />
                  {(
                    [
                      {
                        fieldName: 'task_kind',
                        options: aiSecurityTaskOptionsForApp(
                          simulationDraft.app_id,
                          simulationDraft.task_kind,
                        ),
                      },
                      {
                        fieldName: 'capability',
                        options: aiSecurityCapabilityOptions,
                      },
                      {
                        fieldName: 'provider',
                        options: aiSecurityProviderOptions,
                      },
                      {
                        fieldName: 'content_origin',
                        options: aiSecurityContentOriginOptions,
                      },
                    ] as const
                  ).map(({ fieldName, options }) => (
                    <AiSecurityConditionInput
                      help={t(
                        `admin.console.aiSecurity.simulator.help.${fieldName}`,
                      )}
                      key={fieldName}
                      label={t(
                        `admin.console.aiSecurity.simulator.fields.${fieldName}`,
                      )}
                      listId={`ai-security-simulator-${fieldName}-options`}
                      onChange={(value) =>
                        setSimulationDraft((current) => ({
                          ...current,
                          [fieldName]: value,
                        }))
                      }
                      options={options}
                      placeholder={t(
                        `admin.console.aiSecurity.simulator.placeholders.${fieldName}`,
                      )}
                      value={String(
                        simulationDraft[
                          fieldName as keyof AiSecuritySimulationPayload
                        ] ?? '',
                      )}
                    />
                  ))}
                  <label className="space-y-1">
                    <AiSecurityFieldLabel
                      help={t(
                        'admin.console.aiSecurity.simulator.help.source_kinds',
                      )}
                      label={t(
                        'admin.console.aiSecurity.simulator.fields.source_kinds',
                      )}
                    />
                    <input
                      className={fieldClassName}
                      onChange={(event) =>
                        setSimulationDraft((current) => ({
                          ...current,
                          source_kinds: parseAiSecurityTerms(
                            event.target.value,
                          ),
                        }))
                      }
                      placeholder={t(
                        'admin.console.aiSecurity.simulator.placeholders.source_kinds',
                      )}
                      value={simulationDraft.source_kinds.join(', ')}
                    />
                  </label>
                  <label className="space-y-1">
                    <AiSecurityFieldLabel
                      help={t(
                        'admin.console.aiSecurity.simulator.help.sensitivity_labels',
                      )}
                      label={t(
                        'admin.console.aiSecurity.simulator.fields.sensitivity_labels',
                      )}
                    />
                    <input
                      className={fieldClassName}
                      onChange={(event) =>
                        setSimulationDraft((current) => ({
                          ...current,
                          sensitivity_labels: parseAiSecurityTerms(
                            event.target.value,
                          ),
                        }))
                      }
                      placeholder={t(
                        'admin.console.aiSecurity.simulator.placeholders.sensitivity_labels',
                      )}
                      value={simulationDraft.sensitivity_labels.join(', ')}
                    />
                  </label>
                </div>
              </div>
              <label className="space-y-1">
                <AiSecurityFieldLabel
                  help={t('admin.console.aiSecurity.simulator.help.sample')}
                  label={t('admin.console.aiSecurity.simulator.sampleLabel')}
                />
                <textarea
                  className={`${fieldClassName} min-h-40`}
                  onChange={(event) =>
                    setSimulationDraft((current) => ({
                      ...current,
                      sample_text: event.target.value,
                    }))
                  }
                  placeholder={t(
                    'admin.console.aiSecurity.simulator.samplePlaceholder',
                  )}
                  value={simulationDraft.sample_text ?? ''}
                />
              </label>
              <div className="flex justify-end">
                <Button
                  disabled={saving}
                  onClick={() => void executeSimulation()}
                  type="button"
                  variant="primary"
                >
                  <Play size={16} />
                  {t('admin.console.aiSecurity.simulator.run')}
                </Button>
              </div>
            </form>
          </SurfaceCard>
          <SurfaceCard
            description={t(
              'admin.console.aiSecurity.simulator.resultDescription',
            )}
            title={t('admin.console.aiSecurity.simulator.resultTitle')}
          >
            {simulation ? (
              <div className="space-y-3">
                <div className="flex flex-wrap gap-2">
                  <Badge tone={aiSecurityBadgeTone(simulation.effect)}>
                    {t(`admin.console.aiSecurity.effects.${simulation.effect}`)}
                  </Badge>
                  <Badge tone={aiSecurityBadgeTone(simulation.route_action)}>
                    {t(
                      `admin.console.aiSecurity.simulator.actions.${simulation.route_action}`,
                    )}
                  </Badge>
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  <AiSecurityMetric
                    label={t('admin.console.aiSecurity.simulator.reason')}
                    detail={simulation.reason_code}
                    value={t(
                      `admin.console.aiSecurity.simulator.reasons.${simulation.reason_code}`,
                      { defaultValue: simulation.reason_code },
                    )}
                  />
                  <AiSecurityMetric
                    label={t('admin.console.aiSecurity.simulator.customHits')}
                    value={simulation.custom_block_term_count}
                  />
                  <AiSecurityMetric
                    label={t('admin.console.aiSecurity.simulator.piiHits')}
                    value={simulation.pii_hits.length}
                  />
                  <AiSecurityMetric
                    label={t(
                      'admin.console.aiSecurity.simulator.blockedEntities',
                    )}
                    value={simulation.blocked_entity_types.length}
                  />
                  <AiSecurityMetric
                    label={t(
                      'admin.console.aiSecurity.simulator.externalBlockers',
                    )}
                    value={simulation.external_transfer_blocker_types.length}
                  />
                  <AiSecurityMetric
                    label={t('admin.console.aiSecurity.simulator.hardBlockers')}
                    value={simulation.hard_blocker_types.length}
                  />
                  <AiSecurityMetric
                    detail={simulation.masked_entity_types.join(', ')}
                    label={t('admin.console.aiSecurity.simulator.maskApplied')}
                    value={t(
                      simulation.mask_applied
                        ? 'admin.console.aiSecurity.simulator.boolean.yes'
                        : 'admin.console.aiSecurity.simulator.boolean.no',
                    )}
                  />
                  <AiSecurityMetric
                    label={t(
                      'admin.console.aiSecurity.simulator.privacyFilterStatus',
                    )}
                    value={
                      simulation.privacy_filter_status ?? t('common:empty.none')
                    }
                  />
                </div>
                {simulation.masked_text_preview ? (
                  <div className="space-y-1 rounded-md border border-app-border bg-app-surface-sidebar p-3">
                    <div className="app-text-control text-app-ink">
                      {t(
                        'admin.console.aiSecurity.simulator.maskedTextPreview',
                      )}
                    </div>
                    <pre className="app-text-body-sm whitespace-pre-wrap break-words text-app-ink/75">
                      {simulation.masked_text_preview}
                    </pre>
                  </div>
                ) : null}
                {simulation.external_transfer_exception_allowed ? (
                  <div className="app-text-body-sm rounded-md border border-app-success-border bg-app-success-bg p-3 text-app-success-text">
                    {t('admin.console.aiSecurity.simulator.exceptionApplied', {
                      name:
                        simulation.external_transfer_exception_name ??
                        simulation.external_transfer_exception_id ??
                        t('common:empty.none'),
                    })}
                  </div>
                ) : null}
                {simulation.hard_blocker_types.length > 0 ? (
                  <div className="app-text-body-sm rounded-md border border-app-warning-border bg-app-warning-bg p-3 text-app-warning-text">
                    {t('admin.console.aiSecurity.simulator.hardBlockerWarning')}
                  </div>
                ) : null}
                <div className="app-text-body-sm rounded-md border border-app-border bg-app-surface-sidebar p-3 text-app-ink">
                  {simulation.rule_name ??
                    t('admin.console.aiSecurity.simulator.noRule')}
                </div>
              </div>
            ) : (
              <EmptyPanel
                description={t(
                  'admin.console.aiSecurity.simulator.emptyDescription',
                )}
                title={t('admin.console.aiSecurity.simulator.emptyTitle')}
              />
            )}
          </SurfaceCard>
        </div>
      ) : null}

      <AiSecurityDetectedValueGroupsDialog
        dateRangeLabel={monitoringDateRangeLabel}
        error={detectedValueGroupError}
        items={detectedValueGroups}
        loading={detectedValueGroupLoading}
        locale={locale}
        mode={detectedValueGroupMode ?? 'stored'}
        offset={detectedValueGroupOffset}
        onApplyQuery={applyDetectedValueGroupSearch}
        onNext={() =>
          setDetectedValueGroupOffset(
            (current) => current + AI_SECURITY_DETECTED_VALUE_PAGE_SIZE,
          )
        }
        onOpenChange={(open) => {
          if (!open) {
            closeDetectedValueGroupsDialog();
          }
        }}
        onPrevious={() =>
          setDetectedValueGroupOffset((current) =>
            Math.max(0, current - AI_SECURITY_DETECTED_VALUE_PAGE_SIZE),
          )
        }
        onQueryChange={setDetectedValueGroupQuery}
        onSelect={openDetectedValueDetailsDialog}
        open={detectedValueGroupMode !== null}
        query={detectedValueGroupQuery}
        t={t}
        timeZone={timeZone}
        total={detectedValueGroupTotal}
      />
      <AiSecurityDetectedValueDetailsDialog
        dateRangeLabel={monitoringDateRangeLabel}
        error={detectedValueDetailError}
        group={detectedValueDetailGroup}
        items={detectedValueDetails}
        loading={detectedValueDetailLoading}
        locale={locale}
        offset={detectedValueDetailOffset}
        onApplyQuery={applyDetectedValueDetailSearch}
        onNext={() =>
          setDetectedValueDetailOffset(
            (current) => current + AI_SECURITY_DETECTED_VALUE_PAGE_SIZE,
          )
        }
        onOpenChange={(open) => {
          if (!open) {
            closeDetectedValueDetailsDialog();
          }
        }}
        onPrevious={() =>
          setDetectedValueDetailOffset((current) =>
            Math.max(0, current - AI_SECURITY_DETECTED_VALUE_PAGE_SIZE),
          )
        }
        onQueryChange={setDetectedValueDetailQuery}
        open={detectedValueDetailGroup !== null}
        query={detectedValueDetailQuery}
        t={t}
        total={detectedValueDetailTotal}
      />
    </div>
  );
}
