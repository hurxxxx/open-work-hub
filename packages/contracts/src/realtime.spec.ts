import { describe, expect, it } from 'vitest';

import {
  REALTIME_CLIENT_EVENT_TYPES,
  REALTIME_SERVER_EVENT_TYPES,
  REALTIME_TOPICS,
  REALTIME_TOPIC_EVENT_TYPES,
  REALTIME_WS_PATH,
  createDocsPagesRealtimeSubscriptionMessage,
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
    });
    expect(REALTIME_TOPIC_EVENT_TYPES).toEqual({
      docsPagesChanged: 'docs.pages.changed',
      docsPagesSnapshot: 'docs.pages.snapshot',
    });
  });

  it('resolves websocket URLs from HTTP origins', () => {
    expect(resolveRealtimeWebSocketUrl('http://127.0.0.1:4200')).toBe(
      'ws://127.0.0.1:4200/api/v1/realtime/ws',
    );
    expect(resolveRealtimeWebSocketUrl('https://workspace.example.test')).toBe(
      'wss://workspace.example.test/api/v1/realtime/ws',
    );
  });

  it('builds and validates docs pages subscription messages', () => {
    const message = createDocsPagesRealtimeSubscriptionMessage({
      key: 'doc-1',
      workspaceSlug: 'hq',
      shareToken: 'share-1',
    });

    expect(message).toEqual({
      type: REALTIME_CLIENT_EVENT_TYPES.subscribe,
      topic: REALTIME_TOPICS.docsPages,
      key: 'doc-1',
      workspace_slug: 'hq',
      share_token: 'share-1',
    });
    expect(isDocsPagesRealtimeSubscriptionMessage(message)).toBe(true);
    expect(isDocsPagesRealtimeSubscriptionMessage({
      ...message,
      key: '',
    })).toBe(false);
    expect(isDocsPagesRealtimeSubscriptionMessage({
      ...message,
      topic: 'dm.conversations',
    })).toBe(false);
  });
});
