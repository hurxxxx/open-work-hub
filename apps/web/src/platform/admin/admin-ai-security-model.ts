import type {
  AiSecurityDataProtectionAction,
  AiSecurityExternalAppAction,
  AiSecurityExternalTransferBlocker,
  AiSecurityExternalTransferException,
  AiSecurityExternalTransferExceptionPayload,
  AiSecurityPolicyEffect,
  AiSecurityPolicyRule,
  AiSecurityRulePayload,
  AiSecuritySimulationResult,
} from './admin-api';

export const AI_SECURITY_DETECTED_VALUE_PAGE_SIZE = 20;
export const AI_SECURITY_TABS = [
  'overview',
  'monitoring',
  'data',
  'rules',
  'exceptions',
  'simulator',
] as const;
export type AiSecurityTab = (typeof AI_SECURITY_TABS)[number];

export function resolveAiSecurityTab(value: string | null): AiSecurityTab {
  return AI_SECURITY_TABS.includes(value as AiSecurityTab)
    ? (value as AiSecurityTab)
    : 'overview';
}

export function withAiSecurityTab(
  searchParams: URLSearchParams,
  tab: AiSecurityTab,
): URLSearchParams {
  const next = new URLSearchParams(searchParams);
  if (tab === 'overview') {
    next.delete('tab');
  } else {
    next.set('tab', tab);
  }
  return next;
}
export const AI_SECURITY_EFFECTS: AiSecurityPolicyEffect[] = [
  'inherit',
  'block_external',
  'mask_and_send',
  'audit_only',
];
export const AI_SECURITY_EXCEPTION_BLOCKERS: AiSecurityExternalTransferBlocker[] =
  [
    'internal_context',
    'blocking_sensitivity_label',
    'company_sensitive_entity',
    'policy_block_external',
    'pii',
    'internal_url',
    'security_document',
  ];
export const AI_SECURITY_DATA_ACTIONS: AiSecurityDataProtectionAction[] = [
  'block',
  'mask_and_send',
];
export const AI_SECURITY_EXTERNAL_APP_ACTIONS: AiSecurityExternalAppAction[] = [
  'block',
  'mask_and_send',
];

export type AiSecurityConditionOption = {
  value: string;
  label?: string | null;
};

export type AiSecurityAppOption = AiSecurityConditionOption & {
  description?: string | null;
};

export type AiSecurityExternalAppActions = Partial<
  Record<
    string,
    Partial<
      Record<AiSecurityExternalTransferBlocker, AiSecurityExternalAppAction>
    >
  >
>;

export function aiSecurityConditionOptions(
  ...groups: Array<Array<AiSecurityConditionOption | string>>
): AiSecurityConditionOption[] {
  const byValue = new Map<string, AiSecurityConditionOption>();
  for (const group of groups) {
    for (const item of group) {
      const option = typeof item === 'string' ? { value: item } : { ...item };
      const value = option.value.trim();
      if (!value || byValue.has(value)) continue;
      byValue.set(value, { ...option, value });
    }
  }
  return Array.from(byValue.values()).sort((a, b) =>
    a.value.localeCompare(b.value),
  );
}

export function aiSecuritySearchText(value: string | null | undefined): string {
  return (value ?? '')
    .toLowerCase()
    .replace(/[·.\-_/\\\s]+/g, '')
    .trim();
}

export function aiSecurityMatchesSearch(
  query: string,
  ...values: Array<string | null | undefined>
): boolean {
  const normalizedQuery = aiSecuritySearchText(query);
  if (!normalizedQuery) return true;
  return values.some((value) =>
    aiSecuritySearchText(value).includes(normalizedQuery),
  );
}

export function aiSecurityTranslatedTaskDescription(
  t: (key: string, options?: Record<string, unknown>) => string,
  taskKind: string,
  fallback: string,
): string {
  return t(`admin.console.aiSecurity.taskDescriptions.${taskKind}`, {
    defaultValue: fallback || taskKind,
  });
}

