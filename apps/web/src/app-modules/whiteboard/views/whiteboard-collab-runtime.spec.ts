import { describe, expect, it } from 'vitest';

import type { WhiteboardScene } from '../api/whiteboard-api';
import {
  createWhiteboardCollabDocumentState,
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
});
