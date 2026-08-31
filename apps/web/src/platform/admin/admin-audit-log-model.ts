import type { AuditLogItem } from './admin-api';

type Translate = (key: string, options?: Record<string, unknown>) => string;

export interface AuditLogDetailItem {
  key: string;
  label: string;
  value: string;
}

export interface AuditLogDisplayModel {
  actionCode: string;
  actionLabel: string;
  actorLabel: string;
  detailItems: AuditLogDetailItem[];
  entityLabel: string;
  groupLabel: string;
  summary: string;
}

const ACTION_LABEL_KEYS: Record<string, string> = {
  'admin.ai_runtime.retention.scrub':
    'admin.console.audit.actions.adminAiRuntimeRetentionScrub',
  'admin.company_app_controls.update':
    'admin.console.audit.actions.adminCompanyAppControlsUpdate',
  'admin.team.create': 'admin.console.audit.actions.adminTeamCreate',
  'admin.team.delete': 'admin.console.audit.actions.adminTeamDelete',
  'admin.team.members.replace':
    'admin.console.audit.actions.adminTeamMembersReplace',
  'admin.team.update': 'admin.console.audit.actions.adminTeamUpdate',
  'admin.usage_exclusions.update':
    'admin.console.audit.actions.adminUsageExclusionsUpdate',
  'admin.usage_targets.update':
    'admin.console.audit.actions.adminUsageTargetsUpdate',
  'admin.ai_security.enforcement.update':
    'admin.console.audit.actions.adminAiSecurityEnforcementUpdate',
  'admin.ai_security.data_protection.update':
    'admin.console.audit.actions.adminAiSecurityDataProtectionUpdate',
  'admin.ai_security.external_transfer_exception.create':
    'admin.console.audit.actions.adminAiSecurityExternalTransferExceptionCreate',
  'admin.ai_security.external_transfer_exception.delete':
    'admin.console.audit.actions.adminAiSecurityExternalTransferExceptionDelete',
  'admin.ai_security.external_transfer_exception.update':
    'admin.console.audit.actions.adminAiSecurityExternalTransferExceptionUpdate',
  'admin.ai_security.rule.create':
    'admin.console.audit.actions.adminAiSecurityRuleCreate',
  'admin.ai_security.rule.delete':
    'admin.console.audit.actions.adminAiSecurityRuleDelete',
  'admin.ai_security.rule.update':
    'admin.console.audit.actions.adminAiSecurityRuleUpdate',
  'admin.ai_security.task_policies.update':
    'admin.console.audit.actions.adminAiSecurityTaskPoliciesUpdate',
  'admin.user.create': 'admin.console.audit.actions.adminUserCreate',
  'admin.user.delete': 'admin.console.audit.actions.adminUserDelete',
  'admin.user.reset-password':
    'admin.console.audit.actions.adminUserResetPassword',
  'admin.user.update': 'admin.console.audit.actions.adminUserUpdate',
  'admin.workspace.create': 'admin.console.audit.actions.adminWorkspaceCreate',
  'admin.workspace.delete': 'admin.console.audit.actions.adminWorkspaceDelete',
  'admin.workspace.update': 'admin.console.audit.actions.adminWorkspaceUpdate',
  'admin.workspace.bindings.replace':
    'admin.console.audit.actions.adminWorkspaceBindingsReplace',
  'admin.workspace.member.add':
    'admin.console.audit.actions.adminWorkspaceMemberAdd',
  'admin.workspace.member.remove':
    'admin.console.audit.actions.adminWorkspaceMemberRemove',
  'admin.workspace.member.role.update':
    'admin.console.audit.actions.adminWorkspaceMemberRoleUpdate',
  'admin.workspace_app_defaults.update':
    'admin.console.audit.actions.adminWorkspaceAppDefaultsUpdate',
  'admin.workspace_app_overrides.update':
    'admin.console.audit.actions.adminWorkspaceAppOverridesUpdate',
  ai_meeting_insight_created:
    'admin.console.audit.actions.aiMeetingInsightCreated',
  ai_external_call: 'admin.console.audit.actions.aiExternalCall',
  'auth.change-password': 'admin.console.audit.actions.authChangePassword',
  'auth.desktop-session-link.create':
    'admin.console.audit.actions.authDesktopSessionLinkCreate',
  'auth.desktop-session-link.exchange':
    'admin.console.audit.actions.authDesktopSessionLinkExchange',
  'auth.dev_admin_login': 'admin.console.audit.actions.authDevAdminLogin',
  'auth.dev_login': 'admin.console.audit.actions.authDevLogin',
  'auth.impersonate': 'admin.console.audit.actions.authImpersonate',
  'auth.login': 'admin.console.audit.actions.authLogin',
  'auth.logout': 'admin.console.audit.actions.authLogout',
  'auth.revoke-session': 'admin.console.audit.actions.authRevokeSession',
  'auth.setup': 'admin.console.audit.actions.authSetup',
  'auth.update-preferences':
    'admin.console.audit.actions.authUpdatePreferences',
  llm_call: 'admin.console.audit.actions.llmCall',
  llm_tool_approval_resolved:
    'admin.console.audit.actions.llmToolApprovalResolved',
  llm_tool_call: 'admin.console.audit.actions.llmToolCall',
  'mail.account.create': 'admin.console.audit.actions.mailAccountCreate',
  'mail.account.delete': 'admin.console.audit.actions.mailAccountDelete',
  'mail.account.update': 'admin.console.audit.actions.mailAccountUpdate',
  'mail.draft.send': 'admin.console.audit.actions.mailDraftSend',
};