export function aiSecuritySubjectSummary(
  t: (key: string, options?: Record<string, unknown>) => string,
  item: {
    user_id?: string | null;
    user_name?: string | null;
    workspace_name?: string | null;
  },
): string {
  const userName = item.user_name || item.user_id || '';
  return [
    userName
      ? t('admin.console.aiSecurity.rules.scopeParts.user', {
          name: userName,
        })
      : t('admin.console.aiSecurity.rules.scopeParts.allUsers'),
    item.workspace_name
      ? t('admin.console.aiSecurity.rules.scopeParts.workspace', {
          name: item.workspace_name,
        })
      : t('admin.console.aiSecurity.rules.scopeParts.allWorkspaces'),
  ].join(' / ');
}

export function aiSecurityRequestSummary(
  t: (key: string, options?: Record<string, unknown>) => string,
  item: {
    app_id?: string | null;
    task_kind?: string | null;
    task_kinds?: string[] | null;
    capability?: string | null;
    provider?: string | null;
  },
): string {
  const taskKinds =
    item.task_kinds && item.task_kinds.length > 0
      ? item.task_kinds
      : item.task_kind
        ? [item.task_kind]
        : [];
  return [
    item.app_id
      ? t('admin.console.aiSecurity.rules.requestParts.app', {
          name: item.app_id,
        })
      : t('admin.console.aiSecurity.rules.requestParts.allApps'),
    taskKinds.length > 0
      ? t('admin.console.aiSecurity.rules.requestParts.task', {
          name: taskKinds.join(', '),
        })
      : t('admin.console.aiSecurity.rules.requestParts.allTasks'),
    item.capability
      ? t('admin.console.aiSecurity.rules.requestParts.capability', {
          name: item.capability,
        })
      : t('admin.console.aiSecurity.rules.requestParts.allCapabilities'),
    item.provider
      ? t('admin.console.aiSecurity.rules.requestParts.provider', {
          name: item.provider,
        })
      : t('admin.console.aiSecurity.rules.requestParts.allProviders'),
  ].join(' / ');
}
export function emptyAiSecurityRuleDraft(): AiSecurityRulePayload {
  return {
    name: '',
    description: '',
    enabled: true,
    user_id: null,
    workspace_id: null,
    app_id: null,
    task_kind: null,
    task_kinds: [],
    capability: null,
    provider: null,
    effect: 'block_external',
    custom_block_terms: [],
  };
}

export function aiSecurityRuleDraftFromRule(
  rule: AiSecurityPolicyRule,
): AiSecurityRulePayload {
  return {
    name: rule.name,
    description: rule.description,
    enabled: rule.enabled,
    user_id: rule.user_id ?? null,
    workspace_id: rule.workspace_id ?? null,
    app_id: rule.app_id ?? null,
    task_kind: rule.task_kind ?? null,
    task_kinds: aiSecurityTaskKindsFromScope(rule),
    capability: rule.capability ?? null,
    provider: rule.provider ?? null,
    effect: rule.effect,
    custom_block_terms: rule.custom_block_terms,
  };
}

export function formatAiSecurityDateTimeLocal(date: Date): string {
  const offsetMs = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
}

export function defaultAiSecurityExceptionExpiresAt(): string {
  return formatAiSecurityDateTimeLocal(
    new Date(Date.now() + 30 * 24 * 60 * 60 * 1000),
  );
}

export function aiSecurityDateTimeLocalFromIso(value?: string | null): string {
  if (!value) return defaultAiSecurityExceptionExpiresAt();
  const date = new Date(value);
  if (Number.isNaN(date.getTime()))
    return defaultAiSecurityExceptionExpiresAt();
  return formatAiSecurityDateTimeLocal(date);
}

export function aiSecurityIsoFromDateTimeLocal(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return new Date().toISOString();
  return date.toISOString();
}

