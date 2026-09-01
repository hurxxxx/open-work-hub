import { beforeEach, describe, expect, it, vi } from 'vitest';

import { sendAiChat, type AiChatRequest } from './chatbot-api';

const hermesMocks = vi.hoisted(() => ({
  createHermesRun: vi.fn(),
  createHermesSession: vi.fn(),
  getHermesRun: vi.fn(),
}));

vi.mock('./hermes-agent-api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./hermes-agent-api')>()),
  createHermesRun: hermesMocks.createHermesRun,
  createHermesSession: hermesMocks.createHermesSession,
  getHermesRun: hermesMocks.getHermesRun,
}));

describe('Hermes chat session creation', () => {
  beforeEach(() => {
    hermesMocks.createHermesRun.mockReset();
    hermesMocks.createHermesSession.mockReset();
    hermesMocks.getHermesRun.mockReset();
    hermesMocks.createHermesRun.mockResolvedValue({ id: 'run-1' });
    hermesMocks.getHermesRun.mockResolvedValue({
      id: 'run-1',
      output_text: 'done',
      status: 'completed',
      usage: null,
    });
  });

  it('leaves first-turn titles to the official Hermes auto-title flow', async () => {
    hermesMocks.createHermesSession
      .mockResolvedValueOnce({ id: 'owh-session-1' })
      .mockResolvedValueOnce({ id: 'owh-session-2' });
    const payload = {
      conversation_id: null,
      messages: [{ role: 'user', content: '같은 첫 질문' }],
    } as AiChatRequest;

    await sendAiChat(payload, 'token');
    await sendAiChat(payload, 'token');

    expect(hermesMocks.createHermesSession).toHaveBeenCalledTimes(2);
    expect(hermesMocks.createHermesSession).toHaveBeenNthCalledWith(
      1,
      'token',
      {
        scope_ref: null,
        scope_resource_id: null,
        title: null,
      },
      undefined,
    );
    expect(hermesMocks.createHermesSession).toHaveBeenNthCalledWith(
      2,
      'token',
      {
        scope_ref: null,
        scope_resource_id: null,
        title: null,
      },
      undefined,
    );
  });
});
