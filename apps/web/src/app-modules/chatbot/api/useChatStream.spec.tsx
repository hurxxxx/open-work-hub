import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

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
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('keeps an active stream alive while the chat route is unmounted', async () => {
    let capturedSignal: AbortSignal | null = null;
    vi.mocked(streamAiChat).mockImplementation(async ({ signal }) => {
      capturedSignal = signal;
      return new Response(
        new ReadableStream<Uint8Array>({
          start() {
            // Keep the stream pending until the user explicitly stops it.
          },
        }),
      );
    });

    const rendered = renderHook(() =>
      useChatStream('token-1', 'workspace-1', 'user-1:legacy-issues'),
    );
    let sendPromise: Promise<void> | null = null;

    act(() => {
      sendPromise = rendered.result.current.send({
        messages: [{ role: 'user', content: 'hi' }],
      });
    });

    await waitFor(() => {
      expect(rendered.result.current.state.streamOpened).toBe(true);
    });

    expect(capturedSignal?.aborted).toBe(false);

    rendered.unmount();
    expect(capturedSignal?.aborted).toBe(false);

    const resumed = renderHook(() =>
      useChatStream('token-1', 'workspace-1', 'user-1:legacy-issues'),
    );
    expect(resumed.result.current.state.status).toBe('streaming');
    expect(resumed.result.current.state.streamOpened).toBe(true);
    expect(resumed.result.current.state.pendingUserContent).toBe('hi');

    act(() => {
      resumed.result.current.abort();
    });
    expect(capturedSignal?.aborted).toBe(true);
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

    const legacyIssues = renderHook(() =>
      useChatStream('token-1', 'workspace-1', 'user-1:legacy-issues-isolated'),
    );
    const generalChat = renderHook(() =>
      useChatStream('token-1', 'workspace-1', 'user-1:chatbot'),
    );

    act(() => {
      void legacyIssues.result.current.send({
        messages: [{ role: 'user', content: 'hi' }],
      });
    });

    await waitFor(() => {
      expect(legacyIssues.result.current.state.streamOpened).toBe(true);
    });
    expect(generalChat.result.current.state.status).toBe('idle');

    act(() => {
      legacyIssues.result.current.abort();
    });
    legacyIssues.unmount();
    generalChat.unmount();
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
      useChatStream('token-1', 'workspace-1', 'eof-without-terminal'),
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
      useChatStream('token-1', 'workspace-1', 'durable-no-sync-fallback', {
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
      useChatStream('token-1', 'workspace-1', 'resume-eof-without-terminal'),
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
