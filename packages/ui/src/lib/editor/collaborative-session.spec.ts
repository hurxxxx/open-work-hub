import { describe, expect, it } from 'vitest';

import {
  collaborativeSessionReducer,
  colorForCollaborativeUser,
  hashCollaborativeUserId,
  INITIAL_COLLABORATIVE_SESSION_STATE,
  resolveCollaborativeReadOnlyMessage,
  toCollaborativeWebSocketUrl,
  type CollaborativeSession,
} from './collaborative-session';

function session(
  overrides: Partial<CollaborativeSession> = {},
): CollaborativeSession {
  return {
    roomKey: 'room-1',
    wsPath: '/collab/room-1',
    user: {
      id: 'user-1',
      fullName: 'Ada Lovelace',
    },
    realtimeStatus: 'enabled',
    readOnlyReason: null,
    snapshotContent: [],
    yjsState: null,
    ...overrides,
  };
}

describe('collaborative session', () => {
  it('moves through loading, ready, and failed states', () => {
    const ready = collaborativeSessionReducer(
      INITIAL_COLLABORATIVE_SESSION_STATE,
      {
        type: 'ready',
        session: session(),
      },
    );

    expect(ready).toMatchObject({
      status: 'ready',
      error: null,
      session: { roomKey: 'room-1' },
    });
    expect(collaborativeSessionReducer(ready, { type: 'loading' })).toBe(
      INITIAL_COLLABORATIVE_SESSION_STATE,
    );
    expect(
      collaborativeSessionReducer(ready, {
        type: 'failed',
        error: 'Load failed',
      }),
    ).toEqual({
      status: 'failed',
      session: null,
      error: 'Load failed',
    });
  });

  it('assigns stable collaborative user colors', () => {
    expect(hashCollaborativeUserId('user-1')).toBe(
      hashCollaborativeUserId('user-1'),
    );
    expect(colorForCollaborativeUser('user-1')).toBe(
      colorForCollaborativeUser('user-1'),
    );
    expect(colorForCollaborativeUser('')).toBe('#0ea5e9');
  });

  it('converts websocket paths against the current origin', () => {
    expect(
      toCollaborativeWebSocketUrl('/collab/room-1', 'https://open-work-hub.local'),
    ).toBe('wss://open-work-hub.local/collab/room-1');
    expect(
      toCollaborativeWebSocketUrl('/collab/room-1', 'http://localhost:3000'),
    ).toBe('ws://localhost:3000/collab/room-1');
    expect(
      toCollaborativeWebSocketUrl(
        'wss://relay.example.test/ws',
        'https://open-work-hub.local',
      ),
    ).toBe('ws://relay.example.test/ws');
  });

  it('resolves read-only messages by reason', () => {
    const messages = {
      permissionRevoked: 'Permission revoked',
      relayUnavailable: 'Relay unavailable',
      tooManyConnections: 'Too many connections',
    };

    expect(
      resolveCollaborativeReadOnlyMessage('permission_revoked', messages),
    ).toBe('Permission revoked');
    expect(
      resolveCollaborativeReadOnlyMessage('relay_unavailable', messages),
    ).toBe('Relay unavailable');
    expect(
      resolveCollaborativeReadOnlyMessage('too_many_connections', messages),
    ).toBe('Too many connections');
    expect(resolveCollaborativeReadOnlyMessage(null, messages)).toBe(
      'Relay unavailable',
    );
  });
});
