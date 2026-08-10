import { ApiRequestError, apiFetchJson } from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';
import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

import {
  normalizeWhiteboardScene as normalizeWhiteboardSceneValue,
  type WhiteboardScene,
} from './whiteboard-scene-codec';
import {
  whiteboardApiRoutes,
  type WhiteboardHubRouteParams,
} from './whiteboard-routes';

export type { WhiteboardScene } from './whiteboard-scene-codec';
export type WhiteboardVisibility = 'personal' | 'workspace';

export class WhiteboardApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(
  path: string,
  token: string,
  init: RequestInit = {},
  workspaceSlug?: string | null,
): Promise<T> {
  try {
    return await apiFetchJson<T>(
      rewriteWorkspaceApiPath(path, workspaceSlug),
      token,
      init,
    );
  } catch (error) {
    if (error instanceof ApiRequestError) {
      throw new WhiteboardApiError(error.status, error.message);
    }
    throw error;
  }
}

export type WhiteboardPrimaryTarget = ApiSchema<'WhiteboardPrimaryTarget'>;
export type WhiteboardTargetItem = ApiSchema<'WhiteboardTargetItem'>;
export type WhiteboardHubItem = Omit<
  ApiSchema<'WhiteboardHubItem'>,
  | 'targets'
  | 'last_viewed_at'
  | 'primary_target'
  | 'source_deeplink'
  | 'source_ref'
  | 'trashed_at'
> & {
  source_ref: string | null;
  primary_target: WhiteboardPrimaryTarget | null;
  targets: WhiteboardTargetItem[];
  source_deeplink: string | null;
  trashed_at: string | null;
  last_viewed_at: string | null;
};
export type WhiteboardDetail = WhiteboardHubItem &
  Omit<ApiSchema<'WhiteboardDetail'>, keyof WhiteboardHubItem | 'scene'> & {
    scene: WhiteboardScene;
  };
export type WhiteboardHubResponse = Omit<
  ApiSchema<'WhiteboardHubResponse'>,
  'items'
> & {
  items: WhiteboardHubItem[];
};
export type WhiteboardContextSlotResponse = Omit<
  ApiSchema<'WhiteboardContextSlotResponse'>,
  'item'
> & {
  item: WhiteboardDetail | null;
};
export type ShareableUserItem = ApiSchema<'ShareableUserItem'>;
export type WhiteboardUserShareItem = ApiSchema<'WhiteboardUserShareItem'>;
export type WhiteboardLinkShareItem = ApiSchema<'WhiteboardLinkShareItem'>;
export type WhiteboardSharingResponse = ApiSchema<'WhiteboardSharingResponse'>;
export type ResolveWhiteboardSharedLinkResponse = Omit<
  ApiSchema<'ResolveWhiteboardSharedLinkResponse'>,
  'item'
> & {
  item: WhiteboardHubItem;
};
export type WhiteboardCollabSession = Omit<
  ApiSchema<'WhiteboardCollabSessionResponse'>,
  'read_only_reason' | 'snapshot_scene' | 'yjs_state'
> & {
  read_only_reason: 'relay_unavailable' | 'permission_revoked' | null;
  snapshot_scene: WhiteboardScene | null;
  yjs_state: string | null;
};
export type WhiteboardCollabSnapshotResponse =
  ApiSchema<'WhiteboardCollabSnapshotResponse'>;

export function normalizeWhiteboardScene(value: unknown): WhiteboardScene {
  return normalizeWhiteboardSceneValue(value);
}

export function listWhiteboardHub(
  token: string,
  params: WhiteboardHubRouteParams = {},
  workspaceSlug?: string | null,
): Promise<WhiteboardHubResponse> {
  return request<WhiteboardHubResponse>(
    whiteboardApiRoutes.hub(params),
    token,
    {},
    workspaceSlug,
  );
}

export function createWhiteboard(
  token: string,
  payload: {
    title: string;
    scene?: WhiteboardScene | null;
    source_app?: string;
    source_kind?: string;
    source_ref?: string | null;
    generation_kind?: string;
    primary_target?: {
      app: string;
      type: string;
      id: string;
      sort_order?: number;
    } | null;
  },
  workspaceSlug?: string | null,
): Promise<WhiteboardDetail> {
  return request<WhiteboardDetail>(
    whiteboardApiRoutes.items(),
    token,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
    workspaceSlug,
  );
}

