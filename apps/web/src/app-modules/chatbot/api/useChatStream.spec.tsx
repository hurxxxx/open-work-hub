import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { sendAiChat, streamAiChat, streamAiChatResume } from './chatbot-api';
import { useChatStream } from './useChatStream';

vi.mock('./chatbot-api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./chatbot-api')>();
  return {
    ...actual,
    sendAiChat: vi.fn(),
    streamAiChat: vi.fn(),
    streamAiChatResume: vi.fn(),
  };
});

describe('useChatStream', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });
  it('keeps observing after a stop request until the server confirms terminal state', async () => {
    let streamController: ReadableStreamDefaultController<Uint8Array>;
    const stop = vi.fn().mockResolvedValue(undefined);
    vi.mocked(streamAiChat).mockImplementation(async ({ onStopReady }) => {
      onStopReady?.(stop);
      return new Response(
        new ReadableStream<Uint8Array>({
          start(controller) {
            streamController = controller;
          },
        }),
      );
    });
    const hook = renderHook(() => useChatStream('token', 'confirmed-stop'));
    let sending: Promise<void>;
    act(() => {
      sending = hook.result.current.send({
        messages: [{ role: 'user', content: 'Test stop' }],
      });
    });
    await waitFor(() =>
      expect(hook.result.current.state.streamOpened).toBe(true),
    );
    act(() => {
      hook.result.current.abort();
      hook.result.current.abort();
    });
    expect(stop).toHaveBeenCalledOnce();
    expect(hook.result.current.state.status).toBe('streaming');
    expect(hook.result.current.state.isStopping).toBe(true);
    const signal = vi.mocked(streamAiChat).mock.calls.at(-1)?.[0].signal;
    expect(signal?.aborted).toBe(false);
    await act(async () => {
      streamController.enqueue(
        new TextEncoder().encode(
          'data: {"type":"done","seq":1,"timestamp_ms":1,"data":{"finish_reason":"cancelled","meta":null}}\n\n',
        ),
      );
      streamController.close();
      await sending;
    });
    expect(hook.result.current.state.status).toBe('cancelled');
    expect(hook.result.current.state.isStopping).toBe(false);
    hook.unmount();
  });

  it('allows retrying a failed stop without claiming the run was cancelled', async () => {
    const stop = vi
      .fn()
      .mockRejectedValueOnce(new Error('Stop unavailable'))
      .mockResolvedValue(undefined);
    vi.mocked(streamAiChat).mockImplementation(async ({ onStopReady }) => {
      onStopReady?.(stop);
      return new Response(new ReadableStream<Uint8Array>());
    });
    const hook = renderHook(() => useChatStream('token', 'failed-stop'));
    act(() => {
      void hook.result.current.send({
        messages: [{ role: 'user', content: 'Test stop' }],
      });
    });
    await waitFor(() =>
      expect(hook.result.current.state.streamOpened).toBe(true),
    );
    act(() => hook.result.current.abort());
    await waitFor(() =>
      expect(hook.result.current.state.errorMessage).toBe('Stop unavailable'),
    );
    expect(hook.result.current.state.status).toBe('streaming');
    expect(hook.result.current.state.isStopping).toBe(false);
    act(() => hook.result.current.abort());
    expect(stop).toHaveBeenCalledTimes(2);
    act(() => hook.result.current.reset());
    hook.unmount();
  });

  it('does not create a second run after native admission or stream opening fails', async () => {
    vi.mocked(sendAiChat).mockClear();
    vi.mocked(streamAiChat).mockRejectedValue(
      new Error('Connection lost after admission'),
    );
    const hook = renderHook(() =>
      useChatStream('token', 'no-double-admission'),
    );
    await act(() =>
      hook.result.current.send({
        messages: [{ role: 'user', content: 'One request' }],
      }),
    );
    expect(sendAiChat).not.toHaveBeenCalled();
    expect(hook.result.current.state.status).toBe('error');
    hook.unmount();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('keeps an active stream alive while the chat route is unmounted', async () => {
    vi.mocked(streamAiChat).mockImplementation(async () => {
      return new Response(
        new ReadableStream<Uint8Array>({
          start() {
            // Keep the stream pending until the user explicitly stops it.
          },
        }),
      );
    });

    const rendered = renderHook(() => useChatStream('token-1', 'user-1:docs'));
    let sendPromise: Promise<void> | null = null;

    act(() => {
      sendPromise = rendered.result.current.send({
        messages: [{ role: 'user', content: 'hi' }],
      });
    });

    await waitFor(() => {
      expect(rendered.result.current.state.streamOpened).toBe(true);
    });

    const { signal: capturedSignal } = vi.mocked(streamAiChat).mock.calls[0][0];
    expect(capturedSignal.aborted).toBe(false);

    rendered.unmount();
    expect(capturedSignal.aborted).toBe(false);

    const resumed = renderHook(() => useChatStream('token-1', 'user-1:docs'));
    expect(resumed.result.current.state.status).toBe('streaming');
    expect(resumed.result.current.state.streamOpened).toBe(true);
    expect(resumed.result.current.state.pendingUserContent).toBe('hi');

    act(() => {
      resumed.result.current.abort();
    });
    expect(capturedSignal.aborted).toBe(true);
    expect(resumed.result.current.state.status).toBe('cancelled');
    await act(async () => {
      await expect(sendPromise).resolves.toBeUndefined();
    });
    resumed.unmount();
  });

  it('isolates background runs by runtime key', async () => {
    vi.mocked(streamAiChat).mockImplementation(async () => {
      return new Response(
        new ReadableStream<Uint8Array>({
          start() {
            // Explicit abort below closes this pending stream.
          },
        }),
      );
    });

    const firstRequest = renderHook(() =>
      useChatStream('token-1', 'user-1:docs-isolated'),
    );
    const generalChat = renderHook(() =>
      useChatStream('token-1', 'user-1:chatbot'),
    );

    act(() => {
      void firstRequest.result.current.send({
        messages: [{ role: 'user', content: 'hi' }],
      });
    });

    await waitFor(() => {
      expect(firstRequest.result.current.state.streamOpened).toBe(true);
    });
    expect(generalChat.result.current.state.status).toBe('idle');

    act(() => {
      firstRequest.result.current.abort();
    });
    firstRequest.unmount();
    generalChat.unmount();
  });

  it('runs two conversations in the same chatbot independently and stops only one', async () => {
    vi.mocked(streamAiChat).mockClear();
    vi.mocked(streamAiChat).mockImplementation(
      async () => new Response(new ReadableStream<Uint8Array>()),
    );
    const first = renderHook(() =>
      useChatStream('token', 'parallel-chatbot', { conversationId: 'a' }),
    );
    const second = renderHook(() =>
      useChatStream('token', 'parallel-chatbot', { conversationId: 'b' }),
    );
    act(() => {
      void first.result.current.send({
        conversation_id: 'a',
        messages: [{ role: 'user', content: 'First' }],
      });
      void second.result.current.send({
        conversation_id: 'b',
        messages: [{ role: 'user', content: 'Second' }],
      });
    });
    await waitFor(() => {
      expect(first.result.current.state.streamOpened).toBe(true);
      expect(second.result.current.state.streamOpened).toBe(true);
    });
    const signals = vi
      .mocked(streamAiChat)
      .mock.calls.map(([args]) => args.signal);
    act(() => first.result.current.abort());
    expect(signals[0].reason).toBe('stop');
    expect(signals[1].aborted).toBe(false);
    expect(second.result.current.state.pendingUserContent).toBe('Second');
    act(() => second.result.current.abort());
    first.unmount();
    second.unmount();
  });

  it('fails a stream that reaches EOF without a terminal event', async () => {
    vi.mocked(streamAiChat).mockResolvedValue(
      new Response(
        new ReadableStream<Uint8Array>({
          start(controller) {
            controller.close();
          },
        }),
      ),
    );

    const rendered = renderHook(() =>
      useChatStream('token-1', 'eof-without-terminal'),
    );

    await act(async () => {
      await rendered.result.current.send({
        messages: [{ role: 'user', content: 'hi' }],
      });
    });

    expect(rendered.result.current.state.status).toBe('error');
    rendered.unmount();
  });

  it('does not use the sync fallback for durable graph experiences', async () => {
    vi.mocked(streamAiChat).mockRejectedValue(
      new Error('stream connection failed'),
    );

    const rendered = renderHook(() =>
      useChatStream('token-1', 'durable-no-sync-fallback', {
        disableSyncFallback: true,
      }),
    );

    await act(async () => {
      await rendered.result.current.send({
        messages: [{ role: 'user', content: 'hi' }],
      });
    });

    expect(sendAiChat).not.toHaveBeenCalled();
    expect(rendered.result.current.state.status).toBe('error');
    expect(rendered.result.current.state.errorMessage).toBe(
      'stream connection failed',
    );
    rendered.unmount();
  });

  it('fails a resumed stream that reaches EOF without a terminal event', async () => {
    vi.mocked(streamAiChatResume).mockResolvedValue(
      new Response(
        new ReadableStream<Uint8Array>({
          start(controller) {
            controller.close();
          },
        }),
      ),
    );

    const rendered = renderHook(() =>
      useChatStream('token-1', 'resume-eof-without-terminal'),
    );

    await act(async () => {
      await rendered.result.current.resume({
        approval_id: 'approval-1',
        conversation_id: 'conversation-1',
      });
    });

    expect(rendered.result.current.state.status).toBe('error');
    rendered.unmount();
  });
});
