import { describe, expect, it } from 'vitest';

import {
  REALTIME_CLIENT_EVENT_TYPES,
  REALTIME_SERVER_EVENT_TYPES,
  REALTIME_TOPICS,
  REALTIME_TOPIC_EVENT_TYPES,
  REALTIME_WS_PATH,
  createDocsPagesRealtimeSubscriptionMessage,
  createWhiteboardAccessRealtimeSubscriptionMessage,
  isWhiteboardAccessRealtimeSubscriptionMessage,
  isDocsPagesRealtimeSubscriptionMessage,
  resolveRealtimeWebSocketUrl,
} from './realtime';

describe('realtime protocol contract', () => {
  it('exports the websocket path and event names shared with the API', () => {
    expect(REALTIME_WS_PATH).toBe('/api/v1/realtime/ws');
    expect(REALTIME_CLIENT_EVENT_TYPES).toEqual({
      auth: 'auth',
      subscribe: 'subscribe',
      unsubscribe: 'unsubscribe',
    });
    expect(REALTIME_SERVER_EVENT_TYPES).toEqual({
      authOk: 'realtime.auth.ok',
      keepalive: 'realtime.keepalive',
    });
    expect(REALTIME_TOPICS).toEqual({
      docsPages: 'docs.pages',
      whiteboardAccess: 'whiteboard.access',
    });
    expect(REALTIME_TOPIC_EVENT_TYPES).toEqual({
      docsPagesChanged: 'docs.pages.changed',
      docsPagesSnapshot: 'docs.pages.snapshot',
      docsAccessChanged: 'docs.access.changed',
      whiteboardAccessChanged: 'whiteboard.access.changed',
    });
  });

  it('resolves websocket URLs from HTTP origins', () => {
    expect(resolveRealtimeWebSocketUrl('http://127.0.0.1:4200')).toBe(
      'ws://127.0.0.1:4200/api/v1/realtime/ws',
    );
    expect(resolveRealtimeWebSocketUrl('https://company.example.test')).toBe(
      'wss://company.example.test/api/v1/realtime/ws',
    );
  });

  it('builds and validates docs pages subscription messages', () => {
    const message = createDocsPagesRealtimeSubscriptionMessage({
      key: 'doc-1',
      shareToken: 'share-1',
    });

    expect(message).toEqual({
      type: REALTIME_CLIENT_EVENT_TYPES.subscribe,
      topic: REALTIME_TOPICS.docsPages,
      key: 'doc-1',
      share_token: 'share-1',
    });
    expect(isDocsPagesRealtimeSubscriptionMessage(message)).toBe(true);
    expect(
      isDocsPagesRealtimeSubscriptionMessage({
        ...message,
        key: '',
      }),
    ).toBe(false);
    expect(
      isDocsPagesRealtimeSubscriptionMessage({
        ...message,
        topic: 'dm.conversations',
      }),
    ).toBe(false);
  });
});

describe('resource subscription link context', () => {
  it('builds a Whiteboard access subscription with the exact link lens', () => {
    const message = createWhiteboardAccessRealtimeSubscriptionMessage({
      key: 'board-1',
      shareToken: 'link-1',
    });
    expect(message).toEqual({
      type: 'subscribe',
      topic: 'whiteboard.access',
      key: 'board-1',
      share_token: 'link-1',
    });
    expect(isWhiteboardAccessRealtimeSubscriptionMessage(message)).toBe(true);
    expect(
      isWhiteboardAccessRealtimeSubscriptionMessage({
        ...message,
        topic: 'docs.pages',
      }),
    ).toBe(false);
    expect(
      isWhiteboardAccessRealtimeSubscriptionMessage({ ...message, key: '' }),
    ).toBe(false);
  });

  it.each([false, {}, [], 123, ''])(
    'rejects malformed link credentials %j without falling back to direct rights',
    (shareToken) => {
      expect(
        isDocsPagesRealtimeSubscriptionMessage({
          type: 'subscribe',
          topic: 'docs.pages',
          key: 'doc-1',
          share_token: shareToken,
        }),
      ).toBe(false);
      expect(
        isWhiteboardAccessRealtimeSubscriptionMessage({
          type: 'subscribe',
          topic: 'whiteboard.access',
          key: 'board-1',
          share_token: shareToken,
        }),
      ).toBe(false);
    },
  );

  it.each([null, undefined, 'exact-link'])(
    'accepts optional or explicit link contexts %j',
    (shareToken) => {
      expect(
        isDocsPagesRealtimeSubscriptionMessage({
          type: 'subscribe',
          topic: 'docs.pages',
          key: 'doc-1',
          share_token: shareToken,
        }),
      ).toBe(true);
      expect(
        isWhiteboardAccessRealtimeSubscriptionMessage({
          type: 'subscribe',
          topic: 'whiteboard.access',
          key: 'board-1',
          share_token: shareToken,
        }),
      ).toBe(true);
    },
  );
});
