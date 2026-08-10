import { describe, expect, it } from 'vitest';

import type { AuditLogItem } from './admin-api';
import { buildAuditLogDisplay } from './admin-audit-log-model';

const messages: Record<string, string> = {
  'admin.console.audit.actionGroups.admin': '관리',
  'admin.console.audit.actionGroups.ai': 'AI',
  'admin.console.audit.actionGroups.auth': '인증',
  'admin.console.audit.actions.adminPlatformApiKeyReveal': '플랫폼 API 키 조회',
  'admin.console.audit.actions.authLogin': '로그인',
  'admin.console.audit.actions.llmToolCall': 'AI 도구 호출',
  'admin.console.audit.moreItems': '외 {{count}}개',
  'admin.console.audit.payloadLabels.latency': '지연',
  'admin.console.audit.payloadLabels.status': '상태',
  'admin.console.audit.payloadLabels.tokens': '토큰',
  'admin.console.audit.payloadLabels.tool': '도구',
  'admin.console.audit.payloadValues.latencyMs': '{{value}}ms',
  'admin.console.audit.payloadValues.no': '아니오',
  'admin.console.audit.payloadValues.tokens':
    '전체 {{total}} / 입력 {{prompt}} / 응답 {{completion}}',
  'admin.console.audit.payloadValues.yes': '예',
  'admin.console.audit.systemActor': '시스템',
  'common:empty.none': '없음',
};

function t(key: string, options?: Record<string, unknown>): string {
  const template = messages[key] ?? key;
  return template.replace(/\{\{(\w+)}}/g, (_, token: string) =>
    String(options?.[token] ?? ''),
  );
}

function auditItem(overrides: Partial<AuditLogItem> = {}): AuditLogItem {
  return {
    id: 'audit-1',
    action: 'auth.login',
    actor_name: 'AI-DO Admin',
    actor_user_id: 'user-1',
    created_at: '2026-06-18T09:00:00',
    entity_id: 'session-1',
    entity_kind: 'auth_session',
    payload: {},
    summary: 'Admin signed in',
    ...overrides,
  };
}

describe('admin audit log model', () => {
  it('labels known audit actions and groups', () => {
    const display = buildAuditLogDisplay(auditItem(), t);

    expect(display.actionLabel).toBe('로그인');
    expect(display.groupLabel).toBe('인증');
    expect(display.actorLabel).toBe('AI-DO Admin');
    expect(display.entityLabel).toBe('auth_session / session-1');
  });

  it('labels platform API key security actions', () => {
    const display = buildAuditLogDisplay(
      auditItem({ action: 'admin.platform_api_key.reveal' }),
      t,
    );

    expect(display.actionLabel).toBe('플랫폼 API 키 조회');
    expect(display.groupLabel).toBe('관리');
  });

  it('turns payload JSON into priority details', () => {
    const display = buildAuditLogDisplay(
      auditItem({
        action: 'llm_tool_call',
        actor_name: null,
        payload: {
          ignored_empty: [],
          latency_ms: 42,
          status: 'ok',
          tool_name: 'docs.read_page',
          usage: {
            completion_tokens: 5,
            prompt_tokens: 10,
            total_tokens: 15,
          },
        },
      }),
      t,
    );

    expect(display.actionLabel).toBe('AI 도구 호출');
    expect(display.groupLabel).toBe('AI');
    expect(display.actorLabel).toBe('시스템');
    expect(display.detailItems).toEqual([
      { key: 'status', label: '상태', value: 'ok' },
      { key: 'tool_name', label: '도구', value: 'docs.read_page' },
      { key: 'latency_ms', label: '지연', value: '42ms' },
      {
        key: 'usage',
        label: '토큰',
        value: '전체 15 / 입력 10 / 응답 5',
      },
    ]);
  });
});
