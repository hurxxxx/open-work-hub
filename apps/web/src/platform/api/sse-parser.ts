import { createParser, type EventSourceMessage } from 'eventsource-parser';

export type SseJsonDecodeResult<T> =
  | {
      ok: true;
      event: EventSourceMessage;
      value: T;
    }
  | {
      ok: false;
      error: unknown;
      event: EventSourceMessage;
    };

export interface SseCodecFrameResult {
  events: EventSourceMessage[];
  parseErrors: Error[];
}

export function decodeSseJsonEvent<T = unknown>(
  event: EventSourceMessage,
): SseJsonDecodeResult<T> {
  try {
    return {
      ok: true,
      event,
      value: JSON.parse(event.data) as T,
    };
  } catch (error) {
    return {
      ok: false,
      error,
      event,
    };
  }
}

export class SseEventCodec {
  private readonly decoder = new TextDecoder();
  private readonly events: EventSourceMessage[] = [];
  private readonly parseErrors: Error[] = [];
  private readonly parser = createParser({
    onEvent: (event) => {
      this.events.push(event);
    },
    onError: (error) => {
      this.parseErrors.push(error);
    },
  });

  feedBytes(chunk: Uint8Array): SseCodecFrameResult {
    const text = this.decoder.decode(chunk, { stream: true });
    if (text.length === 0) {
      return this.drain();
    }
    return this.feedText(text);
  }

  feedText(chunk: string): SseCodecFrameResult {
    this.parser.feed(chunk);
    return this.drain();
  }

  close(): SseCodecFrameResult {
    const trailingText = this.decoder.decode();
    if (trailingText.length > 0) {
      this.parser.feed(trailingText);
    }
    return this.drain();
  }

  reset(): void {
    this.decoder.decode();
    this.parser.reset();
    this.events.length = 0;
    this.parseErrors.length = 0;
  }

  private drain(): SseCodecFrameResult {
    return {
      events: this.events.splice(0),
      parseErrors: this.parseErrors.splice(0),
    };
  }
}

export class SseEventStream implements AsyncIterable<EventSourceMessage> {
  private readonly codec = new SseEventCodec();
  private readonly queue: EventSourceMessage[] = [];
  private readonly reader: ReadableStreamDefaultReader<Uint8Array>;
  private readonly waiters: Array<() => void> = [];
  private readonly abortListener = () => {
    void this.close();
  };

  private closed = false;
  private producerDone = false;
  private producerError: unknown = null;
  private pumpPromise: Promise<void>;

  constructor(
    body: ReadableStream<Uint8Array>,
    private readonly signal: AbortSignal,
  ) {
    this.reader = body.getReader();
    if (!signal.aborted) {
      signal.addEventListener('abort', this.abortListener, { once: true });
    }
    this.pumpPromise = this.pump();
    if (signal.aborted) {
      void this.close();
    }
  }

  [Symbol.asyncIterator](): AsyncIterator<EventSourceMessage> {
    return {
      next: () => this.next(),
      return: async () => {
        await this.close();
        return {
          done: true,
          value: undefined,
        };
      },
      throw: async (error) => {
        await this.close();
        throw error;
      },
    };
  }

  async close(): Promise<void> {
    if (!this.closed) {
      this.closed = true;
      this.signal.removeEventListener('abort', this.abortListener);
      this.resolveWaiters();
      try {
        await this.reader.cancel('sse-stream-closed');
      } catch {
        /* ignore - stream may already be closed or released */
      }
    }
    await this.pumpPromise.catch(() => undefined);
  }

  private async next(): Promise<IteratorResult<EventSourceMessage, void>> {
    while (true) {
      if (this.closed || this.signal.aborted) {
        return {
          done: true,
          value: undefined,
        };
      }
      const nextEvent = this.queue.shift();
      if (nextEvent) {
        return {
          done: false,
          value: nextEvent,
        };
      }
      if (this.producerDone) {
        if (this.producerError) {
          throw this.producerError;
        }
        return {
          done: true,
          value: undefined,
        };
      }
      await this.waitForProducer();
    }
  }

  private async pump(): Promise<void> {
    try {
      while (!this.closed && !this.signal.aborted) {
        const { value, done } = await this.reader.read();
        if (done) {
          this.enqueue(this.codec.close().events);
          return;
        }
        this.enqueue(this.codec.feedBytes(value).events);
      }
    } catch (error) {
      if (!this.closed && !this.signal.aborted) {
        this.producerError = error;
      }
    } finally {
      this.producerDone = true;
      this.signal.removeEventListener('abort', this.abortListener);
      this.resolveWaiters();
      try {
        this.reader.releaseLock();
      } catch {
        /* ignore - already released */
      }
    }
  }

  private enqueue(events: EventSourceMessage[]): void {
    if (events.length === 0) {
      return;
    }
    this.queue.push(...events);
    this.resolveWaiters();
  }

  private waitForProducer(): Promise<void> {
    return new Promise((resolve) => {
      this.waiters.push(resolve);
    });
  }

  private resolveWaiters(): void {
    const waiters = this.waiters.splice(0);
    for (const resolve of waiters) {
      resolve();
    }
  }
}

/**
 * Convert a fetch response body into an async iterable of SSE events.
 * Uses eventsource-parser so UTF-8 splits, multi-line data fields,
 * and comment keepalives are handled correctly.
 */
export async function* iterSseEvents(
  body: ReadableStream<Uint8Array>,
  signal: AbortSignal,
): AsyncGenerator<EventSourceMessage> {
  const stream = new SseEventStream(body, signal);
  try {
    yield* stream;
  } finally {
    await stream.close();
  }
}
