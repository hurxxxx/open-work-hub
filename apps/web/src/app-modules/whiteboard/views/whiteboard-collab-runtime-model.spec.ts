import { describe, expect, it } from 'vitest';

import {
  buildWhiteboardCollaborators,
  createWhiteboardAwarenessUser,
  normalizeWhiteboardSelectedElementIds,
  resolveWhiteboardCollabStatus,
  resolveWhiteboardConnectionCloseStatus,
  resolveWhiteboardProviderStatus,
} from './whiteboard-collab-runtime-model';

describe('whiteboard collab runtime model', () => {
  it('resolves effective collaboration status for the active board', () => {
    expect(
      resolveWhiteboardCollabStatus({
        boardId: null,
        snapshot: { boardId: 'board-1', status: 'connected' },
      }),
    ).toBeNull();
    expect(
      resolveWhiteboardCollabStatus({
        boardId: 'board-1',
        snapshot: null,
      }),
    ).toBe('connecting');
    expect(
      resolveWhiteboardCollabStatus({
        boardId: 'board-1',
        snapshot: { boardId: 'board-2', status: 'connected' },
      }),
    ).toBe('connecting');
    expect(
      resolveWhiteboardCollabStatus({
        boardId: 'board-1',
        snapshot: { boardId: 'board-1', status: 'connected' },
      }),
    ).toBe('connected');
  });

  it('maps provider status and close codes to collab status', () => {
    expect(resolveWhiteboardProviderStatus('connected')).toBe('connected');
    expect(resolveWhiteboardProviderStatus('connecting')).toBe('connecting');
    expect(resolveWhiteboardProviderStatus('disconnected')).toBe('offline');
    expect(resolveWhiteboardProviderStatus('unknown')).toBeNull();

    expect(resolveWhiteboardConnectionCloseStatus(4403)).toBe('error');
    expect(resolveWhiteboardConnectionCloseStatus(1011)).toBe('offline');
    expect(resolveWhiteboardConnectionCloseStatus(1013)).toBe('offline');
    expect(resolveWhiteboardConnectionCloseStatus(1000)).toBeNull();
  });

  it('normalizes local awareness fields', () => {
    const user = createWhiteboardAwarenessUser({
      id: 'user-1',
      fullName: 'A User',
    });

    expect(user).toMatchObject({
      id: 'user-1',
      fullName: 'A User',
    });
    expect(user.color).toMatch(/^#/);
    expect(normalizeWhiteboardSelectedElementIds({ a: true })).toEqual({
      a: true,
    });
    expect(normalizeWhiteboardSelectedElementIds(null)).toEqual({});
  });

  it('projects awareness states into Excalidraw collaborators', () => {
    const collaborators = buildWhiteboardCollaborators({
      localClientId: 1,
      states: new Map<number, unknown>([
        [
          1,
          {
            user: {
              id: 'local',
              fullName: 'Local',
              color: '#111111',
            },
          },
        ],
        [
          2,
          {
            user: {
              id: 'remote',
              fullName: 'Remote User',
              color: '#222222',
            },
            cursor: { x: 10, y: 20, tool: 'pointer' },
            button: 'down',
            selectedElementIds: { shape: true },
          },
        ],
      ]),
    });

    expect([...collaborators.keys()]).toEqual(['2']);
    expect(collaborators.get('2' as never)).toMatchObject({
      id: 'remote',
      username: 'Remote User',
      pointer: { x: 10, y: 20, tool: 'pointer' },
      button: 'down',
      selectedElementIds: { shape: true },
      color: {
        stroke: '#222222',
        background: '#222222',
      },
    });
  });
});
