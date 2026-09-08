import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  REALTIME_CLIENT_EVENT_TYPES,
  REALTIME_SERVER_EVENT_TYPES,
  createDocsPagesRealtimeSubscriptionMessage,
  createWhiteboardAccessRealtimeSubscriptionMessage,
} from '@open-work-hub/contracts/realtime';

import {
  createRealtimeRuntime,
  type RealtimeEvent,
  type RealtimeStatus,
} from './realtime-runtime';

class FakeSocket extends EventTarget {
  static readonly OPEN = 1;
  static readonly CLOSED = 3;

  readonly sent: string[] = [];
  readyState = 0;

  send(payload: string): void {
    this.sent.push(payload);
  }

  close(code = 1000): void {
    if (this.readyState === FakeSocket.CLOSED) {
      return;
    }
    this.readyState = FakeSocket.CLOSED;
    const event = new Event('close') as CloseEvent;
    Object.defineProperty(event, 'code', { value: code });
    this.dispatchEvent(event);
  }

  open(): void {
    this.readyState = FakeSocket.OPEN;
    this.dispatchEvent(new Event('open'));
  }

  receive(payload: unknown): void {
    this.receiveRaw(JSON.stringify(payload));
  }

  receiveRaw(data: string): void {
    this.dispatchEvent(new MessageEvent('message', { data }));
  }
}

function sentPayloads(socket: FakeSocket): Array<Record<string, unknown>> {
  return socket.sent.map(
    (payload) => JSON.parse(payload) as Record<string, unknown>,
  );
}

function createHarness() {
  const sockets: FakeSocket[] = [];
  const statuses: RealtimeStatus[] = [];
  const events: RealtimeEvent[] = [];
  const runtime = createRealtimeRuntime({
    socketFactory: () => {
      const socket = new FakeSocket();
      sockets.push(socket);
      return socket;
    },
    url: 'ws://localhost/api/v1/realtime/ws',
    token: 'token-1',
    heartbeatTimeoutMs: 70000,
    reconnectDelayMs: 2500,
    timers: {
      setTimeout: (callback, delayMs) => setTimeout(callback, delayMs),
      clearTimeout: (timerId) =>
        clearTimeout(timerId as ReturnType<typeof setTimeout>),
    },
    onStatusChange: (status) => statuses.push(status),
    onEvent: (event) => events.push(event),
  });
  return { events, runtime, sockets, statuses };
}

