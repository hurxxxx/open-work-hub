import { expect, test } from '@playwright/test';

import {
  stubApprovalApi,
  stubConversationsApi,
  stubShellBackend,
} from './helpers';

const PENDING_CONVERSATION = {
  id: 'conversation-approval',
  title: '',
  createdAt: '2026-04-22T11:00:00Z',
  updatedAt: '2026-04-22T11:00:00Z',
  scopeRef: null,
  scopeResourceId: null,
  livePendingApproval: {
    approvalId: 'approval-1',
    agentRunId: 'agent-run-1',
    callId: 'call-approval-1',
    tool: 'docs.create_page',
    resourcePreview: '승인 테스트 문서',
    expiresAtMs: Date.parse('2026-04-22T12:00:00Z'),
    status: 'pending' as const,
    reason: null,
  },
  turns: [],
};

test.describe('AI approval modal flow', () => {
  test.beforeEach(async ({ page }) => {
    await stubShellBackend(page);
    await stubConversationsApi(page, {
      detail: {
        'conversation-approval': PENDING_CONVERSATION,
      },
    });
  });

  test('restores a live pending approval on reload and blocks the composer', async ({
    page,
  }) => {
    await stubApprovalApi(page);

    await page.goto('/w/hq/ai?c=conversation-approval');

    await expect(page.getByRole('dialog', { name: '작업 승인 필요' })).toBeVisible();
    await expect(page.getByPlaceholder('현재 승인을 해결해야 다음 요청이 가능합니다.')).toBeDisabled();
    await expect(page.getByText('승인 테스트 문서', { exact: true })).toBeVisible();
  });

  test('approves and resumes into the assistant response', async ({ page }) => {
    await stubApprovalApi(page, {
      resolveResponse: {
        id: 'approval-1',
        workspace_id: 'workspace-hq',
        conversation_id: 'conversation-approval',
        agent_run_id: 'agent-run-1',
        tool_call_id: 'call-approval-1',
        tool_name: 'docs.create_page',
        arguments_json: '{"title":"승인 테스트"}',
        resource_preview: '승인 테스트 문서',
        status: 'approved',
        requested_by_user_id: 'user-e2e',
        resolved_by_user_id: 'user-e2e',
        reject_reason: null,
        resolved_at: '2026-04-22T11:05:00Z',
        expires_at: '2026-04-22T12:00:00Z',
        execution_result_json: null,
        error_message: null,
        created_at: '2026-04-22T11:00:00Z',
        snapshot_status: 'resumed',
      },
      resumeFrames: [
        `event: approval_resolved\r\ndata: ${JSON.stringify({
          seq: 0,
          timestamp_ms: 0,
          type: 'approval_resolved',
          data: {
            approval_id: 'approval-1',
            call_id: 'call-approval-1',
            decision: 'approved',
            reason: null,
          },
        })}\r\n\r\n`,
        `event: content_delta\r\ndata: ${JSON.stringify({
          seq: 1,
          timestamp_ms: 0,
          type: 'content_delta',
          data: { text: '승인 후 재개 완료' },
        })}\r\n\r\n`,
        `event: done\r\ndata: ${JSON.stringify({
          seq: 2,
          timestamp_ms: 0,
          type: 'done',
          data: { finish_reason: 'stop', audit_id: null, meta: null },
        })}\r\n\r\n`,
      ],
    });

    await page.goto('/w/hq/ai?c=conversation-approval');

    await page.getByRole('button', { name: '승인' }).click();

    await expect(page.getByRole('dialog', { name: '작업 승인 필요' })).toHaveCount(0);
    await expect(page.getByText('승인 후 재개 완료')).toBeVisible();
    await expect(page.getByPlaceholder('메시지를 입력하세요')).toBeEnabled();
  });

  test('rejects with a reason and resumes with the rejected path', async ({ page }) => {
    await stubApprovalApi(page, {
      resolveResponse: {
        id: 'approval-1',
        workspace_id: 'workspace-hq',
        conversation_id: 'conversation-approval',
        agent_run_id: 'agent-run-1',
        tool_call_id: 'call-approval-1',
        tool_name: 'docs.create_page',
        arguments_json: '{"title":"승인 테스트"}',
        resource_preview: '승인 테스트 문서',
        status: 'rejected',
        requested_by_user_id: 'user-e2e',
        resolved_by_user_id: 'user-e2e',
        reject_reason: '우선 보류',
        resolved_at: '2026-04-22T11:05:00Z',
        expires_at: '2026-04-22T12:00:00Z',
        execution_result_json: null,
        error_message: null,
        created_at: '2026-04-22T11:00:00Z',
        snapshot_status: 'resumed',
      },
      resumeFrames: [
        `event: approval_resolved\r\ndata: ${JSON.stringify({
          seq: 0,
          timestamp_ms: 0,
          type: 'approval_resolved',
          data: {
            approval_id: 'approval-1',
            call_id: 'call-approval-1',
            decision: 'rejected',
            reason: '우선 보류',
          },
        })}\r\n\r\n`,
        `event: content_delta\r\ndata: ${JSON.stringify({
          seq: 1,
          timestamp_ms: 0,
          type: 'content_delta',
          data: { text: '거절 사유를 반영해 다음 단계를 정리했어요.' },
        })}\r\n\r\n`,
        `event: done\r\ndata: ${JSON.stringify({
          seq: 2,
          timestamp_ms: 0,
          type: 'done',
          data: { finish_reason: 'stop', audit_id: null, meta: null },
        })}\r\n\r\n`,
      ],
    });

    await page.goto('/w/hq/ai?c=conversation-approval');

    await page.getByPlaceholder('필요하면 거절 사유를 남기세요. 비워도 됩니다.').fill('우선 보류');
    await page.getByRole('button', { name: '거절' }).click();

    await expect(page.getByRole('dialog', { name: '작업 승인 필요' })).toHaveCount(0);
    await expect(page.getByText('거절 사유를 반영해 다음 단계를 정리했어요.')).toBeVisible();
    await expect(page.getByPlaceholder('메시지를 입력하세요')).toBeEnabled();
  });

  test('abandons the pending approval and re-enables the composer without resume', async ({
    page,
  }) => {
    await stubApprovalApi(page);

    await page.goto('/w/hq/ai?c=conversation-approval');

    await page.getByRole('button', { name: '요청 취소' }).click();

    await expect(page.getByRole('dialog', { name: '작업 승인 필요' })).toHaveCount(0);
    await expect(page.getByPlaceholder('메시지를 입력하세요')).toBeEnabled();
    await expect(page.getByText('현재 승인을 해결해야 다음 요청이 가능합니다.')).toHaveCount(0);
  });
});
