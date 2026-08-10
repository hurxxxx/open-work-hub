import {
  getWhiteboard,
  normalizeWhiteboardScene,
  type WhiteboardHubItem,
  type WhiteboardScene,
} from '../api/whiteboard-api';
import { WHITEBOARD_PREVIEW_BACKGROUND_COLOR } from './whiteboard-colors';

export type WhiteboardPreviewStatus =
  | 'idle'
  | 'loading'
  | 'ready'
  | 'empty'
  | 'error';

export interface WhiteboardPreviewState {
  sourceKey: string;
  status: WhiteboardPreviewStatus;
  previewUrl: string | null;
}

export type WhiteboardPreviewAction =
  | { type: 'previewVisible'; sourceKey: string }
  | { type: 'previewLoaded'; sourceKey: string; previewUrl: string | null }
  | { type: 'previewFailed'; sourceKey: string };

export interface WhiteboardPreviewLoader {
  load(
    token: string,
    item: WhiteboardHubItem,
    workspaceSlug?: string | null,
  ): Promise<string | null>;
}

export interface CreateWhiteboardPreviewLoaderOptions {
  fetchWhiteboard: typeof getWhiteboard;
  renderScenePreview: (scene: WhiteboardScene) => Promise<string | null>;
  cacheKey?: (item: Pick<WhiteboardHubItem, 'id' | 'updated_at'>) => string;
}

export function getWhiteboardPreviewSourceKey(
  item: Pick<WhiteboardHubItem, 'id' | 'updated_at'>,
): string {
  return `${item.id}:${item.updated_at}`;
}

export function createWhiteboardPreviewState(
  sourceKey: string,
): WhiteboardPreviewState {
  return {
    sourceKey,
    status: 'idle',
    previewUrl: null,
  };
}

export function whiteboardPreviewReducer(
  state: WhiteboardPreviewState,
  action: WhiteboardPreviewAction,
): WhiteboardPreviewState {
  const currentState =
    state.sourceKey === action.sourceKey
      ? state
      : createWhiteboardPreviewState(action.sourceKey);

  switch (action.type) {
    case 'previewVisible':
      return currentState.status === 'idle'
        ? { ...currentState, status: 'loading' }
        : currentState;
    case 'previewLoaded':
      return {
        ...currentState,
        status: action.previewUrl ? 'ready' : 'empty',
        previewUrl: action.previewUrl,
      };
    case 'previewFailed':
      return {
        ...currentState,
        status: 'error',
        previewUrl: null,
      };
    default:
      return currentState;
  }
}

function isDeletedElement(element: unknown): boolean {
  return Boolean(
    element &&
      typeof element === 'object' &&
      (element as { isDeleted?: unknown }).isDeleted,
  );
}

export async function renderWhiteboardScenePreview(
  scene: WhiteboardScene,
): Promise<string | null> {
  const normalized = normalizeWhiteboardScene(scene);
  const elements = normalized.elements.filter(
    (element) => !isDeletedElement(element),
  );
  if (elements.length === 0) return null;

  const { exportToBlob } = await import('@excalidraw/excalidraw');
  const blob = await exportToBlob({
    elements: elements as never,
    appState: {
      ...normalized.appState,
      exportBackground: true,
      viewBackgroundColor: WHITEBOARD_PREVIEW_BACKGROUND_COLOR,
    } as never,
    files: normalized.files as never,
    mimeType: 'image/png',
    exportPadding: 32,
    maxWidthOrHeight: 720,
  });
  return URL.createObjectURL(blob);
}

export function createWhiteboardPreviewLoader(
  options: CreateWhiteboardPreviewLoaderOptions,
): WhiteboardPreviewLoader {
  const previewCache = new Map<string, string | null>();
  const previewPromiseCache = new Map<string, Promise<string | null>>();
  const cacheKey = options.cacheKey ?? getWhiteboardPreviewSourceKey;

  return {
    load(token, item, workspaceSlug) {
      const key = cacheKey(item);
      if (previewCache.has(key)) {
        return Promise.resolve(previewCache.get(key) ?? null);
      }

      const existing = previewPromiseCache.get(key);
      if (existing) return existing;

      const promise = options
        .fetchWhiteboard(token, item.id, workspaceSlug)
        .then((detail) => options.renderScenePreview(detail.scene))
        .then((url) => {
          previewCache.set(key, url);
          return url;
        })
        .finally(() => {
          previewPromiseCache.delete(key);
        });

      previewPromiseCache.set(key, promise);
      return promise;
    },
  };
}

export const whiteboardPreviewLoader = createWhiteboardPreviewLoader({
  fetchWhiteboard: getWhiteboard,
  renderScenePreview: renderWhiteboardScenePreview,
});
