import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  sendAiChat,
  streamAiChat,
  streamAiExistingRun,
  type AiChatRequest,
} from './chatbot-api';
import { HermesAgentApiError } from './hermes-agent-api';

const hermesMocks = vi.hoisted(() => ({
  createHermesRun: vi.fn(),
  createHermesSession: vi.fn(),
  getHermesRun: vi.fn(),
  stopHermesRun: vi.fn(),
  streamHermesRunEvents: vi.fn(),
}));

vi.mock('./hermes-agent-api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./hermes-agent-api')>()),
  createHermesRun: hermesMocks.createHermesRun,
  createHermesSession: hermesMocks.createHermesSession,
  getHermesRun: hermesMocks.getHermesRun,
  stopHermesRun: hermesMocks.stopHermesRun,
  streamHermesRunEvents: hermesMocks.streamHermesRunEvents,
}));

describe('Hermes chat session creation', () => {
  beforeEach(() => {
    hermesMocks.createHermesRun.mockReset();
    hermesMocks.createHermesSession.mockReset();
    hermesMocks.getHermesRun.mockReset();
    hermesMocks.stopHermesRun.mockReset();
    hermesMocks.stopHermesRun.mockResolvedValue({
      id: 'run-1',
      status: 'cancelled',
    });
    hermesMocks.streamHermesRunEvents.mockReset();
    vi.useRealTimers();
    hermesMocks.createHermesRun.mockResolvedValue({ id: 'run-1' });
    hermesMocks.getHermesRun.mockResolvedValue({
      id: 'run-1',
      output_text: 'done',
      status: 'completed',
      usage: null,
    });
  });

  it.each([false, true])(
    'replaces partial streamed text at completion when status lookup fails: %s',
    async (unavailable) => {
      hermesMocks.getHermesRun.mockResolvedValueOnce({
        id: 'run-1',
        status: 'running',
      });
      if (unavailable)
        hermesMocks.getHermesRun.mockRejectedValueOnce(
          new Error('Unavailable'),
        );
      else
        hermesMocks.getHermesRun.mockResolvedValueOnce({
          id: 'run-1',
          status: 'completed',
          output_text: 'complete durable answer',
        });
      hermesMocks.streamHermesRunEvents.mockResolvedValue(
        new Response(
          'id: 1\nevent: message.delta\ndata: {"event":"message.delta","delta":"partial"}\n\n' +
            'id: 2\nevent: run.completed\ndata: {"event":"run.completed","output":"complete event answer"}\n\n',
        ),
      );
      const response = await streamAiExistingRun(
        'token',
        'run-1',
        'session-1',
        new AbortController().signal,
      );
      const frames = (await response.text())
        .trim()
        .split('\n\n')
        .map((frame) => JSON.parse(frame.slice(6)));
      expect(frames.at(-1).data.content).toBe(
        unavailable ? 'complete event answer' : 'complete durable answer',
      );
      expect(frames.at(-1).data.finish_reason).toBe('stop');
    },
  );

  it('retains a longer streamed prefix when the final lookup is unavailable', async () => {
    hermesMocks.getHermesRun
      .mockResolvedValueOnce({ id: 'run-1', status: 'running' })
      .mockRejectedValueOnce(new Error('Unavailable'));
    hermesMocks.streamHermesRunEvents.mockResolvedValue(
      new Response(
        'id: 1\nevent: message.delta\ndata: {"event":"message.delta","delta":"complete streamed answer"}\n\n' +
          'id: 2\nevent: run.completed\ndata: {"event":"run.completed","output":"complete"}\n\n',
      ),
    );
    const response = await streamAiExistingRun(
      'token',
      'run-1',
      'session-1',
      new AbortController().signal,
    );
    const frames = (await response.text())
      .trim()
      .split('\n\n')
      .map((frame) => JSON.parse(frame.slice(6)));
    expect(frames.at(-1).data.content).toBe('complete streamed answer');
  });

  it.each([undefined, [], ['pms']])(
    'preserves the caller app scope when creating a native run: %j',
    async (allowedAppIds) => {
      hermesMocks.createHermesSession.mockResolvedValue({
        id: 'owh-session-1',
      });
      await sendAiChat(
        {
          messages: [{ role: 'user', content: 'Show my tasks' }],
          allowed_app_ids: allowedAppIds,
        },
        'token',
      );
      expect(hermesMocks.createHermesRun).toHaveBeenCalledWith(
        'token',
        'owh-session-1',
        expect.objectContaining({ allowed_app_ids: allowedAppIds ?? null }),
        expect.anything(),
      );
    },
  );

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
    );
    expect(hermesMocks.createHermesSession).toHaveBeenNthCalledWith(
      2,
      'token',
      {
        scope_ref: null,
        scope_resource_id: null,
        title: null,
      },
    );
  });

  it('reuses one idempotency key after an ambiguous create response', async () => {
    vi.useFakeTimers();
    hermesMocks.createHermesSession.mockResolvedValue({ id: 'owh-session-1' });
    hermesMocks.createHermesRun
      .mockRejectedValueOnce(new HermesAgentApiError(0, 'network disconnected'))
      .mockResolvedValueOnce({ id: 'run-1' });
    const resultPromise = sendAiChat(
      {
        conversation_id: null,
        messages: [{ role: 'user', content: 'retry safely' }],
      } as AiChatRequest,
      'token',
    );

    await vi.advanceTimersByTimeAsync(250);
    await resultPromise;

    expect(hermesMocks.createHermesRun).toHaveBeenCalledTimes(2);
    const firstKey = hermesMocks.createHermesRun.mock.calls[0]?.[3];
    const secondKey = hermesMocks.createHermesRun.mock.calls[1]?.[3];
    expect(firstKey).toBeTruthy();
    expect(secondKey).toBe(firstKey);
  });

  it('reconnects the durable event stream without creating another run', async () => {
    vi.useFakeTimers();
    hermesMocks.createHermesSession.mockResolvedValue({ id: 'owh-session-1' });
    hermesMocks.streamHermesRunEvents
      .mockRejectedValueOnce(new Error('temporary disconnect'))
      .mockResolvedValueOnce(
        new Response(
          'id: 2\nevent: run.completed\ndata: {"event":"run.completed","output":"done"}\n\n',
          { headers: { 'Content-Type': 'text/event-stream' } },
        ),
      );
    const response = await streamAiChat({
      payload: {
        conversation_id: null,
        messages: [{ role: 'user', content: 'keep one run' }],
      },
      signal: new AbortController().signal,
      token: 'token',
    });
    const bodyPromise = response.text();

    await vi.advanceTimersByTimeAsync(1000);
    const body = await bodyPromise;

    expect(hermesMocks.createHermesRun).toHaveBeenCalledTimes(1);
    expect(hermesMocks.streamHermesRunEvents).toHaveBeenCalledTimes(2);
    expect(body).toContain('"finish_reason":"stop"');
  });

  it('backs off repeated event streams that close before yielding an event', async () => {
    vi.useFakeTimers();
    hermesMocks.createHermesSession.mockResolvedValue({ id: 'owh-session-1' });
    hermesMocks.streamHermesRunEvents
      .mockResolvedValueOnce(
        new Response('', { headers: { 'Content-Type': 'text/event-stream' } }),
      )
      .mockResolvedValueOnce(
        new Response('', { headers: { 'Content-Type': 'text/event-stream' } }),
      )
      .mockResolvedValueOnce(
        new Response(
          'id: 2\nevent: run.completed\ndata: {"event":"run.completed","output":"done"}\n\n',
          { headers: { 'Content-Type': 'text/event-stream' } },
        ),
      );
    const response = await streamAiChat({
      payload: {
        conversation_id: null,
        messages: [{ role: 'user', content: 'back off empty streams' }],
      },
      signal: new AbortController().signal,
      token: 'token',
    });
    const bodyPromise = response.text();

    await vi.advanceTimersByTimeAsync(1000);
    expect(hermesMocks.streamHermesRunEvents).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(1999);
    expect(hermesMocks.streamHermesRunEvents).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(1);

    expect(await bodyPromise).toContain('"finish_reason":"stop"');
    expect(hermesMocks.streamHermesRunEvents).toHaveBeenCalledTimes(3);
  });

  it('resolves an intentionally closed event stream from the durable run projection', async () => {
    hermesMocks.createHermesSession.mockResolvedValue({ id: 'owh-session-1' });
    hermesMocks.getHermesRun.mockResolvedValue({
      id: 'run-1',
      output_text: 'retained result',
      status: 'completed',
      usage: { input_tokens: 2, output_tokens: 3 },
    });
    hermesMocks.streamHermesRunEvents.mockResolvedValue(
      new Response('event: stream.closed\ndata: {}\n\n', {
        headers: { 'Content-Type': 'text/event-stream' },
      }),
    );

    const response = await streamAiChat({
      payload: {
        conversation_id: null,
        messages: [{ role: 'user', content: 'recover retained result' }],
      },
      signal: new AbortController().signal,
      token: 'token',
    });
    const body = await response.text();

    expect(body).toContain('retained result');
    expect(body).toContain('"finish_reason":"stop"');
    expect(hermesMocks.getHermesRun).toHaveBeenCalledWith('token', 'run-1');
    expect(hermesMocks.streamHermesRunEvents).toHaveBeenCalledTimes(1);
  });

  it('does not reconnect after the response consumer cancels the stream', async () => {
    vi.useFakeTimers();
    hermesMocks.createHermesSession.mockResolvedValue({ id: 'owh-session-1' });
    hermesMocks.streamHermesRunEvents.mockResolvedValue(
      new Response('', { headers: { 'Content-Type': 'text/event-stream' } }),
    );
    const response = await streamAiChat({
      payload: {
        conversation_id: null,
        messages: [{ role: 'user', content: 'cancel reconnect loop' }],
      },
      signal: new AbortController().signal,
      token: 'token',
    });
    const reader = response.body?.getReader();
    expect(reader).toBeDefined();
    await reader?.read();
    await reader?.cancel();

    await vi.advanceTimersByTimeAsync(60_000);

    expect(hermesMocks.streamHermesRunEvents).toHaveBeenCalledTimes(1);
  });

  it.each([
    ['stop', 1],
    ['navigation', 0],
  ] as const)(
    'handles an early %s without duplicate or unintended cancellation',
    async (reason, expectedStops) => {
      hermesMocks.createHermesSession.mockResolvedValue({
        id: 'session-early',
      });
      const controller = new AbortController();
      controller.abort(reason);
      const response = await streamAiChat({
        payload: {
          conversation_id: null,
          messages: [{ role: 'user', content: 'start' }],
        },
        token: 'token',
        signal: controller.signal,
      });
      await response.text();
      expect(hermesMocks.createHermesRun).toHaveBeenCalledTimes(1);
      expect(hermesMocks.stopHermesRun).toHaveBeenCalledTimes(expectedStops);
    },
  );

  it('recovers an existing run and reports its actual administrator model policy', async () => {
    hermesMocks.getHermesRun.mockResolvedValue({
      id: 'run-retained',
      output_text: 'done',
      status: 'completed',
      usage: {},
      model_policy: {
        route: 'local',
        provider: 'vllm',
        model: 'selected-model',
      },
    });
    hermesMocks.streamHermesRunEvents.mockResolvedValue(
      new Response('event: stream.closed\ndata: {}\n\n'),
    );
    const response = await streamAiExistingRun(
      'token',
      'run-retained',
      'session-retained',
      new AbortController().signal,
    );
    const body = await response.text();
    expect(body).toContain('"chosen_pool":"local"');
    expect(body).toContain('"chosen_model":"selected-model"');
    expect(hermesMocks.createHermesRun).not.toHaveBeenCalled();
    expect(hermesMocks.createHermesSession).not.toHaveBeenCalled();
  });

  it.each(['running', 'completed', 'awaiting_approval'])(
    'skips resolved approvals during recovery when the run is %s',
    async (status) => {
      hermesMocks.getHermesRun.mockResolvedValue({
        id: 'run-1',
        status,
        pending_approval:
          status === 'awaiting_approval' ? { request_id: 'current' } : null,
      });
      const events = [
        { event: 'approval.request', request_id: 'resolved', tool: 'terminal' },
        { event: 'approval.responded', request_id: 'resolved' },
        { event: 'message.delta', delta: 'continued after approval' },
        status === 'awaiting_approval'
          ? {
              event: 'approval.request',
              request_id: 'current',
              tool: 'terminal',
            }
          : { event: 'run.completed', output: 'continued after approval' },
      ];
      hermesMocks.streamHermesRunEvents.mockResolvedValue(
        new Response(
          events
            .map(
              (event, i) =>
                `id: ${i + 1}\nevent: ${event.event}\ndata: ${JSON.stringify(event)}\n\n`,
            )
            .join(''),
        ),
      );
      const response = await streamAiExistingRun(
        'token',
        'run-1',
        'session-1',
        new AbortController().signal,
      );
      const frames = (await response.text())
        .trim()
        .split('\n\n')
        .map((frame) => JSON.parse(frame.slice('data: '.length)));
      expect(frames.filter((frame) => frame.type === 'content_delta')).toEqual([
        expect.objectContaining({ data: { text: 'continued after approval' } }),
      ]);
      const approvals = frames.filter(
        (frame) => frame.type === 'approval_required',
      );
      expect(approvals).toHaveLength(status === 'awaiting_approval' ? 1 : 0);
      if (status === 'awaiting_approval') {
        expect(approvals[0].data.approval_id).toBe('hermes:run-1:4:current');
      }
      expect(frames.at(-1).data.finish_reason).toBe(
        status === 'awaiting_approval' ? 'awaiting_approval' : 'stop',
      );
      expect(hermesMocks.createHermesRun).not.toHaveBeenCalled();
    },
  );

  it('retries an approval event when its authoritative state could not be read', async () => {
    vi.useFakeTimers();
    hermesMocks.getHermesRun
      .mockResolvedValueOnce({ id: 'run-1', status: 'running' })
      .mockRejectedValueOnce(new HermesAgentApiError(503, 'unavailable'))
      .mockResolvedValue({
        id: 'run-1',
        status: 'awaiting_approval',
        pending_approval: { request_id: 'current' },
      });
    hermesMocks.streamHermesRunEvents.mockImplementation(
      async () =>
        new Response(
          'id: 1\nevent: approval.request\ndata: {"event":"approval.request","request_id":"current","tool":"terminal"}\n\n',
        ),
    );
    const response = await streamAiExistingRun(
      'token',
      'run-1',
      'session-1',
      new AbortController().signal,
    );
    const bodyPromise = response.text();
    await vi.advanceTimersByTimeAsync(1000);
    const body = await bodyPromise;
    expect(hermesMocks.streamHermesRunEvents).toHaveBeenCalledTimes(2);
    expect(
      hermesMocks.streamHermesRunEvents.mock.calls[1]?.[2].afterSequence,
    ).toBe(0);
    expect(body).toContain('hermes:run-1:1:current');
    expect(body).toContain('"finish_reason":"awaiting_approval"');
  });

  it('preserves the name, duration and failure when only a native completion arrives', async () => {
    const events = [
      { event: 'tool.started', tool: 'read_file', timestamp: 1_789_257_600 },
      {
        event: 'tool.completed',
        tool: 'terminal',
        timestamp: 1_789_257_612,
        duration: 10,
        error: true,
      },
      {
        event: 'tool.completed',
        tool: 'read_file',
        timestamp: 1_789_257_614,
        error: false,
      },
      { event: 'run.completed', output: 'done' },
    ];
    hermesMocks.streamHermesRunEvents.mockResolvedValue(
      new Response(
        events
          .map(
            (event, i) =>
              `id: ${i + 1}\nevent: ${event.event}\ndata: ${JSON.stringify(event)}\n\n`,
          )
          .join(''),
      ),
    );
    const response = await streamAiExistingRun(
      'token',
      'run-1',
      'session-1',
      new AbortController().signal,
    );
    const frames = (await response.text())
      .trim()
      .split('\n\n')
      .map((frame) => JSON.parse(frame.slice('data: '.length)));
    const started = frames.filter(
      (frame) => frame.type === 'tool_call_started',
    );
    const results = frames.filter((frame) => frame.type === 'tool_result');
    expect(started.map((frame) => frame.data.name)).toEqual([
      'read_file',
      'terminal',
    ]);
    expect(results[0].data).toMatchObject({
      call_id: started[1].data.call_id,
      status: 'error',
    });
    expect(results[1].data).toMatchObject({
      call_id: started[0].data.call_id,
      status: 'ok',
    });
    expect(results[0].timestamp_ms - started[1].timestamp_ms).toBe(10_000);
  });
});
