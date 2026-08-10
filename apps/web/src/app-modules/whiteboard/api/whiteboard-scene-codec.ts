export interface WhiteboardScene {
  elements: unknown[];
  appState: Record<string, unknown>;
  files: Record<string, unknown>;
  [key: string]: unknown;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function sceneElementId(element: unknown): string | null {
  if (!isRecord(element)) return null;
  const id = element.id;
  return typeof id === 'string' && id ? id : null;
}

function compactSceneElements(elements: unknown[]): unknown[] {
  const orderedIds: string[] = [];
  const byId = new Map<string, unknown>();
  const anonymous: unknown[] = [];

  for (const element of elements) {
    const id = sceneElementId(element);
    if (!id) {
      anonymous.push(element);
      continue;
    }
    if (!byId.has(id)) {
      orderedIds.push(id);
    }
    byId.set(id, element);
  }

  const compacted: unknown[] = [];
  for (const id of orderedIds) {
    const element = byId.get(id);
    if (element !== undefined) {
      compacted.push(element);
    }
  }
  return [...compacted, ...anonymous];
}

export function normalizeWhiteboardScene(value: unknown): WhiteboardScene {
  if (!isRecord(value)) {
    return { elements: [], appState: {}, files: {} };
  }

  return {
    ...value,
    elements: compactSceneElements(
      Array.isArray(value.elements) ? value.elements : [],
    ),
    appState: isRecord(value.appState) ? value.appState : {},
    files: isRecord(value.files) ? value.files : {},
  };
}
