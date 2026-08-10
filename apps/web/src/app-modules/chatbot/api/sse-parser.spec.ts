import type { EventSourceMessage } from 'eventsource-parser';
import { describe, expect, it } from 'vitest';

import { decodeSseJsonEvent, iterSseEvents, SseEventCodec } from './sse-parser';

const encoder = new TextEncoder();

function bytes(text: string): Uint8Array {
  return encoder.encode(text);
}

function streamFromChunks(chunks: Uint8Array[]): ReadableStream<Uint8Array> {
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(chunk);
      }
      controller.close();
    },
  });
}

async function collectEvents(chunks: Uint8Array[]): Promise<EventSourceMessage[]> {
  const controller = new AbortController();
  const events: EventSourceMessage[] = [];
  for await (const event of iterSseEvents(streamFromChunks(chunks), controller.signal)) {
    events.push(event);
  }
  return events;
}

function indexOfSubarray(haystack: Uint8Array, needle: Uint8Array): number {
  for (let index = 0; index <= haystack.length - needle.length; index += 1) {
    let matches = true;
    for (let offset = 0; offset < needle.length; offset += 1) {
      if (haystack[index + offset] !== needle[offset]) {
        matches = false;
        break;
      }
    }
    if (matches) {
      return index;
    }
  }
  return -1;
}

describe('SseEventCodec', () => {
  it('keeps parser and UTF-8 state across chunk boundaries', async () => {
    const payload = `event: content_delta\ndata: ${JSON.stringify({ text: '안녕' })}\n\n`;
    const encoded = bytes(payload);
    const koreanByteIndex = indexOfSubarray(encoded, bytes('녕'));
    if (koreanByteIndex < 0) {
      throw new Error('test payload did not include expected UTF-8 bytes');
    }

    const events = await collectEvents([
      encoded.slice(0, koreanByteIndex + 1),
      encoded.slice(koreanByteIndex + 1),
    ]);

    expect(events).toHaveLength(1);
    const event = events.at(0);
    expect(event?.event).toBe('content_delta');

    if (!event) {
      throw new Error('expected one SSE event');
    }
    const decoded = decodeSseJsonEvent<{ text: string }>(event);
    expect(decoded.ok).toBe(true);
    if (decoded.ok) {
      expect(decoded.value).toEqual({ text: '안녕' });
    }
  });

  it('frames multiple events from one chunk', () => {
    const codec = new SseEventCodec();
    const result = codec.feedText(
      [
        'id: first',
        'event: content_delta',
        'data: {"text":"Hel"}',
        '',
        'event: content_delta',
        'data: {"text":"lo"}',
        '',
        '',
      ].join('\n'),
    );

    expect(result.parseErrors).toEqual([]);
    expect(result.events).toEqual([
      {
        id: 'first',
        event: 'content_delta',
        data: '{"text":"Hel"}',
      },
      {
        event: 'content_delta',
        data: '{"text":"lo"}',
      },
    ]);
  });

  it('ignores comments and blank keepalive frames', () => {
    const codec = new SseEventCodec();

    expect(codec.feedText(': keepalive\n\n\n: still alive\n\n')).toEqual({
      events: [],
      parseErrors: [],
    });

    expect(codec.feedText('event: message\n\n')).toEqual({
      events: [],
      parseErrors: [],
    });
  });

  it('returns JSON decode errors without throwing', () => {
    const decoded = decodeSseJsonEvent({
      event: 'message',
      data: '{"unterminated":',
    });

    expect(decoded.ok).toBe(false);
    if (!decoded.ok) {
      expect(decoded.error).toBeInstanceOf(SyntaxError);
      expect(decoded.event.data).toBe('{"unterminated":');
    }
  });
});

describe('SseEventStream', () => {
  it('drains queued events when the readable stream closes', async () => {
    const events = await collectEvents([
      bytes('event: content_delta\ndata: {"text":"done"}\n\n'),
    ]);

    expect(events).toEqual([
      {
        event: 'content_delta',
        data: '{"text":"done"}',
      },
    ]);
  });

  it('closes the reader when the consumer stops early', async () => {
    let canceled = false;
    const controller = new AbortController();
    const body = new ReadableStream<Uint8Array>({
      start(streamController) {
        streamController.enqueue(bytes('event: content_delta\ndata: {"text":"first"}\n\n'));
      },
      cancel() {
        canceled = true;
      },
    });

    const events: EventSourceMessage[] = [];
    for await (const event of iterSseEvents(body, controller.signal)) {
      events.push(event);
      break;
    }

    expect(events).toHaveLength(1);
    expect(canceled).toBe(true);
  });

  it('completes pending reads when the abort signal fires', async () => {
    let canceled = false;
    const controller = new AbortController();
    const body = new ReadableStream<Uint8Array>({
      cancel() {
        canceled = true;
      },
    });

    const iterator = iterSseEvents(body, controller.signal)[Symbol.asyncIterator]();
    const pending = iterator.next();

    controller.abort();

    await expect(pending).resolves.toEqual({
      done: true,
      value: undefined,
    });
    expect(canceled).toBe(true);
  });

  it('surfaces readable stream errors to the iterator', async () => {
    const failure = new Error('network closed');
    const controller = new AbortController();
    const body = new ReadableStream<Uint8Array>({
      start(streamController) {
        streamController.error(failure);
      },
    });

    const iterator = iterSseEvents(body, controller.signal)[Symbol.asyncIterator]();
    await expect(iterator.next()).rejects.toThrow(failure);
  });
});