export function emptyAiSecurityExceptionDraft(): AiSecurityExternalTransferExceptionPayload {
  return {
    name: '',
    description: '',
    enabled: true,
    user_id: null,
    workspace_id: null,
    app_id: null,
    task_kind: null,
    task_kinds: [],
    capability: 'llm',
    provider: null,
    allowed_blocker_types: ['internal_context'],
    reason: '',
    expires_at: defaultAiSecurityExceptionExpiresAt(),
  };
}

export function aiSecurityExceptionDraftFromException(
  exception: AiSecurityExternalTransferException,
): AiSecurityExternalTransferExceptionPayload {
  return {
    name: exception.name,
    description: exception.description,
    enabled: exception.enabled,
    user_id: exception.user_id ?? null,
    workspace_id: exception.workspace_id ?? null,
    app_id: exception.app_id ?? null,
    task_kind: exception.task_kind ?? null,
    task_kinds: aiSecurityTaskKindsFromScope(exception),
    capability: exception.capability ?? null,
    provider: exception.provider ?? null,
    allowed_blocker_types: exception.allowed_blocker_types.filter((item) =>
      AI_SECURITY_EXCEPTION_BLOCKERS.includes(item),
    ),
    reason: exception.reason,
    expires_at: aiSecurityDateTimeLocalFromIso(exception.expires_at),
  };
}

export function aiSecurityNullable(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

export function aiSecurityPresent(
  value: string | null | undefined,
): value is string {
  return Boolean(value?.trim());
}

export function aiSecurityTaskKindsFromScope(item: {
  task_kind?: string | null;
  task_kinds?: string[] | null;
}): string[] {
  const values =
    item.task_kinds && item.task_kinds.length > 0
      ? item.task_kinds
      : item.task_kind
        ? [item.task_kind]
        : [];
  return Array.from(
    new Set(values.map((value) => value.trim()).filter(Boolean)),
  );
}

export function parseAiSecurityTerms(value: string): string[] {
  return Array.from(
    new Set(
      value
        .split(/[\r\n,]+/)
        .map((item) => item.trim())
        .filter((item) => item.length >= 2),
    ),
  );
}

export function aiSecurityTermsText(values: string[]): string {
  return values.join('\n');
}

export function aiSecurityDataProtectionAction(
  actions: Partial<
    Record<AiSecurityExternalTransferBlocker, AiSecurityDataProtectionAction>
  >,
  blocker: AiSecurityExternalTransferBlocker,
): AiSecurityDataProtectionAction {
  return actions[blocker] ?? 'block';
}

export function aiSecurityExternalAppAction(
  actions: Partial<
    Record<AiSecurityExternalTransferBlocker, AiSecurityExternalAppAction>
  >,
  blocker: AiSecurityExternalTransferBlocker,
): AiSecurityExternalAppAction {
  return actions[blocker] ?? 'block';
}

export function aiSecurityDefaultExternalAppActions(
  blockers: readonly AiSecurityExternalTransferBlocker[],
): Partial<
  Record<AiSecurityExternalTransferBlocker, AiSecurityExternalAppAction>
> {
  return Object.fromEntries(blockers.map((blocker) => [blocker, 'block']));
}

export function aiSecurityBadgeTone(
  effect: AiSecurityPolicyEffect | AiSecuritySimulationResult['route_action'],
): 'default' | 'green' | 'amber' | 'purple' {
  if (effect === 'block_external' || effect === 'blocked') return 'amber';
  if (
    effect === 'unchanged' ||
    effect === 'external_exception' ||
    effect === 'masked_external'
  )
    return 'green';
  if (effect === 'mask_and_send') return 'purple';
  if (effect === 'audit_only') return 'purple';
  return 'default';
}

export function aiSecurityExceptionExpiryState(
  expiresAt: string | null | undefined,
): 'expired' | 'expiringSoon' | 'active' {
  if (!expiresAt) return 'expired';
  const expiresAtMs = new Date(expiresAt).getTime();
  if (!Number.isFinite(expiresAtMs) || expiresAtMs <= Date.now()) {
    return 'expired';
  }
  return expiresAtMs - Date.now() <= 7 * 24 * 60 * 60 * 1000
    ? 'expiringSoon'
    : 'active';
}
