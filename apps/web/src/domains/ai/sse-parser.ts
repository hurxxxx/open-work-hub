import { createParser, type EventSourceMessage } from 'eventsource-parser';

/**
 * Convert a ``fetch`` response body into an async iterable of SSE events.
 * Uses ``eventsource-parser`` so UTF-8 splits, multi-line ``data:`` fields,
 * and ``:``-comment keepalives are handled correctly.
 *
 * The iterable completes when the server closes the stream or ``signal``
 * is aborted.
 */
export async function* iterSseEvents(
  body: ReadableStream<Uint8Array>,
  signal: AbortSignal,
): AsyncGenerator<EventSourceMessage> {
  const decoder = new TextDecoder();
  const queue: EventSourceMessage[] = [];
  let resolvePending: (() => void) | null = null;
  let producerDone = false;
  let producerError: unknown = null;

  const parser = createParser({
    onEvent: (event) => {
      queue.push(event);
      resolvePending?.();
      resolvePending = null;
    },
  });

  const reader = body.getReader();

  const pump = async () => {
    try {
      while (!signal.aborted) {
        const { value, done } = await reader.read();
        if (done) {
          break;
        }
        parser.feed(decoder.decode(value, { stream: true }));
      }
    } catch (error) {
      producerError = error;
    } finally {
      producerDone = true;
      resolvePending?.();
      resolvePending = null;
      try {
        reader.releaseLock();
      } catch {
        /* ignore — already released */
      }
    }
  };

  const pumpPromise = pump();

  try {
    while (true) {
      if (queue.length > 0) {
        yield queue.shift()!;
        continue;
      }
      if (producerDone) {
        if (producerError) {
          throw producerError;
        }
        return;
      }
      await new Promise<void>((resolve) => {
        resolvePending = resolve;
      });
    }
  } finally {
    await pumpPromise.catch(() => undefined);
  }
}
