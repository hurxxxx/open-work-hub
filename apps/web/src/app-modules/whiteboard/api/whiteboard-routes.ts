type PathSegment = string | number;
type QueryValue = string | number | boolean | null | undefined;
type QueryEntry = readonly [string, QueryValue];

export interface WhiteboardHubRouteParams {
  view?: string;
  q?: string;
  sort_by?: string;
  sort_dir?: string;
  page?: number;
  page_size?: number;
  source_app?: string;
  source_kind?: string;
  space_id?: string;
  target_app?: string;
  target_type?: string;
  target_id?: string;
}

export interface WhiteboardContextRouteParams {
  app: string;
  type: string;
  id: string;
}

const WHITEBOARD_API_ROOT = '/api/v1/whiteboard';

function encodePathSegment(segment: PathSegment): string {
  return encodeURIComponent(String(segment));
}

function shouldOmitQueryValue(value: QueryValue): boolean {
  return value === null || value === undefined || value === '';
}

function appendQuery(
  path: string,
  entries: readonly QueryEntry[] = [],
): string {
  const query = new URLSearchParams();
  for (const [key, value] of entries) {
    if (shouldOmitQueryValue(value)) continue;
    query.set(key, String(value));
  }

  const serialized = query.toString();
  return serialized ? `${path}?${serialized}` : path;
}

export function buildWhiteboardApiPath(
  segments: readonly PathSegment[] = [],
  query: readonly QueryEntry[] = [],
): string {
  const suffix = segments.map(encodePathSegment).join('/');
  const path = suffix
    ? `${WHITEBOARD_API_ROOT}/${suffix}`
    : WHITEBOARD_API_ROOT;
  return appendQuery(path, query);
}

export const whiteboardApiRoutes = {
  hub(params: WhiteboardHubRouteParams = {}): string {
    return buildWhiteboardApiPath(
      ['hub'],
      [
        ['view', params.view],
        ['q', params.q],
        ['sort_by', params.sort_by],
        ['sort_dir', params.sort_dir],
        ['page', params.page],
        ['page_size', params.page_size],
        ['source_app', params.source_app],
        ['source_kind', params.source_kind],
        ['space_id', params.space_id],
        ['target_app', params.target_app],
        ['target_type', params.target_type],
        ['target_id', params.target_id],
      ],
    );
  },

  items(): string {
    return buildWhiteboardApiPath(['items']);
  },

  item(itemId: string): string {
    return buildWhiteboardApiPath(['items', itemId]);
  },

  itemTarget(itemId: string): string {
    return buildWhiteboardApiPath(['items', itemId, 'target']);
  },

  itemRestore(itemId: string): string {
    return buildWhiteboardApiPath(['items', itemId, 'restore']);
  },

  itemPermanent(itemId: string): string {
    return buildWhiteboardApiPath(['items', itemId, 'permanent']);
  },

  itemFavorite(itemId: string): string {
    return buildWhiteboardApiPath(['items', itemId, 'favorite']);
  },

  itemView(itemId: string): string {
    return buildWhiteboardApiPath(['items', itemId, 'view']);
  },

  collabSession(itemId: string): string {
    return buildWhiteboardApiPath(['collab', 'items', itemId, 'session']);
  },

  collabSnapshot(itemId: string): string {
    return buildWhiteboardApiPath(['collab', 'items', itemId, 'snapshot']);
  },

  contextSlot(context?: WhiteboardContextRouteParams): string {
    return buildWhiteboardApiPath(
      ['contexts', 'slot'],
      context
        ? [
            ['app', context.app],
            ['type', context.type],
            ['id', context.id],
          ]
        : [],
    );
  },

  shareableUsers(q = ''): string {
    return buildWhiteboardApiPath(['shareable-users'], [['q', q]]);
  },

  sharing(itemId: string): string {
    return buildWhiteboardApiPath(['items', itemId, 'sharing']);
  },

  userShare(itemId: string, userId: string): string {
    return buildWhiteboardApiPath([
      'items',
      itemId,
      'sharing',
      'users',
      userId,
    ]);
  },

  linkShare(itemId: string): string {
    return buildWhiteboardApiPath(['items', itemId, 'sharing', 'link']);
  },

  sharedLink(shareToken: string): string {
    return buildWhiteboardApiPath(['shared-links', shareToken]);
  },

  sharedLinkItem(shareToken: string): string {
    return buildWhiteboardApiPath(['shared-links', shareToken, 'item']);
  },

  sharedLinkView(shareToken: string): string {
    return buildWhiteboardApiPath(['shared-links', shareToken, 'view']);
  },
};
