import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApprovalModal } from './ApprovalModal';

const aiHarness = vi.hoisted(() => ({
  getAiApprovalStatus: vi.fn(),
}));

vi.mock('@/src/domains/auth/auth-provider', () => ({
  useAuth: () => ({
    token: 'test-token',
  }),
}));

vi.mock('@/src/domains/ai/ai-api', async () => {
  const actual = await vi.importActual<typeof import('@/src/domains/ai/ai-api')>(
    '@/src/domains/ai/ai-api',
  );
  return {
    ...actual,
    getAiApprovalStatus: aiHarness.getAiApprovalStatus,
  };
});

describe('ApprovalModal', () => {
  beforeEach(() => {
    aiHarness.getAiApprovalStatus.mockReset();
    aiHarness.getAiApprovalStatus.mockResolvedValue({
      id: 'approval-1',
      workspace_id: 'workspace-1',
      conversation_id: 'conversation-1',
      agent_run_id: 'agent-run-1',
      tool_call_id: 'call-1',
      tool_name: 'docs.create_page',
      arguments_json: '{"title":"분기 계획"}',
      resource_preview: '분기 계획 문서 초안',
      status: 'pending',
      requested_by_user_id: 'user-1',
      resolved_by_user_id: null,
      reject_reason: null,
      resolved_at: null,
      expires_at: '2026-04-21T12:00:00Z',
      execution_result_json: null,
      error_message: null,
      created_at: '2026-04-21T11:00:00Z',
      snapshot_status: 'awaiting_approval',
    });
  });

  it('does not treat the dialog close button as an abandon action', async () => {
    const onClose = vi.fn();

    render(
      <ApprovalModal
        approval={{
          approval_id: 'approval-1',
          call_id: 'call-1',
          tool: 'docs.create_page',
          resource_preview: '분기 계획 문서 초안',
          expires_at_ms: Date.parse('2026-04-21T12:00:00Z'),
          decision: null,
          reason: null,
        }}
        onResolve={vi.fn()}
        onClose={onClose}
      />,
    );

    await waitFor(() => {
      expect(aiHarness.getAiApprovalStatus).toHaveBeenCalledWith(
        'test-token',
        'approval-1',
      );
    });

    fireEvent.click(screen.getByRole('button', { name: /close dialog/i }));
    expect(onClose).not.toHaveBeenCalled();
  });

  it('uses the explicit 요청 취소 button for abandon', async () => {
    const onClose = vi.fn();

    render(
      <ApprovalModal
        approval={{
          approval_id: 'approval-1',
          call_id: 'call-1',
          tool: 'docs.create_page',
          resource_preview: '분기 계획 문서 초안',
          expires_at_ms: Date.parse('2026-04-21T12:00:00Z'),
          decision: null,
          reason: null,
        }}
        onResolve={vi.fn()}
        onClose={onClose}
      />,
    );

    await waitFor(() => {
      expect(aiHarness.getAiApprovalStatus).toHaveBeenCalledWith(
        'test-token',
        'approval-1',
      );
    });

    fireEvent.click(screen.getByRole('button', { name: '요청 취소' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
