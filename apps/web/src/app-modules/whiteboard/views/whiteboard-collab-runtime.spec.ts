import { describe, expect, it } from 'vitest';

import type { WhiteboardScene } from '../api/whiteboard-api';
import {
  createWhiteboardCollabDocumentState,
  createWhiteboardCollabProvider,
  encodeWhiteboardCollabDocumentState,
} from './whiteboard-collab-runtime';

function scene(id: string): WhiteboardScene {
  return {
    elements: [{ id, type: 'rectangle', version: 1 }],
    appState: { gridModeEnabled: id === 'grid' },
    files: {},
  };
}

function elementIds(value: WhiteboardScene): string[] {
  return value.elements.map((item) =>
    item && typeof item === 'object'
      ? String((item as { id?: unknown }).id ?? '')
      : '',
  );
}

describe('whiteboard collab runtime', () => {
  it('starts from snapshot scene and migrates it into collab maps', () => {
    const state = createWhiteboardCollabDocumentState({
      seedScene: scene('seed'),
      session: {
        snapshot_scene: scene('snapshot'),
        yjs_state: null,
      },
    });

    expect(elementIds(state.initialScene)).toEqual(['snapshot']);
    expect(state.maps.elementOrder.toArray()).toEqual(['snapshot']);
    expect(state.initialSignature).toBeTypeOf('string');
  });

  it('uses seed scene when no snapshot or encoded state exists', () => {
    const state = createWhiteboardCollabDocumentState({
      seedScene: scene('seed'),
      session: {
        snapshot_scene: null,
        yjs_state: null,
      },
    });

    expect(elementIds(state.initialScene)).toEqual(['seed']);
  });

  it('prefers encoded element state over stale snapshots', () => {
    const existing = createWhiteboardCollabDocumentState({
      seedScene: scene('encoded'),
      session: {
        snapshot_scene: null,
        yjs_state: null,
      },
    });

    const restored = createWhiteboardCollabDocumentState({
      seedScene: scene('seed'),
      session: {
        snapshot_scene: scene('snapshot'),
        yjs_state: encodeWhiteboardCollabDocumentState(existing.doc),
      },
    });

    expect(elementIds(restored.initialScene)).toEqual(['encoded']);
  });
  it('uses the shared auth-first provider without putting credentials into its URL', () => {
    const state = createWhiteboardCollabDocumentState({
      seedScene: scene('seed'),
      session: { snapshot_scene: null, yjs_state: null },
    });
    const provider = createWhiteboardCollabProvider({
      doc: state.doc,
      roomKey: 'test-room',
      token: 'private-test-token',
      wsPath: '/api/v1/whiteboard/collab',
    });
    expect(provider.url).not.toContain('private-test-token');
    expect(provider.params).toEqual({});
    expect(provider.shouldConnect).toBe(false);
    expect(provider.disableBc).toBe(true);
    provider.destroy();
    state.doc.destroy();
  });
});
