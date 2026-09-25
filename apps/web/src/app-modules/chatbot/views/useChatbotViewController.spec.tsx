import { act, renderHook, waitFor } from '@testing-library/react';
import type { PropsWithChildren } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { expect, it, vi } from 'vitest';

import { streamAiChat } from '../api/chatbot-api';
import { useChatbotViewController } from './useChatbotViewController';

vi.mock('@open-work-hub/ui', async (original) => ({
  ...(await original<typeof import('@open-work-hub/ui')>()),
  useConfirm: () => ({ confirm: vi.fn(), confirmDialog: null }),
}));
vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({
    status: 'authenticated',
    token: 'test-token',
    user: { id: 'test-user' },
  }),
}));
vi.mock('./useChatbotHealth', () => ({
  useChatbotHealth: () => ({ health: null, healthError: null }),
}));
vi.mock('../api/chatbot-api', async (original) => ({
  ...(await original<typeof import('../api/chatbot-api')>()),
  streamAiChat: vi.fn(),
}));

it('submits ordinary chat without disabling all registered app tools', async () => {
  vi.mocked(streamAiChat).mockResolvedValue(
    new Response(
      'data: {"type":"done","seq":1,"timestamp_ms":1,"data":{"finish_reason":"stop","meta":null}}\n\n',
    ),
  );
  const hook = renderHook(() => useChatbotViewController(), {
    wrapper: ({ children }: PropsWithChildren) => (
      <MemoryRouter initialEntries={['/apps/chatbot']}>{children}</MemoryRouter>
    ),
  });

  act(() => hook.result.current.actions.setInput('내 PMS 공간을 보여줘'));
  act(() => hook.result.current.actions.handleSubmit());

  await waitFor(() => expect(streamAiChat).toHaveBeenCalledOnce());
  const request = vi.mocked(streamAiChat).mock.calls[0][0].payload;
  expect(request.messages).toEqual([
    expect.objectContaining({ role: 'user', content: '내 PMS 공간을 보여줘' }),
  ]);
  // Omission delegates the available tools to server admission and source ACL.
  // An explicit [] is a different contract: no app tools may execute.
  expect(request.allowed_app_ids).toBeUndefined();
  await waitFor(() => expect(hook.result.current.state.isSending).toBe(false));
  hook.unmount();
});