export function getWhiteboard(
  token: string,
  itemId: string,
  workspaceSlug?: string | null,
): Promise<WhiteboardDetail> {
  return request<WhiteboardDetail>(
    whiteboardApiRoutes.item(itemId),
    token,
    {},
    workspaceSlug,
  );
}

export function getSharedWhiteboard(
  token: string,
  shareToken: string,
): Promise<WhiteboardDetail> {
  return request<WhiteboardDetail>(
    whiteboardApiRoutes.sharedLinkItem(shareToken),
    token,
  );
}

export function updateWhiteboard(
  token: string,
  itemId: string,
  payload: {
    title?: string;
    scene?: WhiteboardScene | null;
  },
  workspaceSlug?: string | null,
): Promise<WhiteboardDetail> {
  return request<WhiteboardDetail>(
    whiteboardApiRoutes.item(itemId),
    token,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
    workspaceSlug,
  );
}

export function updateSharedWhiteboard(
  token: string,
  shareToken: string,
  payload: {
    title?: string;
    scene?: WhiteboardScene | null;
  },
): Promise<WhiteboardDetail> {
  return request<WhiteboardDetail>(
    whiteboardApiRoutes.sharedLinkItem(shareToken),
    token,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  );
}

export function getWhiteboardCollabSession(
  token: string,
  itemId: string,
  workspaceSlug?: string | null,
): Promise<WhiteboardCollabSession> {
  return request<WhiteboardCollabSession>(
    whiteboardApiRoutes.collabSession(itemId),
    token,
    {},
    workspaceSlug,
  );
}

export function saveWhiteboardCollabSnapshot(
  token: string,
  itemId: string,
  payload: {
    scene?: WhiteboardScene | null;
    yjs_state?: string | null;
  },
  workspaceSlug?: string | null,
): Promise<WhiteboardCollabSnapshotResponse> {
  return request<WhiteboardCollabSnapshotResponse>(
    whiteboardApiRoutes.collabSnapshot(itemId),
    token,
    {
      method: 'PUT',
      body: JSON.stringify(payload),
    },
    workspaceSlug,
  );
}

export function deleteWhiteboard(
  token: string,
  itemId: string,
  workspaceSlug?: string | null,
): Promise<void> {
  return request<void>(
    whiteboardApiRoutes.item(itemId),
    token,
    { method: 'DELETE' },
    workspaceSlug,
  );
}

export function restoreWhiteboard(
  token: string,
  itemId: string,
  workspaceSlug?: string | null,
): Promise<WhiteboardDetail> {
  return request<WhiteboardDetail>(
    whiteboardApiRoutes.itemRestore(itemId),
    token,
    { method: 'POST' },
    workspaceSlug,
  );
}

export function updateWhiteboardTarget(
  token: string,
  itemId: string,
  payload: {
    app: string;
    type: string;
    id: string;
    sort_order?: number;
  },
  workspaceSlug?: string | null,
): Promise<WhiteboardDetail> {
  return request<WhiteboardDetail>(
    whiteboardApiRoutes.itemTarget(itemId),
    token,
    {
      method: 'PUT',
      body: JSON.stringify(payload),
    },
    workspaceSlug,
  );
}

export function deleteWhiteboardTarget(
  token: string,
  itemId: string,
  workspaceSlug?: string | null,
): Promise<WhiteboardDetail> {
  return request<WhiteboardDetail>(
    whiteboardApiRoutes.itemTarget(itemId),
    token,
    { method: 'DELETE' },
    workspaceSlug,
  );
}

export function permanentlyDeleteWhiteboard(
  token: string,
  itemId: string,
  workspaceSlug?: string | null,
): Promise<void> {
  return request<void>(
    whiteboardApiRoutes.itemPermanent(itemId),
    token,
    { method: 'DELETE' },
    workspaceSlug,
  );
}

export function toggleWhiteboardFavorite(
  token: string,
  itemId: string,
  workspaceSlug?: string | null,
): Promise<{ is_favorite: boolean }> {
  return request<{ is_favorite: boolean }>(
    whiteboardApiRoutes.itemFavorite(itemId),
    token,
    { method: 'PATCH' },
    workspaceSlug,
  );
}

export function recordWhiteboardView(
  token: string,
  itemId: string,
  workspaceSlug?: string | null,
): Promise<void> {
  return request<void>(
    whiteboardApiRoutes.itemView(itemId),
    token,
    { method: 'POST' },
    workspaceSlug,
  );
}