const PAYLOAD_KEY_ORDER = [
  'status',
  'decision',
  'source',
  'tool_name',
  'task_kind',
  'app_id',
  'capability',
  'provider',
  'model',
  'policy',
  'chosen_pool',
  'policy_reason',
  'decision_reason',
  'ai_security_policy_effect',
  'ai_security_policy_reason',
  'blocked_entity_types',
  'removed_entity_types',
  'custom_block_term_count',
  'mask_applied',
  'masked_entity_types',
  'privacy_filter_status',
  'forced_local',
  'latency_ms',
  'usage',
  'error',
  'target_user_id',
  'user_id',
  'actor_user_id',
  'workspace_id',
  'principal_id',
  'approval_id',
  'call_id',
  'resource_ids',
  'added_user_ids',
  'removed_user_ids',
  'impersonation',
] as const;

const PAYLOAD_LABEL_KEYS: Record<string, string> = {
  actor_user_id: 'admin.console.audit.payloadLabels.actorUser',
  added_user_ids: 'admin.console.audit.payloadLabels.addedUsers',
  ai_security_policy_effect:
    'admin.console.audit.payloadLabels.aiSecurityPolicyEffect',
  ai_security_policy_reason:
    'admin.console.audit.payloadLabels.aiSecurityPolicyReason',
  approval_id: 'admin.console.audit.payloadLabels.approval',
  app_id: 'admin.console.audit.payloadLabels.app',
  blocked_entity_types: 'admin.console.audit.payloadLabels.blockedEntities',
  call_id: 'admin.console.audit.payloadLabels.call',
  capability: 'admin.console.audit.payloadLabels.capability',
  chosen_pool: 'admin.console.audit.payloadLabels.pool',
  custom_block_term_count:
    'admin.console.audit.payloadLabels.customBlockTermCount',
  decision: 'admin.console.audit.payloadLabels.decision',
  decision_reason: 'admin.console.audit.payloadLabels.reason',
  error: 'admin.console.audit.payloadLabels.error',
  forced_local: 'admin.console.audit.payloadLabels.forcedLocal',
  impersonation: 'admin.console.audit.payloadLabels.impersonation',
  latency_ms: 'admin.console.audit.payloadLabels.latency',
  mask_applied: 'admin.console.audit.payloadLabels.maskApplied',
  masked_entity_types: 'admin.console.audit.payloadLabels.maskedEntities',
  model: 'admin.console.audit.payloadLabels.model',
  policy: 'admin.console.audit.payloadLabels.policy',
  policy_reason: 'admin.console.audit.payloadLabels.policyReason',
  principal_id: 'admin.console.audit.payloadLabels.principal',
  privacy_filter_status: 'admin.console.audit.payloadLabels.privacyFilter',
  provider: 'admin.console.audit.payloadLabels.provider',
  removed_entity_types: 'admin.console.audit.payloadLabels.removedEntities',
  removed_user_ids: 'admin.console.audit.payloadLabels.removedUsers',
  resource_ids: 'admin.console.audit.payloadLabels.resources',
  source: 'admin.console.audit.payloadLabels.source',
  status: 'admin.console.audit.payloadLabels.status',
  target_user_id: 'admin.console.audit.payloadLabels.targetUser',
  task_kind: 'admin.console.audit.payloadLabels.taskKind',
  tool_name: 'admin.console.audit.payloadLabels.tool',
  usage: 'admin.console.audit.payloadLabels.tokens',
  user_id: 'admin.console.audit.payloadLabels.user',
  workspace_id: 'admin.console.audit.payloadLabels.workspace',
};

