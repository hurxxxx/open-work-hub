export const REALTIME_WS_PATH = '/api/v1/realtime/ws';

export const REALTIME_CLIENT_EVENT_TYPES = {
  auth: 'auth',
  subscribe: 'subscribe',
  unsubscribe: 'unsubscribe',
} as const;

export const REALTIME_SERVER_EVENT_TYPES = {
  authOk: 'realtime.auth.ok',
  keepalive: 'realtime.keepalive',
} as const;

type RealtimeTopicDescriptor<TTopic extends string> = {
  readonly topic: TTopic;
  readonly eventType: <TEventName extends string>(
    eventName: TEventName,
  ) => `${TTopic}.${TEventName}`;
  readonly isKey: (value: unknown) => value is string;
};

function createRealtimeTopicDescriptor<const TTopic extends string>(
  topic: TTopic,
): RealtimeTopicDescriptor<TTopic> {
  return {
    topic,
    eventType: <TEventName extends string>(
      eventName: TEventName,
    ): `${TTopic}.${TEventName}` =>
      `${topic}.${eventName}` as `${TTopic}.${TEventName}`,
    isKey: (value: unknown): value is string =>
      typeof value === 'string' && value.length > 0,
  };
}

const DOCS_PAGES_REALTIME = createRealtimeTopicDescriptor('docs.pages');
const WHITEBOARD_ACCESS_REALTIME =
  createRealtimeTopicDescriptor('whiteboard.access');

export const REALTIME_TOPICS = {
  docsPages: DOCS_PAGES_REALTIME.topic,
  whiteboardAccess: WHITEBOARD_ACCESS_REALTIME.topic,
} as const;

export const REALTIME_TOPIC_EVENT_TYPES = {
  docsPagesChanged: DOCS_PAGES_REALTIME.eventType('changed'),
  docsPagesSnapshot: DOCS_PAGES_REALTIME.eventType('snapshot'),
  docsAccessChanged: 'docs.access.changed',
  whiteboardAccessChanged: WHITEBOARD_ACCESS_REALTIME.eventType('changed'),
} as const;

export type RealtimeClientEventType =
  (typeof REALTIME_CLIENT_EVENT_TYPES)[keyof typeof REALTIME_CLIENT_EVENT_TYPES];

export type RealtimeServerEventType =
  (typeof REALTIME_SERVER_EVENT_TYPES)[keyof typeof REALTIME_SERVER_EVENT_TYPES];

export type RealtimeTopic =
  (typeof REALTIME_TOPICS)[keyof typeof REALTIME_TOPICS];

export type RealtimeTopicEventType =
  (typeof REALTIME_TOPIC_EVENT_TYPES)[keyof typeof REALTIME_TOPIC_EVENT_TYPES];

export type DocsPagesRealtimeSubscriptionMessage = {
  type: typeof REALTIME_CLIENT_EVENT_TYPES.subscribe;
  topic: typeof REALTIME_TOPICS.docsPages;
  key: string;
  share_token?: string | null;
};

export type DocsPagesRealtimeSubscriptionInput = {
  key: string;
  shareToken?: string | null;
};

export function createDocsPagesRealtimeSubscriptionMessage({
  key,
  shareToken = null,
}: DocsPagesRealtimeSubscriptionInput): DocsPagesRealtimeSubscriptionMessage {
  return {
    type: REALTIME_CLIENT_EVENT_TYPES.subscribe,
    topic: DOCS_PAGES_REALTIME.topic,
    key,
    share_token: shareToken,
  };
}

export function isDocsPagesRealtimeSubscriptionMessage(
  value: unknown,
): value is DocsPagesRealtimeSubscriptionMessage {
  if (!value || typeof value !== 'object') {
    return false;
  }
  const record = value as Record<string, unknown>;
  return (
    record.type === REALTIME_CLIENT_EVENT_TYPES.subscribe &&
    record.topic === DOCS_PAGES_REALTIME.topic &&
    DOCS_PAGES_REALTIME.isKey(record.key) &&
    isOptionalShareToken(record.share_token)
  );
}

export type WhiteboardAccessRealtimeSubscriptionMessage = {
  type: typeof REALTIME_CLIENT_EVENT_TYPES.subscribe;
  topic: typeof REALTIME_TOPICS.whiteboardAccess;
  key: string;
  share_token?: string | null;
};

export type WhiteboardAccessRealtimeSubscriptionInput = {
  key: string;
  shareToken?: string | null;
};

export function createWhiteboardAccessRealtimeSubscriptionMessage({
  key,
  shareToken = null,
}: WhiteboardAccessRealtimeSubscriptionInput): WhiteboardAccessRealtimeSubscriptionMessage {
  return {
    type: REALTIME_CLIENT_EVENT_TYPES.subscribe,
    topic: WHITEBOARD_ACCESS_REALTIME.topic,
    key,
    share_token: shareToken,
  };
}

export function isWhiteboardAccessRealtimeSubscriptionMessage(
  value: unknown,
): value is WhiteboardAccessRealtimeSubscriptionMessage {
  if (!value || typeof value !== 'object') return false;
  const record = value as Record<string, unknown>;
  return (
    record.type === REALTIME_CLIENT_EVENT_TYPES.subscribe &&
    record.topic === WHITEBOARD_ACCESS_REALTIME.topic &&
    WHITEBOARD_ACCESS_REALTIME.isKey(record.key) &&
    isOptionalShareToken(record.share_token)
  );
}

function isOptionalShareToken(value: unknown): boolean {
  return (
    value === undefined ||
    value === null ||
    (typeof value === 'string' && value.length > 0)
  );
}

export function resolveRealtimeWebSocketUrl(baseUrl: string | URL): string {
  const url = new URL(REALTIME_WS_PATH, baseUrl);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return url.toString();
}
