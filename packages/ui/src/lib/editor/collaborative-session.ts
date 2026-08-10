import type { BlockContent } from './types';

export type CollaborativeReadOnlyReason =
  | 'relay_unavailable'
  | 'permission_revoked'
  | 'too_many_connections'
  | null;

export type CollaborativeSession = {
  roomKey: string;
  wsPath: string;
  user: {
    id: string;
    fullName: string;
  };
  realtimeStatus: 'enabled' | 'degraded';
  readOnlyReason: CollaborativeReadOnlyReason;
  snapshotContent: BlockContent | null;
  yjsState: string | null;
};

export type CollaborativeBlockEditorMessages = {
  permissionRevoked: string;
  relayUnavailable: string;
  tooManyConnections: string;
  startFailed: string;
  preparing: string;
};

export const COLLAB_CLOSE_CODE_TOO_MANY_CONNECTIONS = 4429;

type CollaborativeSessionState =
  | {
      status: 'loading';
      session: null;
      error: null;
    }
  | {
      status: 'ready';
      session: CollaborativeSession;
      error: null;
    }
  | {
      status: 'failed';
      session: null;
      error: string;
    };

type CollaborativeSessionAction =
  | {
      type: 'loading';
    }
  | {
      type: 'ready';
      session: CollaborativeSession;
    }
  | {
      type: 'failed';
      error: string;
    };

export const INITIAL_COLLABORATIVE_SESSION_STATE: CollaborativeSessionState = {
  status: 'loading',
  session: null,
  error: null,
};

const USER_COLORS = [
  '#0ea5e9',
  '#ef4444',
  '#10b981',
  '#f59e0b',
  '#8b5cf6',
  '#ec4899',
  '#14b8a6',
  '#f97316',
] as const;

export function collaborativeSessionReducer(
  _state: CollaborativeSessionState,
  action: CollaborativeSessionAction,
): CollaborativeSessionState {
  switch (action.type) {
    case 'loading':
      return INITIAL_COLLABORATIVE_SESSION_STATE;
    case 'ready':
      return {
        status: 'ready',
        session: action.session,
        error: null,
      };
    case 'failed':
      return {
        status: 'failed',
        session: null,
        error: action.error,
      };
  }
}

export function hashCollaborativeUserId(value: string): number {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash << 5) - hash + value.charCodeAt(index);
    hash |= 0;
  }
  return Math.abs(hash);
}

export function colorForCollaborativeUser(userId: string): string {
  return USER_COLORS[hashCollaborativeUserId(userId) % USER_COLORS.length];
}

export function toCollaborativeWebSocketUrl(
  wsPath: string,
  origin: string,
): string {
  const resolved = new URL(wsPath, origin);
  resolved.protocol = resolved.protocol === 'https:' ? 'wss:' : 'ws:';
  return resolved.toString();
}

export function resolveCollaborativeReadOnlyMessage(
  reason: CollaborativeReadOnlyReason,
  messages: Pick<
    CollaborativeBlockEditorMessages,
    'permissionRevoked' | 'relayUnavailable' | 'tooManyConnections'
  >,
): string {
  if (reason === 'permission_revoked') {
    return messages.permissionRevoked;
  }
  if (reason === 'too_many_connections') {
    return messages.tooManyConnections;
  }
  return messages.relayUnavailable;
}
