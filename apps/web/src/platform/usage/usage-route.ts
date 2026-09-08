const UUID_SEGMENT_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const LONG_HEX_SEGMENT_PATTERN = /^[0-9a-f]{16,}$/i;
const LONG_NUMBER_SEGMENT_PATTERN = /^\d{4,}$/;

function safeDecodePathSegment(segment: string): string {
  try {
    return decodeURIComponent(segment);
  } catch {
    return segment;
  }
}

function normalizePathSegment(segment: string): string {
  const decoded = safeDecodePathSegment(segment).trim();
  if (
    UUID_SEGMENT_PATTERN.test(decoded) ||
    LONG_HEX_SEGMENT_PATTERN.test(decoded) ||
    LONG_NUMBER_SEGMENT_PATTERN.test(decoded)
  ) {
    return ':id';
  }
  const safe = decoded.replace(/[^a-zA-Z0-9._~-]/g, '-');
  return (safe || ':segment').slice(0, 64);
}

export function normalizeUsageRoutePath(pathname: string): string {
  const segments = pathname.split('/').filter(Boolean);
  if (segments.length === 0) {
    return '/';
  }
  const normalized = segments.map((segment, index) => {
    const decoded = safeDecodePathSegment(segment);

    if (index === 1 && segments[0] === 'admin') {
      return normalizePathSegment(decoded);
    }
    return normalizePathSegment(decoded);
  });
  return `/${normalized.join('/')}`.slice(0, 240);
}

export function resolveUsageEventAppId({
  activeAppId,
  activeNavItemId,
  navItems,
}: {
  activeAppId: string;
  activeNavItemId?: string | null;
  navItems?:
    | readonly {
        app_id?: string | null;
        id: string;
      }[]
    | null;
}): string {
  const activeNavItem = activeNavItemId
    ? navItems?.find((item) => item.id === activeNavItemId)
    : null;
  return (activeNavItem?.app_id || activeAppId).slice(0, 64);
}