const REASON_PAYLOAD_KEYS = new Set([
  'decision_reason',
  'policy_reason',
  'ai_security_policy_reason',
]);

const ENTITY_TYPE_PAYLOAD_KEYS = new Set([
  'blocked_entity_types',
  'removed_entity_types',
  'masked_entity_types',
]);

function translateWithFallback(
  t: Translate,
  key: string,
  fallback: string,
  options?: Record<string, unknown>,
): string {
  const translated = t(key, options);
  return translated === key ? fallback : translated;
}

function humanizeIdentifier(value: string): string {
  return value
    .replace(/[_-]+/g, ' ')
    .replace(/\.+/g, ' / ')
    .replace(/\s+/g, ' ')
    .trim();
}

function formatReasonCode(value: string, t: Translate): string {
  return translateWithFallback(
    t,
    `admin.console.aiSecurity.monitoring.reasons.${value}`,
    humanizeIdentifier(value),
  );
}

function formatEntityType(value: string, t: Translate): string {
  const [base, detail] = value.split(':', 2);
  const label = translateWithFallback(
    t,
    `admin.console.aiSecurity.blockers.${base}`,
    humanizeIdentifier(base),
  );
  return detail ? `${label} (${detail})` : label;
}

function auditActionGroupKey(action: string): string {
  if (action.startsWith('admin.')) return 'admin';
  if (action.startsWith('auth.')) return 'auth';
  if (action.startsWith('mail.')) return 'mail';
  if (action.startsWith('llm_') || action.startsWith('ai_')) return 'ai';
  return 'system';
}

function payloadLabel(key: string, t: Translate): string {
  const labelKey = PAYLOAD_LABEL_KEYS[key];
  if (labelKey) {
    return translateWithFallback(t, labelKey, humanizeIdentifier(key));
  }
  return humanizeIdentifier(key);
}

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function isEmptyPayloadValue(value: unknown): boolean {
  if (value === null || value === undefined || value === '') {
    return true;
  }
  if (Array.isArray(value)) {
    return value.length === 0;
  }
  if (isPlainRecord(value)) {
    return Object.keys(value).length === 0;
  }
  return false;
}

function truncateValue(value: string): string {
  return value.length > 140 ? `${value.slice(0, 137)}...` : value;
}

function formatArrayValue(
  value: unknown[],
  t: Translate,
  key?: string,
): string {
  const visible = value.slice(0, 3).map((item) => {
    if (key && ENTITY_TYPE_PAYLOAD_KEYS.has(key) && typeof item === 'string') {
      return formatEntityType(item, t);
    }
    return formatPayloadValue(item, t);
  });
  const remaining = value.length - visible.length;
  return remaining > 0
    ? `${visible.join(', ')} ${t('admin.console.audit.moreItems', {
        count: remaining,
      })}`
    : visible.join(', ');
}