describe('createRealtimeRuntime', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('sends auth when the socket opens', () => {
    const { runtime, sockets } = createHarness();

    runtime.connect();
    sockets[0].open();

    expect(sentPayloads(sockets[0])).toEqual([
      { type: REALTIME_CLIENT_EVENT_TYPES.auth, token: 'token-1' },
    ]);
  });

  it('marks live and dispatches authOk events after auth succeeds', () => {
    const { events, runtime, sockets, statuses } = createHarness();

    runtime.connect();
    sockets[0].open();
    sockets[0].receive({ type: REALTIME_SERVER_EVENT_TYPES.authOk, data: {} });

    expect(statuses).toEqual(['connecting', 'live']);
    expect(events).toEqual([
      { type: REALTIME_SERVER_EVENT_TYPES.authOk, data: {} },
    ]);
  });

  it('ref-counts duplicate subscriptions and unsubscribes only on the final subscriber', () => {
    const { runtime, sockets } = createHarness();
    const subscription = createDocsPagesRealtimeSubscriptionMessage({
      key: 'doc-1',
    });

    const unsubscribeOne = runtime.subscribe(subscription);
    const unsubscribeTwo = runtime.subscribe(subscription);
    runtime.connect();
    sockets[0].open();
    sockets[0].receive({ type: REALTIME_SERVER_EVENT_TYPES.authOk });

    expect(
      sentPayloads(sockets[0]).filter(
        (payload) => payload.type === REALTIME_CLIENT_EVENT_TYPES.subscribe,
      ),
    ).toHaveLength(1);

    unsubscribeOne();
    expect(
      sentPayloads(sockets[0]).filter(
        (payload) => payload.type === REALTIME_CLIENT_EVENT_TYPES.unsubscribe,
      ),
    ).toHaveLength(0);

    unsubscribeTwo();
    expect(
      sentPayloads(sockets[0]).filter(
        (payload) => payload.type === REALTIME_CLIENT_EVENT_TYPES.unsubscribe,
      ),
    ).toEqual([
      {
        type: REALTIME_CLIENT_EVENT_TYPES.unsubscribe,
        topic: subscription.topic,
        key: subscription.key,
        share_token: null,
      },
    ]);
  });

  it('ignores malformed JSON messages', () => {
    const { events, runtime, sockets } = createHarness();
    const listener = vi.fn();
    runtime.addEventListener('*', listener);

    runtime.connect();
    sockets[0].open();
    sockets[0].receiveRaw('{');

    expect(events).toEqual([]);
    expect(listener).not.toHaveBeenCalled();
  });

  it('keeps direct and distinct link authorities independently subscribed and replayed', () => {
    const { runtime, sockets } = createHarness();
    const direct = createDocsPagesRealtimeSubscriptionMessage({ key: 'doc-1' });
    const firstLink = createDocsPagesRealtimeSubscriptionMessage({
      key: 'doc-1',
      shareToken: 'first-link',
    });
    const otherLink = createDocsPagesRealtimeSubscriptionMessage({
      key: 'doc-1',
      shareToken: 'other-link',
    });
    const removeDirect = runtime.subscribe(direct);
    const removeFirst = runtime.subscribe(firstLink);
    const removeDuplicate = runtime.subscribe(firstLink);
    runtime.subscribe(otherLink);
    runtime.connect();
    sockets[0].open();
    sockets[0].receive({ type: REALTIME_SERVER_EVENT_TYPES.authOk });
    expect(
      sentPayloads(sockets[0]).filter(
        (message) => message.type === REALTIME_CLIENT_EVENT_TYPES.subscribe,
      ),
    ).toEqual([direct, firstLink, otherLink]);
    removeFirst();
    expect(
      sentPayloads(sockets[0]).filter(
        (message) => message.type === REALTIME_CLIENT_EVENT_TYPES.unsubscribe,
      ),
    ).toEqual([]);
    removeDuplicate();
    removeDirect();
    expect(
      sentPayloads(sockets[0]).filter(
        (message) => message.type === REALTIME_CLIENT_EVENT_TYPES.unsubscribe,
      ),
    ).toEqual([
      { ...firstLink, type: REALTIME_CLIENT_EVENT_TYPES.unsubscribe },
      { ...direct, type: REALTIME_CLIENT_EVENT_TYPES.unsubscribe },
    ]);
    sockets[0].close(1006);
    vi.advanceTimersByTime(2500);
    sockets[1].open();
    sockets[1].receive({ type: REALTIME_SERVER_EVENT_TYPES.authOk });
    expect(
      sentPayloads(sockets[1]).filter(
        (message) => message.type === REALTIME_CLIENT_EVENT_TYPES.subscribe,
      ),
    ).toEqual([otherLink]);
  });

  it('keeps Docs and Whiteboard subscriptions independent for matching resource IDs', () => {
    const { runtime, sockets } = createHarness();
    const docs = createDocsPagesRealtimeSubscriptionMessage({
      key: 'resource-1',
    });
    const whiteboard = createWhiteboardAccessRealtimeSubscriptionMessage({
      key: 'resource-1',
      shareToken: 'shared-board',
    });
    const unsubscribeDocs = runtime.subscribe(docs);
    runtime.subscribe(whiteboard);
    runtime.connect();
    sockets[0].open();
    sockets[0].receive({ type: REALTIME_SERVER_EVENT_TYPES.authOk });
    expect(
      sentPayloads(sockets[0]).filter(
        (message) => message.type === REALTIME_CLIENT_EVENT_TYPES.subscribe,
      ),
    ).toEqual([docs, whiteboard]);

    unsubscribeDocs();
    sockets[0].close(1006);
    vi.advanceTimersByTime(2500);
    sockets[1].open();
    sockets[1].receive({ type: REALTIME_SERVER_EVENT_TYPES.authOk });
    expect(
      sentPayloads(sockets[1]).filter(
        (message) => message.type === REALTIME_CLIENT_EVENT_TYPES.subscribe,
      ),
    ).toEqual([whiteboard]);
  });

  it.each([1008, 4401, 4403, 4409])(
    'does not reconnect after policy close code %s',
    (closeCode) => {
      const { runtime, sockets } = createHarness();

      runtime.connect();
      sockets[0].open();
      sockets[0].close(closeCode);
      vi.advanceTimersByTime(2500);

      expect(sockets).toHaveLength(1);
    },
  );

  it('closes stale sockets after the heartbeat timeout', () => {
    const { runtime, sockets, statuses } = createHarness();

    runtime.connect();
    sockets[0].open();
    vi.advanceTimersByTime(70000);

    expect(sockets[0].readyState).toBe(FakeSocket.CLOSED);
    expect(statuses).toEqual(['connecting', 'offline']);
  });

  it('replays active subscriptions after reconnect and auth', () => {
    const { runtime, sockets } = createHarness();
    const subscription = createDocsPagesRealtimeSubscriptionMessage({
      key: 'doc-1',
    });
    runtime.subscribe(subscription);

    runtime.connect();
    sockets[0].open();
    sockets[0].receive({ type: REALTIME_SERVER_EVENT_TYPES.authOk });
    sockets[0].close(1006);
    vi.advanceTimersByTime(2500);
    sockets[1].open();
    sockets[1].receive({ type: REALTIME_SERVER_EVENT_TYPES.authOk });

    expect(
      sentPayloads(sockets[1]).filter(
        (payload) => payload.type === REALTIME_CLIENT_EVENT_TYPES.subscribe,
      ),
    ).toEqual([subscription]);
  });
});
