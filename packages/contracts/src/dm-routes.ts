export interface DmAttachmentUploadFile {
  size: number;
}

export const DM_API_PREFIX = '/api/v1/dm';
export const DM_QUERY_LIMIT_MIN = 1;
export const DM_QUERY_LIMIT_MAX = 100;
export const DEFAULT_DM_MESSAGE_LIMIT = 50;
export const DEFAULT_DM_USER_SEARCH_LIMIT = 30;
export const DM_ROUTE_ID_MAX_LENGTH = 36;
export const DM_ROUTE_ID_ALLOWED_PATTERN = '^[A-Za-z0-9_-]+$';
export const DM_MAX_ATTACHMENT_BYTES = 52428800;

const DM_ROUTE_ID_PATTERN = new RegExp(DM_ROUTE_ID_ALLOWED_PATTERN, 'u');

export const dmRoutes = {
  users: (input: { q?: string; limit?: number } = {}) => {
    const params = new URLSearchParams();
    if (input.q != null) {
      params.set('q', input.q);
    }
    params.set(
      'limit',
      String(normalizeDmLimit(input.limit ?? DEFAULT_DM_USER_SEARCH_LIMIT)),
    );
    return `${DM_API_PREFIX}/users?${params.toString()}`;
  },
  conversations: () => `${DM_API_PREFIX}/conversations`,
  conversation: (conversationId: string) =>
    `${DM_API_PREFIX}/conversations/${encodeSegment(conversationId)}`,
  conversationParticipants: (conversationId: string) =>
    `${DM_API_PREFIX}/conversations/${encodeSegment(conversationId)}/participants`,
  conversationParticipant: (conversationId: string, userId: string) =>
    `${DM_API_PREFIX}/conversations/${encodeSegment(conversationId)}/participants/${encodeSegment(userId)}`,
  leaveConversation: (conversationId: string) =>
    `${DM_API_PREFIX}/conversations/${encodeSegment(conversationId)}/participants/me`,
  messages: (conversationId: string) =>
    `${DM_API_PREFIX}/conversations/${encodeSegment(conversationId)}/messages`,
  listMessages: (
    conversationId: string,
    input: { limit?: number; before?: string | Date | null } = {},
  ) => {
    const params = new URLSearchParams({
      limit: String(normalizeDmLimit(input.limit ?? DEFAULT_DM_MESSAGE_LIMIT)),
    });
    if (input.before) {
      params.set(
        'before',
        typeof input.before === 'string'
          ? input.before
          : input.before.toISOString(),
      );
    }
    return `${dmRoutes.messages(conversationId)}?${params.toString()}`;
  },
  messageAttachments: (conversationId: string) =>
    `${DM_API_PREFIX}/conversations/${encodeSegment(conversationId)}/attachments`,
  attachmentDownload: (attachmentId: string) =>
    `${DM_API_PREFIX}/attachments/${encodeSegment(attachmentId)}/download`,
  attachmentPreview: (attachmentId: string) =>
    `${DM_API_PREFIX}/attachments/${encodeSegment(attachmentId)}/preview`,
  markRead: (conversationId: string) =>
    `${DM_API_PREFIX}/conversations/${encodeSegment(conversationId)}/read`,
} as const;

export function normalizeDmLimit(value: number): number {
  if (
    !Number.isInteger(value) ||
    value < DM_QUERY_LIMIT_MIN ||
    value > DM_QUERY_LIMIT_MAX
  ) {
    throw new RangeError(
      `DM query limit must be an integer from ${DM_QUERY_LIMIT_MIN} to ${DM_QUERY_LIMIT_MAX}.`,
    );
  }
  return value;
}

export function isDmRouteId(value: string): boolean {
  return (
    value.length > 0 &&
    value.length <= DM_ROUTE_ID_MAX_LENGTH &&
    DM_ROUTE_ID_PATTERN.test(value)
  );
}

export function resolveDmAttachmentUrl(
  value: string | null | undefined,
  baseUrl: string,
): string | null {
  if (!value) {
    return null;
  }
  try {
    const base = new URL(baseUrl);
    const url = new URL(value, base);
    if (
      url.origin !== base.origin ||
      url.username ||
      url.password ||
      url.hash ||
      !isDmAttachmentUrl(url)
    ) {
      return null;
    }
    return url.toString();
  } catch {
    return null;
  }
}

export function isDmAttachmentUploadFileAllowed(
  file: DmAttachmentUploadFile,
): boolean {
  return (
    Number.isFinite(file.size) &&
    file.size >= 0 &&
    file.size <= DM_MAX_ATTACHMENT_BYTES
  );
}

function encodeSegment(value: string): string {
  if (!isDmRouteId(value)) {
    throw new Error(
      `DM route id must be 1-${DM_ROUTE_ID_MAX_LENGTH} URL segment-safe characters.`,
    );
  }
  return encodeURIComponent(value);
}

function isDmAttachmentUrl(url: URL): boolean {
  const segments = url.pathname.slice(1).split('/');
  const prefixSegments = DM_API_PREFIX.slice(1).split('/');
  if (
    segments.length !== prefixSegments.length + 3 ||
    prefixSegments.some((segment, index) => segments[index] !== segment) ||
    segments[prefixSegments.length] !== 'attachments'
  ) {
    return false;
  }
  let attachmentId: string;
  try {
    attachmentId = decodeURIComponent(
      segments[prefixSegments.length + 1] ?? '',
    );
  } catch {
    return false;
  }
  const action = segments[prefixSegments.length + 2];
  if (!isDmRouteId(attachmentId)) {
    return false;
  }
  return action === 'download' || action === 'preview' || action === 'content';
}
