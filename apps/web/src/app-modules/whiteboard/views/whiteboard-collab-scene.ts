import type { ExcalidrawProps } from '@excalidraw/excalidraw/types';
import type * as Y from 'yjs';

import {
  normalizeWhiteboardScene,
  type WhiteboardScene,
} from '../api/whiteboard-api';

type ExcalidrawOnChange = NonNullable<ExcalidrawProps['onChange']>;
type ExcalidrawSceneSerializer = (
  elements: Parameters<ExcalidrawOnChange>[0],
  appState: Parameters<ExcalidrawOnChange>[1],
  files: Parameters<ExcalidrawOnChange>[2],
) => string;

const PERSISTED_APP_STATE_KEYS = new Set([
  'gridModeEnabled',
  'gridSize',
  'viewBackgroundColor',
]);

export type WhiteboardElement = Record<string, unknown> & {
  id?: string;
  version?: number;
  versionNonce?: number;
  updated?: number;
  isDeleted?: boolean;
};

export type WhiteboardCollabSceneMaps = {
  elementsMap: Y.Map<unknown>;
  elementOrder: Y.Array<string>;
  filesMap: Y.Map<unknown>;
  appStateMap: Y.Map<unknown>;
};

export function sceneFromExcalidraw(
  elements: Parameters<ExcalidrawOnChange>[0],
  appState: Parameters<ExcalidrawOnChange>[1],
  files: Parameters<ExcalidrawOnChange>[2],
  serializeScene: ExcalidrawSceneSerializer,
): WhiteboardScene {
  const serialized = normalizeWhiteboardScene(
    JSON.parse(serializeScene(elements, appState, files)),
  );
  return sceneForPersistence({
    elements: cloneCollabValue([...elements]),
    appState: serialized.appState,
    files: serialized.files,
  });
}

export function sceneSignature(scene: WhiteboardScene): string {
  return JSON.stringify(stableJsonValue(sceneForPersistence(scene)));
}

export function sceneForPersistence(scene: unknown): WhiteboardScene {
  const normalized = normalizeWhiteboardScene(scene);
  return {
    elements: normalized.elements,
    appState: appStateForPersistence(normalized.appState),
    files: normalized.files,
  };
}

export function selectedElementCount(
  elements: readonly unknown[],
  selectedElementIds: unknown,
): number {
  if (!selectedElementIds || typeof selectedElementIds !== 'object') return 0;
  let count = 0;
  for (const element of elements) {
    const id = elementId(element);
    if (!id) continue;
    if (
      (selectedElementIds as Record<string, unknown>)[id] === true &&
      !(element as WhiteboardElement).isDeleted
    ) {
      count += 1;
    }
  }
  return count;
}

export function shouldAcceptElementUpdate(
  next: WhiteboardElement,
  current: WhiteboardElement | undefined,
): boolean {
  if (!current) return true;
  const nextVersion = numericElementField(next, 'version');
  const currentVersion = numericElementField(current, 'version');
  if (nextVersion !== currentVersion) {
    return nextVersion > currentVersion;
  }
  const nextUpdated = numericElementField(next, 'updated');
  const currentUpdated = numericElementField(current, 'updated');
  if (nextUpdated !== currentUpdated) {
    return nextUpdated > currentUpdated;
  }
  const nextNonce = numericElementField(next, 'versionNonce');
  const currentNonce = numericElementField(current, 'versionNonce');
  if (nextNonce !== currentNonce) {
    return nextNonce > currentNonce;
  }
  return JSON.stringify(next) !== JSON.stringify(current);
}

export function buildCollabSceneFromMaps({
  elementsMap,
  elementOrder,
  filesMap,
  appStateMap,
}: WhiteboardCollabSceneMaps): WhiteboardScene {
  const elements: unknown[] = [];
  const seen = new Set<string>();
  for (const id of elementOrder.toArray()) {
    if (seen.has(id)) continue;
    const element = elementsMap.get(id);
    if (element) {
      elements.push(cloneCollabValue(element));
      seen.add(id);
    }
  }
  elementsMap.forEach((element, id) => {
    if (!seen.has(id)) {
      elements.push(cloneCollabValue(element));
    }
  });
  return normalizeWhiteboardScene({
    elements,
    appState: objectFromYMap(appStateMap),
    files: objectFromYMap(filesMap),
  });
}

export function writeCollabSceneToMaps(
  { elementsMap, elementOrder, filesMap, appStateMap }: WhiteboardCollabSceneMaps,
  scene: WhiteboardScene,
): void {
  const normalized = normalizeWhiteboardScene(scene);
  const elements = normalized.elements as WhiteboardElement[];
  const order = uniqueElementOrder(elements);

  for (const element of elements) {
    const id = elementId(element);
    if (!id) continue;
    const current = elementsMap.get(id) as WhiteboardElement | undefined;
    if (shouldAcceptElementUpdate(element, current)) {
      elementsMap.set(id, cloneCollabElement(element));
    }
  }
  elementOrder.delete(0, elementOrder.length);
  elementOrder.insert(0, order);

  filesMap.clear();
  Object.entries(normalized.files).forEach(([key, value]) => {
    filesMap.set(key, cloneCollabValue(value));
  });

  appStateMap.clear();
  Object.entries(normalized.appState).forEach(([key, value]) => {
    appStateMap.set(key, cloneCollabValue(value));
  });
}

function cloneCollabValue<T>(value: T): T {
  if (value === undefined || value === null) {
    return value;
  }
  return JSON.parse(JSON.stringify(value)) as T;
}

function stableJsonValue(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(stableJsonValue);
  }
  if (!value || typeof value !== 'object') {
    return value;
  }
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>)
      .filter(([, entry]) => entry !== undefined)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, entry]) => [key, stableJsonValue(entry)]),
  );
}

function appStateForPersistence(
  appState: Record<string, unknown>,
): Record<string, unknown> {
  const persisted: Record<string, unknown> = {};
  for (const key of PERSISTED_APP_STATE_KEYS) {
    if (appState[key] !== undefined) {
      persisted[key] = appState[key];
    }
  }
  return persisted;
}

function cloneCollabElement(element: WhiteboardElement): WhiteboardElement {
  return cloneCollabValue(element);
}

function uniqueElementOrder(elements: readonly unknown[]): string[] {
  const order: string[] = [];
  const seen = new Set<string>();
  for (const element of elements) {
    const id = elementId(element);
    if (!id || seen.has(id)) continue;
    seen.add(id);
    order.push(id);
  }
  return order;
}

export function elementId(element: unknown): string | null {
  if (!element || typeof element !== 'object') return null;
  const id = (element as WhiteboardElement).id;
  return typeof id === 'string' && id ? id : null;
}

function numericElementField(
  element: WhiteboardElement | undefined,
  key: 'updated' | 'version' | 'versionNonce',
): number {
  const value = element?.[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

function objectFromYMap(map: Y.Map<unknown>): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  map.forEach((value, key) => {
    result[key] = cloneCollabValue(value);
  });
  return result;
}
