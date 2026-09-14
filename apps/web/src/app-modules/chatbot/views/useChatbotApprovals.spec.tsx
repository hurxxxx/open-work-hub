import { act, renderHook } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';

import type { PendingApproval } from '../api/agent-events';
import { AiApiError, resolveAiApproval } from '../api/chatbot-api';
import { useChatbotApprovals } from './useChatbotApprovals';

vi.mock('../api/chatbot-api', async (original) => ({
  ...(await original<typeof import('../api/chatbot-api')>()),
  resolveAiApproval: vi.fn(),
}));

const approval: PendingApproval = {
  approval_id: 'approval-1',
  call_id: 'call-1',
  tool: 'tasks.create',
  resource_preview: null,
  expires_at_ms: Date.now() + 60_000,
  decision: null,
};
const resolved = {
  id: approval.approval_id,
  conversation_id: 'conversation-1',
  agent_run_id: 'run-1',
  tool_call_id: 'call-1',
  tool_name: 'tasks.create',
  arguments_json: '{}',
  status: 'approved',
  requested_by_user_id: 'user-1',
  expires_at: '2026-09-14T02:00:00Z',
  created_at: '2026-09-14T01:00:00Z',
};
function props() {
  return {
    allowedAppIds: ['chatbot'],
    currentConversationId: 'conversation-1',
    routeConversationId: 'conversation-1',
    isConversationReady: true,
    isSending: false,
    pendingApprovals: [approval],
    replacePendingApprovals: vi.fn(),
    resumeChat: vi.fn().mockResolvedValue(undefined),
    setApprovalAction: vi.fn(),
    setApprovalError: vi.fn(),
    token: 'token',
    upsertPendingApproval: vi.fn(),
  };
}
beforeEach(() => vi.clearAllMocks());

it('resolves a double click only once and resumes with the exact decision', async () => {
  let finish!: () => void;
  vi.mocked(resolveAiApproval).mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = () => resolve({ ...resolved, status: 'rejected' });
      }),
  );
  const input = props();
  const { result } = renderHook(() => useChatbotApprovals(input));
  let first!: Promise<void>;
  act(() => {
    first = result.current.handleResolveApproval(approval, 'rejected');
    void result.current.handleResolveApproval(approval, 'approved');
  });
  expect(resolveAiApproval).toHaveBeenCalledTimes(1);
  await act(async () => {
    finish();
    await first;
  });
  expect(input.upsertPendingApproval).toHaveBeenCalledWith(
    expect.objectContaining({ decision: 'rejected' }),
  );
  expect(input.resumeChat).toHaveBeenCalledTimes(1);
});

it('does not resume or alter a different conversation after a late approval response', async () => {
  let finish!: () => void;
  vi.mocked(resolveAiApproval).mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = () => resolve(resolved);
      }),
  );
  const input = props();
  const { result, rerender } = renderHook(
    (value) => useChatbotApprovals(value),
    { initialProps: input },
  );
  let pending!: Promise<void>;
  act(() => {
    pending = result.current.handleResolveApproval(approval, 'approved');
  });
  rerender({
    ...input,
    currentConversationId: 'conversation-2',
    routeConversationId: 'conversation-2',
  });
  input.setApprovalAction.mockClear();
  input.setApprovalError.mockClear();
  await act(async () => {
    finish();
    await pending;
  });
  expect(input.resumeChat).not.toHaveBeenCalled();
  expect(input.upsertPendingApproval).not.toHaveBeenCalled();
  expect(input.setApprovalAction).not.toHaveBeenCalled();
  expect(input.setApprovalError).not.toHaveBeenCalled();
});

it('clears an expired approval without resuming its run', async () => {
  vi.mocked(resolveAiApproval).mockRejectedValue(
    new AiApiError(410, 'Expired'),
  );
  const input = props();
  const { result } = renderHook(() => useChatbotApprovals(input));
  await act(async () => {
    await result.current.handleResolveApproval(approval, 'approved');
  });
  expect(input.replacePendingApprovals).toHaveBeenCalledWith([]);
  expect(input.resumeChat).not.toHaveBeenCalled();
});
