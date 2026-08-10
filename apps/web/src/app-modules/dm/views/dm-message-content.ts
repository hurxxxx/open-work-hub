const urlPattern = /(https?:\/\/[^\s<>"']+|www\.[^\s<>"']+)/gi;

export type DmMessageContentSegment =
  | { kind: 'text'; text: string }
  | { kind: 'link'; href: string; label: string };

export interface DmMessageLinkPreview {
  key: string;
  href: string;
  label: string;
  host: string;
  path: string;
}

export interface DmMessageContent {
  segments: DmMessageContentSegment[];
  previews: DmMessageLinkPreview[];
}

function trimUrlToken(value: string): string {
  let next = value;
  while (/[.,!?;:]$/.test(next)) {
    next = next.slice(0, -1);
  }
  while (
    next.endsWith(')') &&
    (next.match(/\)/g)?.length ?? 0) > (next.match(/\(/g)?.length ?? 0)
  ) {
    next = next.slice(0, -1);
  }
  return next;
}

function messageLinkPreview(rawValue: string): DmMessageLinkPreview | null {
  const label = trimUrlToken(rawValue);
  const href = label.startsWith('www.') ? `https://${label}` : label;
  try {
    const url = new URL(href);
    if (url.protocol !== 'http:' && url.protocol !== 'https:') {
      return null;
    }
    const displayPath = `${url.pathname}${url.search}`;
    return {
      key: url.href,
      href: url.href,
      label,
      host: url.hostname.replace(/^www\./, ''),
      path: displayPath === '/' ? url.hostname : displayPath,
    };
  } catch {
    return null;
  }
}

function addPreview(
  previews: DmMessageLinkPreview[],
  seen: Set<string>,
  preview: DmMessageLinkPreview,
): void {
  if (previews.length >= 3 || seen.has(preview.key)) {
    return;
  }
  seen.add(preview.key);
  previews.push(preview);
}

export function buildDmMessageContent(body: string): DmMessageContent {
  const segments: DmMessageContentSegment[] = [];
  const previews: DmMessageLinkPreview[] = [];
  const seenPreviews = new Set<string>();
  let lastIndex = 0;

  for (const match of body.matchAll(urlPattern)) {
    const matched = match[0];
    const start = match.index ?? 0;
    const preview = messageLinkPreview(matched);
    if (!preview) {
      continue;
    }

    if (start > lastIndex) {
      segments.push({ kind: 'text', text: body.slice(lastIndex, start) });
    }
    segments.push({
      kind: 'link',
      href: preview.href,
      label: preview.label,
    });
    lastIndex = start + preview.label.length;
    addPreview(previews, seenPreviews, preview);
  }

  if (lastIndex < body.length) {
    segments.push({ kind: 'text', text: body.slice(lastIndex) });
  }

  return {
    segments,
    previews,
  };
}
