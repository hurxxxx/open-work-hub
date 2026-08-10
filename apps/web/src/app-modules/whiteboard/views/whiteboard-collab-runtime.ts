import { WebsocketProvider } from 'y-websocket';
import * as Y from 'yjs';

import {
  normalizeWhiteboardScene,
  type WhiteboardCollabSession,
  type WhiteboardScene,
} from '../api/whiteboard-api';
import {
  buildCollabSceneFromMaps,
  sceneSignature,
  writeCollabSceneToMaps,
  type WhiteboardCollabSceneMaps,
} from './whiteboard-collab-scene';
import {
  decodeBase64ToUint8Array,
  encodeUint8ArrayToBase64,
  toWebSocketUrl,
} from './whiteboard-editor-utils';

export const WHITEBOARD_LOCAL_COLLAB_ORIGIN = 'whiteboard-local-scene';
export const WHITEBOARD_REMOTE_APPLY_GUARD_MS = 32;

export type WhiteboardCollabDocument = Y.Doc;
export type WhiteboardCollabProvider = WebsocketProvider;

export interface WhiteboardCollabDocumentState {
  doc: WhiteboardCollabDocument;
  initialScene: WhiteboardScene;
  initialSignature: string;
  maps: WhiteboardCollabSceneMaps;
}

export function createWhiteboardCollabDocumentState({
  seedScene,
  session,
}: {
  seedScene: WhiteboardScene;
  session: Pick<WhiteboardCollabSession, 'snapshot_scene' | 'yjs_state'>;
}): WhiteboardCollabDocumentState {
  const doc = new Y.Doc();
  if (session.yjs_state) {
    Y.applyUpdate(doc, decodeBase64ToUint8Array(session.yjs_state));
  }

  const legacySceneMap = doc.getMap<WhiteboardScene>('whiteboard');
  const maps: WhiteboardCollabSceneMaps = {
    elementsMap: doc.getMap<unknown>('whiteboard-elements'),
    elementOrder: doc.getArray<string>('whiteboard-element-order'),
    filesMap: doc.getMap<unknown>('whiteboard-files'),
    appStateMap: doc.getMap<unknown>('whiteboard-app-state'),
  };

  const hasElementState =
    maps.elementsMap.size > 0 || maps.elementOrder.length > 0;
  const initialScene = hasElementState
    ? buildCollabSceneFromMaps(maps)
    : normalizeWhiteboardScene(
        legacySceneMap.get('scene') ?? session.snapshot_scene ?? seedScene,
      );
  if (!hasElementState) {
    doc.transact(() => {
      writeCollabSceneToMaps(maps, initialScene);
    }, WHITEBOARD_LOCAL_COLLAB_ORIGIN);
  }

  return {
    doc,
    initialScene,
    initialSignature: sceneSignature(initialScene),
    maps,
  };
}

export function createWhiteboardCollabProvider({
  doc,
  roomKey,
  token,
  wsPath,
}: {
  doc: WhiteboardCollabDocument;
  roomKey: string;
  token: string;
  wsPath: string;
}): WhiteboardCollabProvider {
  return new WebsocketProvider(toWebSocketUrl(wsPath), roomKey, doc, {
    connect: false,
    maxBackoffTime: 4000,
    params: { token },
  });
}

export function encodeWhiteboardCollabDocumentState(
  doc: WhiteboardCollabDocument,
): string {
  return encodeUint8ArrayToBase64(Y.encodeStateAsUpdate(doc));
}