export function recordSharedWhiteboardView(
  token: string,
  shareToken: string,
): Promise<void> {
  return request<void>(whiteboardApiRoutes.sharedLinkView(shareToken), token, {
    method: 'POST',
  });
}

export function getWhiteboardContextSlot(
  token: string,
  context: { app: string; type: string; id: string },
  workspaceSlug?: string | null,
): Promise<WhiteboardContextSlotResponse> {
  return request<WhiteboardContextSlotResponse>(
    whiteboardApiRoutes.contextSlot(context),
    token,
    {},
    workspaceSlug,
  );
}

export function createWhiteboardContextSlot(
  token: string,
  payload: { app: string; type: string; id: string; title?: string },
  workspaceSlug?: string | null,
): Promise<WhiteboardDetail> {
  return request<WhiteboardDetail>(
    whiteboardApiRoutes.contextSlot(),
    token,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
    workspaceSlug,
  );
}

export function attachWhiteboardContextSlot(
  token: string,
  payload: { app: string; type: string; id: string; whiteboard_id: string },
  workspaceSlug?: string | null,
): Promise<WhiteboardDetail> {
  return request<WhiteboardDetail>(
    whiteboardApiRoutes.contextSlot(),
    token,
    {
      method: 'PUT',
      body: JSON.stringify(payload),
    },
    workspaceSlug,
  );
}

export function detachWhiteboardContextSlot(
  token: string,
  context: { app: string; type: string; id: string },
  workspaceSlug?: string | null,
): Promise<void> {
  return request<void>(
    whiteboardApiRoutes.contextSlot(context),
    token,
    { method: 'DELETE' },
    workspaceSlug,
  );
}

export function listWhiteboardShareableUsers(
  token: string,
  q = '',
  workspaceSlug?: string | null,
): Promise<ShareableUserItem[]> {
  return request<ShareableUserItem[]>(
    whiteboardApiRoutes.shareableUsers(q),
    token,
    {},
    workspaceSlug,
  );
}

export function getWhiteboardSharing(
  token: string,
  itemId: string,
  workspaceSlug?: string | null,
): Promise<WhiteboardSharingResponse> {
  return request<WhiteboardSharingResponse>(
    whiteboardApiRoutes.sharing(itemId),
    token,
    {},
    workspaceSlug,
  );
}

export function upsertWhiteboardUserShare(
  token: string,
  itemId: string,
  userId: string,
  accessLevel: 'read' | 'edit',
  workspaceSlug?: string | null,
): Promise<WhiteboardSharingResponse> {
  return request<WhiteboardSharingResponse>(
    whiteboardApiRoutes.userShare(itemId, userId),
    token,
    {
      method: 'PUT',
      body: JSON.stringify({ access_level: accessLevel }),
    },
    workspaceSlug,
  );
}

export function deleteWhiteboardUserShare(
  token: string,
  itemId: string,
  userId: string,
  workspaceSlug?: string | null,
): Promise<WhiteboardSharingResponse> {
  return request<WhiteboardSharingResponse>(
    whiteboardApiRoutes.userShare(itemId, userId),
    token,
    { method: 'DELETE' },
    workspaceSlug,
  );
}

export function upsertWhiteboardLinkShare(
  token: string,
  itemId: string,
  payload: {
    access_level: 'read' | 'edit';
    active?: boolean;
    regenerate_token?: boolean;
  },
  workspaceSlug?: string | null,
): Promise<WhiteboardSharingResponse> {
  return request<WhiteboardSharingResponse>(
    whiteboardApiRoutes.linkShare(itemId),
    token,
    {
      method: 'PUT',
      body: JSON.stringify(payload),
    },
    workspaceSlug,
  );
}

export function deleteWhiteboardLinkShare(
  token: string,
  itemId: string,
  workspaceSlug?: string | null,
): Promise<WhiteboardSharingResponse> {
  return request<WhiteboardSharingResponse>(
    whiteboardApiRoutes.linkShare(itemId),
    token,
    { method: 'DELETE' },
    workspaceSlug,
  );
}

export function resolveWhiteboardSharedLink(
  token: string,
  shareToken: string,
): Promise<ResolveWhiteboardSharedLinkResponse> {
  return request<ResolveWhiteboardSharedLinkResponse>(
    whiteboardApiRoutes.sharedLink(shareToken),
    token,
  );
}
