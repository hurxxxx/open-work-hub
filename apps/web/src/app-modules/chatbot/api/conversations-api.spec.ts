import { beforeEach, describe, expect, it, vi } from 'vitest';

import { getConversation } from './conversations-api';

const hermes = vi.hoisted(() => ({
  getHermesSession: vi.fn(),
  getHermesSessionMessages: vi.fn(),
  listHermesRuns: vi.fn(),
}));

vi.mock('./hermes-agent-api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./hermes-agent-api')>()),
  ...hermes,
}));

describe('Hermes conversation history', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    hermes.getHermesSession.mockResolvedValue({
      id: 'session-1',
      title: 'History',
      created_at: '2026-09-13T00:00:00Z',
      updated_at: '2026-09-13T00:01:00Z',
    });
    hermes.getHermesSessionMessages.mockResolvedValue({ data: [] });
    hermes.listHermesRuns.mockResolvedValue({ data: [] });
  });

  it('matches stored tool results by call ID and preserves errors and missing results', async () => {
    hermes.getHermesSessionMessages.mockResolvedValue({
      data: [
        {
          role: 'assistant',
          timestamp: 1_789_257_600,
          tool_calls: ['good', 'bad', 'exit', 'missing'].map((id) => ({
            id,
            function: { name: 'terminal', arguments: '{}' },
          })),
        },
        {
          role: 'tool',
          tool_call_id: 'bad',
          content: '{"error":"Transport failed"}',
        },
        {
          role: 'tool',
          tool_call_id: 'good',
          content: '{"exit_code":0,"output":"66"}',
          timestamp: 1_789_257_610,
        },
        {
          role: 'tool',
          tool_call_id: 'exit',
          content: '{"exit_code":1,"output":"failed"}',
        },
      ],
    });

    const detail = await getConversation('token', 'session-1');

    expect(detail.turns).toHaveLength(1);
    expect(detail.turns[0]).toMatchObject({ provider: null, chosenPool: null });
    expect(detail.turns[0]?.toolCalls).toMatchObject([
      {
        call_id: 'good',
        status: 'ok',
        result: { preview: '{"exit_code":0,"output":"66"}' },
      },
      {
        call_id: 'bad',
        status: 'error',
        result: { error: 'Transport failed' },
      },
      { call_id: 'exit', status: 'error' },
      {
        call_id: 'missing',
        status: 'unknown',
        result: null,
        completedAtMs: null,
      },
    ]);
    const good = detail.turns[0]?.toolCalls?.[0];
    expect(Number(good?.completedAtMs) - Number(good?.startedAtMs)).toBe(
      10_000,
    );
  });

  it.each(['failed', 'invalid_output'])(
    'restores the latest %s run error',
    async (status) => {
      hermes.listHermesRuns.mockResolvedValue({
        data: [{ status, error_message: 'Provider returned HTTP 429' }],
      });
      expect(await getConversation('token', 'session-1')).toMatchObject({
        runError: 'Provider returned HTTP 429',
      });
    },
  );

  it('does not retain an older error after a successful run', async () => {
    hermes.listHermesRuns.mockResolvedValue({
      data: [{ status: 'completed', error_message: null }],
    });
    expect(await getConversation('token', 'session-1')).toMatchObject({
      runError: null,
    });
  });
});
