import { ApiRequestError, apiFetchJson } from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';

import {
  whiteboardApiRoutes,
  type WhiteboardHubRouteParams,
} from './whiteboard-routes';
import {
  normalizeWhiteboardScene as normalizeWhiteboardSceneValue,
  type WhiteboardScene,
} from './whiteboard-scene-codec';

export type { WhiteboardScene } from './whiteboard-scene-codec';
export type WhiteboardVisibility = 'personal' | 'company';

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
): Promise<T> {
  try {
    return await apiFetchJson<T>(path, token, init);
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
): Promise<WhiteboardHubResponse> {
  return request<WhiteboardHubResponse>(
    whiteboardApiRoutes.hub(params),
    token,
    {},
  );
}

export function createWhiteboard(
  token: string,
  payload: {
    title: string;
    company_visible?: boolean;
    company_admin_read_acknowledged?: boolean;
    scene?: WhiteboardScene | null;
    source_app?: string;
    source_kind?: string;
    source_ref?: string | null;
    generation_kind?: string;
    primary_target?: {
      company_admin_read_acknowledged?: boolean;
      app: string;
      type: string;
      id: string;
      sort_order?: number;
    } | null;
  },
): Promise<WhiteboardDetail> {
  return request<WhiteboardDetail>(whiteboardApiRoutes.items(), token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function getWhiteboard(
  token: string,
  itemId: string,
): Promise<WhiteboardDetail> {
  return request<WhiteboardDetail>(whiteboardApiRoutes.item(itemId), token, {});
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
): Promise<WhiteboardDetail> {
  return request<WhiteboardDetail>(whiteboardApiRoutes.item(itemId), token, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
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
): Promise<WhiteboardCollabSession> {
  return request<WhiteboardCollabSession>(
    whiteboardApiRoutes.collabSession(itemId),
    token,
    {},
  );
}

export function saveWhiteboardCollabSnapshot(
  token: string,
  itemId: string,
  payload: {
    scene?: WhiteboardScene | null;
    yjs_state?: string | null;
  },
): Promise<WhiteboardCollabSnapshotResponse> {
  return request<WhiteboardCollabSnapshotResponse>(
    whiteboardApiRoutes.collabSnapshot(itemId),
    token,
    {
      method: 'PUT',
      body: JSON.stringify(payload),
    },
  );
}

export function deleteWhiteboard(token: string, itemId: string): Promise<void> {
  return request<void>(whiteboardApiRoutes.item(itemId), token, {
    method: 'DELETE',
  });
}

export function restoreWhiteboard(
  token: string,
  itemId: string,
): Promise<WhiteboardDetail> {
  return request<WhiteboardDetail>(
    whiteboardApiRoutes.itemRestore(itemId),
    token,
    { method: 'POST' },
  );
}

export function updateWhiteboardTarget(
  token: string,
  itemId: string,
  payload: {
    company_admin_read_acknowledged?: boolean;
    app: string;
    type: string;
    id: string;
    sort_order?: number;
  },
): Promise<WhiteboardDetail> {
  return request<WhiteboardDetail>(
    whiteboardApiRoutes.itemTarget(itemId),
    token,
    {
      method: 'PUT',
      body: JSON.stringify(payload),
    },
  );
}

export function deleteWhiteboardTarget(
  token: string,
  itemId: string,
): Promise<WhiteboardDetail> {
  return request<WhiteboardDetail>(
    whiteboardApiRoutes.itemTarget(itemId),
    token,
    { method: 'DELETE' },
  );
}

export function permanentlyDeleteWhiteboard(
  token: string,
  itemId: string,
): Promise<void> {
  return request<void>(whiteboardApiRoutes.itemPermanent(itemId), token, {
    method: 'DELETE',
  });
}

export function toggleWhiteboardFavorite(
  token: string,
  itemId: string,
): Promise<{ is_favorite: boolean }> {
  return request<{ is_favorite: boolean }>(
    whiteboardApiRoutes.itemFavorite(itemId),
    token,
    { method: 'PATCH' },
  );
}

export function recordWhiteboardView(
  token: string,
  itemId: string,
): Promise<void> {
  return request<void>(whiteboardApiRoutes.itemView(itemId), token, {
    method: 'POST',
  });
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
): Promise<WhiteboardContextSlotResponse> {
  return request<WhiteboardContextSlotResponse>(
    whiteboardApiRoutes.contextSlot(context),
    token,
    {},
  );
}

export function createWhiteboardContextSlot(
  token: string,
  payload: { app: string; type: string; id: string; title?: string },
): Promise<WhiteboardDetail> {
  return request<WhiteboardDetail>(whiteboardApiRoutes.contextSlot(), token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function attachWhiteboardContextSlot(
  token: string,
  payload: { app: string; type: string; id: string; whiteboard_id: string },
): Promise<WhiteboardDetail> {
  return request<WhiteboardDetail>(whiteboardApiRoutes.contextSlot(), token, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export function detachWhiteboardContextSlot(
  token: string,
  context: { app: string; type: string; id: string },
): Promise<void> {
  return request<void>(whiteboardApiRoutes.contextSlot(context), token, {
    method: 'DELETE',
  });
}

export function listWhiteboardShareableUsers(
  token: string,
  q = '',
): Promise<ShareableUserItem[]> {
  return request<ShareableUserItem[]>(
    whiteboardApiRoutes.shareableUsers(q),
    token,
    {},
  );
}

export function getWhiteboardSharing(
  token: string,
  itemId: string,
): Promise<WhiteboardSharingResponse> {
  return request<WhiteboardSharingResponse>(
    whiteboardApiRoutes.sharing(itemId),
    token,
    {},
  );
}

export function upsertWhiteboardUserShare(
  token: string,
  itemId: string,
  userId: string,
  accessLevel: 'read' | 'edit',
): Promise<WhiteboardSharingResponse> {
  return request<WhiteboardSharingResponse>(
    whiteboardApiRoutes.userShare(itemId, userId),
    token,
    {
      method: 'PUT',
      body: JSON.stringify({ access_level: accessLevel }),
    },
  );
}

export function deleteWhiteboardUserShare(
  token: string,
  itemId: string,
  userId: string,
): Promise<WhiteboardSharingResponse> {
  return request<WhiteboardSharingResponse>(
    whiteboardApiRoutes.userShare(itemId, userId),
    token,
    { method: 'DELETE' },
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
): Promise<WhiteboardSharingResponse> {
  return request<WhiteboardSharingResponse>(
    whiteboardApiRoutes.linkShare(itemId),
    token,
    {
      method: 'PUT',
      body: JSON.stringify(payload),
    },
  );
}

export function deleteWhiteboardLinkShare(
  token: string,
  itemId: string,
): Promise<WhiteboardSharingResponse> {
  return request<WhiteboardSharingResponse>(
    whiteboardApiRoutes.linkShare(itemId),
    token,
    { method: 'DELETE' },
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

export async function updateWhiteboardCompanySharing(
  token: string,
  itemId: string,
  enabled: boolean,
  acknowledged: boolean,
): Promise<WhiteboardDetail> {
  await request<void>(
    `/api/v1/whiteboard/items/${itemId}/sharing/company`,
    token,
    {
      method: 'PUT',
      body: JSON.stringify({
        enabled,
        company_admin_read_acknowledged: acknowledged,
      }),
    },
  );
  return getWhiteboard(token, itemId);
}