function formatUsageValue(
  value: Record<string, unknown>,
  t: Translate,
): string {
  const total = value.total_tokens;
  const prompt = value.prompt_tokens;
  const completion = value.completion_tokens;
  if (
    typeof total === 'number' ||
    typeof prompt === 'number' ||
    typeof completion === 'number'
  ) {
    return t('admin.console.audit.payloadValues.tokens', {
      completion: typeof completion === 'number' ? completion : 0,
      prompt: typeof prompt === 'number' ? prompt : 0,
      total: typeof total === 'number' ? total : 0,
    });
  }
  return truncateValue(JSON.stringify(value));
}

function formatImpersonationValue(
  value: Record<string, unknown>,
  t: Translate,
): string {
  const impersonator = value.impersonator_user_id;
  const impersonated = value.impersonated_user_id;
  if (typeof impersonator === 'string' && typeof impersonated === 'string') {
    return t('admin.console.audit.payloadValues.impersonation', {
      impersonated,
      impersonator,
    });
  }
  return truncateValue(JSON.stringify(value));
}

function formatPayloadValue(
  value: unknown,
  t: Translate,
  key?: string,
): string {
  if (value === null || value === undefined) {
    return t('common:empty.none');
  }
  if (typeof value === 'boolean') {
    return value
      ? t('admin.console.audit.payloadValues.yes')
      : t('admin.console.audit.payloadValues.no');
  }
  if (typeof value === 'number') {
    if (key === 'latency_ms') {
      return t('admin.console.audit.payloadValues.latencyMs', { value });
    }
    return new Intl.NumberFormat().format(value);
  }
  if (typeof value === 'string') {
    if (key && REASON_PAYLOAD_KEYS.has(key)) {
      return formatReasonCode(value, t);
    }
    if (key && ENTITY_TYPE_PAYLOAD_KEYS.has(key)) {
      return formatEntityType(value, t);
    }
    return truncateValue(value);
  }
  if (Array.isArray(value)) {
    return formatArrayValue(value, t, key);
  }
  if (isPlainRecord(value)) {
    if (key === 'usage') {
      return formatUsageValue(value, t);
    }
    if (key === 'impersonation') {
      return formatImpersonationValue(value, t);
    }
    return truncateValue(JSON.stringify(value));
  }
  return truncateValue(String(value));
}

function orderedPayloadKeys(payload: Record<string, unknown>): string[] {
  const known = PAYLOAD_KEY_ORDER.filter((key) => key in payload);
  const remaining = Object.keys(payload)
    .filter((key) => !PAYLOAD_KEY_ORDER.includes(key as never))
    .sort();
  return [...known, ...remaining];
}

export function buildAuditLogDisplay(
  item: AuditLogItem,
  t: Translate,
): AuditLogDisplayModel {
  const actionLabelKey = ACTION_LABEL_KEYS[item.action];
  const actionLabel = actionLabelKey
    ? translateWithFallback(t, actionLabelKey, humanizeIdentifier(item.action))
    : humanizeIdentifier(item.action);
  const groupKey = auditActionGroupKey(item.action);
  const detailItems = orderedPayloadKeys(item.payload ?? {})
    .filter((key) => !isEmptyPayloadValue(item.payload[key]))
    .slice(0, 8)
    .map((key) => ({
      key,
      label: payloadLabel(key, t),
      value: formatPayloadValue(item.payload[key], t, key),
    }));

  return {
    actionCode: item.action,
    actionLabel,
    actorLabel: item.actor_name ?? t('admin.console.audit.systemActor'),
    detailItems,
    entityLabel: `${item.entity_kind} / ${
      item.entity_id ?? t('common:empty.none')
    }`,
    groupLabel: t(`admin.console.audit.actionGroups.${groupKey}`),
    summary: item.summary || actionLabel,
  };
}
