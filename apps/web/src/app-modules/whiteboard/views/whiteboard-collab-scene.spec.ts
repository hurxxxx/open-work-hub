import { describe, expect, it } from 'vitest';
import * as Y from 'yjs';

import type { WhiteboardScene } from '../api/whiteboard-api';
import {
  buildCollabSceneFromMaps,
  sceneForPersistence,
  sceneSignature,
  selectedElementCount,
  shouldAcceptElementUpdate,
  writeCollabSceneToMaps,
  type WhiteboardCollabSceneMaps,
  type WhiteboardElement,
} from './whiteboard-collab-scene';

function element(
  id: string,
  overrides: Partial<WhiteboardElement> = {},
): WhiteboardElement {
  return {
    id,
    type: 'rectangle',
    version: 1,
    versionNonce: 1,
    updated: 1,
    ...overrides,
  };
}

function createMaps(): WhiteboardCollabSceneMaps {
  const doc = new Y.Doc();
  return {
    elementsMap: doc.getMap<unknown>('whiteboard-elements'),
    elementOrder: doc.getArray<string>('whiteboard-element-order'),
    filesMap: doc.getMap<unknown>('whiteboard-files'),
    appStateMap: doc.getMap<unknown>('whiteboard-app-state'),
  };
}

function elementIds(scene: WhiteboardScene): string[] {
  return scene.elements.map((item) => (item as WhiteboardElement).id ?? '');
}

describe('whiteboard collab scene model', () => {
  it('builds stable signatures and strips transient app state', () => {
    const left: WhiteboardScene = {
      elements: [element('a', { customData: { z: 2, a: 1 } })],
      appState: {
        currentItemStrokeColor: '#111',
        gridModeEnabled: true,
      },
      files: {
        file: { dataURL: 'data:image/png;base64,a', mimeType: 'image/png' },
      },
    };
    const right: WhiteboardScene = {
      files: {
        file: { mimeType: 'image/png', dataURL: 'data:image/png;base64,a' },
      },
      appState: {
        gridModeEnabled: true,
        currentItemStrokeColor: '#222',
      },
      elements: [element('a', { customData: { a: 1, z: 2 } })],
    };

    expect(sceneSignature(left)).toBe(sceneSignature(right));
    expect(sceneForPersistence(left).appState).toEqual({
      gridModeEnabled: true,
    });
  });

  it('orders element updates by version, updated time, and nonce', () => {
    const current = element('a', {
      version: 2,
      updated: 20,
      versionNonce: 20,
    });

    expect(
      shouldAcceptElementUpdate(
        element('a', { version: 3, updated: 1, versionNonce: 1 }),
        current,
      ),
    ).toBe(true);
    expect(
      shouldAcceptElementUpdate(
        element('a', { version: 1, updated: 99, versionNonce: 99 }),
        current,
      ),
    ).toBe(false);
    expect(
      shouldAcceptElementUpdate(
        element('a', { version: 2, updated: 21, versionNonce: 1 }),
        current,
      ),
    ).toBe(true);
    expect(
      shouldAcceptElementUpdate(
        element('a', { version: 2, updated: 20, versionNonce: 21 }),
        current,
      ),
    ).toBe(true);
  });

  it('writes unique element order and app state into collab maps', () => {
    const maps = createMaps();

    writeCollabSceneToMaps(maps, {
      elements: [
        element('a', { version: 1 }),
        element('b'),
        element('a', { version: 2 }),
      ],
      appState: { gridModeEnabled: true, viewBackgroundColor: '#fff' },
      files: { image: { id: 'image', dataURL: 'data:image/png;base64,a' } },
    });

    expect(maps.elementOrder.toArray()).toEqual(['a', 'b']);
    expect(maps.elementsMap.get('a')).toMatchObject({ version: 2 });
    expect(maps.filesMap.get('image')).toMatchObject({ id: 'image' });
    expect(maps.appStateMap.get('gridModeEnabled')).toBe(true);
  });

  it('reads ordered map elements and appends orphan entries once', () => {
    const maps = createMaps();
    writeCollabSceneToMaps(maps, {
      elements: [element('b'), element('a')],
      appState: { gridModeEnabled: true },
      files: {},
    });
    maps.elementsMap.set('orphan', element('orphan'));
    maps.elementOrder.insert(0, ['b']);

    const scene = buildCollabSceneFromMaps(maps);

    expect(elementIds(scene)).toEqual(['b', 'a', 'orphan']);
  });

  it('counts only selected live elements', () => {
    expect(
      selectedElementCount(
        [
          element('a'),
          element('b', { isDeleted: true }),
          { type: 'anonymous' },
        ],
        { a: true, b: true, c: true },
      ),
    ).toBe(1);
  });
});
