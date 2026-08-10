import DOMPurify from 'dompurify';

const forbiddenMailHtmlTags = [
  'applet',
  'base',
  'button',
  'embed',
  'form',
  'frame',
  'frameset',
  'iframe',
  'input',
  'link',
  'meta',
  'object',
  'script',
  'select',
  'style',
  'textarea',
];

const forbiddenMailHtmlAttributes = ['srcdoc'];

const MAIL_DOCUMENT_COLORS = {
  bg: '#ffffff',
  ink: '#111827',
  link: '#2563eb',
} as const;

export interface MailHtmlDocument {
  blockedRemoteImageCount: number;
  srcDoc: string;
}

export function extractMailPreviewText(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return '';

  const sanitized = DOMPurify.sanitize(trimmed, {
    FORBID_TAGS: [...forbiddenMailHtmlTags, 'head', 'noscript', 'title'],
    WHOLE_DOCUMENT: false,
  });
  const document = new DOMParser().parseFromString(
    `<body>${sanitized}</body>`,
    'text/html',
  );
  document
    .querySelectorAll('head, noscript, script, style, title')
    .forEach((element) => element.remove());

  return normalizeMailText(
    stripCssBlocks(document.body.textContent ?? sanitized),
  );
}

export function buildMailHtmlDocument(
  html: string,
  options: { allowRemoteImages: boolean },
): MailHtmlDocument {
  const sanitized = DOMPurify.sanitize(html, {
    FORBID_ATTR: forbiddenMailHtmlAttributes,
    FORBID_TAGS: forbiddenMailHtmlTags,
    WHOLE_DOCUMENT: false,
  });
  const document = new DOMParser().parseFromString(
    `<body>${sanitized}</body>`,
    'text/html',
  );
  let blockedRemoteImageCount = 0;

  document.querySelectorAll<HTMLElement>('[style]').forEach((element) => {
    const cleanedStyle = cleanInlineStyle(element.getAttribute('style') ?? '');
    if (cleanedStyle) {
      element.setAttribute('style', cleanedStyle);
    } else {
      element.removeAttribute('style');
    }
  });

  document.querySelectorAll<HTMLElement>('[background]').forEach((element) => {
    const background = element.getAttribute('background') ?? '';
    if (!isSafeEmbeddedResource(background)) {
      element.removeAttribute('background');
    }
  });

  document.querySelectorAll<HTMLAnchorElement>('a[href]').forEach((anchor) => {
    const href = anchor.getAttribute('href') ?? '';
    if (!isAllowedLinkHref(href)) {
      anchor.removeAttribute('href');
      return;
    }
    anchor.setAttribute('target', '_blank');
    anchor.setAttribute('rel', 'noopener noreferrer');
  });

  document.querySelectorAll<HTMLImageElement>('img').forEach((image) => {
    image.removeAttribute('srcset');
    image.removeAttribute('sizes');
    const source = image.getAttribute('src') ?? '';
    if (!source) return;
    if (shouldBlockImageSource(source, options.allowRemoteImages)) {
      blockedRemoteImageCount += 1;
      image.setAttribute('data-blocked-src', source);
      image.removeAttribute('src');
      image.setAttribute('aria-hidden', 'true');
      image.setAttribute(
        'style',
        appendInlineStyle(
          image.getAttribute('style') ?? '',
          'display:none!important',
        ),
      );
    }
  });

  return {
    blockedRemoteImageCount,
    srcDoc: wrapMailHtml(document.body.innerHTML),
  };
}

function wrapMailHtml(bodyHtml: string): string {
  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <base target="_blank" />
  <style>
    html { color-scheme: light; }
    body {
      margin: 0;
      padding: 16px;
      background: ${MAIL_DOCUMENT_COLORS.bg};
      color: ${MAIL_DOCUMENT_COLORS.ink};
      font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      overflow-wrap: anywhere;
    }
    table { max-width: 100%; }
    img { max-width: 100%; height: auto; }
    a { color: ${MAIL_DOCUMENT_COLORS.link}; }
  </style>
</head>
<body>${bodyHtml}</body>
</html>`;
}

function cleanInlineStyle(style: string): string {
  const declarations: string[] = [];
  for (const declaration of style
    .replace(/@import[^;]+;?/gi, '')
    .replace(/url\s*\([^)]*\)/gi, '')
    .split(';')) {
    const trimmed = declaration.trim();
    if (trimmed) {
      declarations.push(trimmed);
    }
  }
  return declarations.join('; ');
}

function appendInlineStyle(current: string, next: string): string {
  const cleaned = cleanInlineStyle(current);
  return cleaned ? `${cleaned}; ${next}` : next;
}

function stripCssBlocks(value: string): string {
  let current = value;
  for (let index = 0; index < 8; index += 1) {
    const next = current
      .replace(/\s@media\b[\s\S]*$/gi, ' ')
      .replace(
        /(?:^|\s)(?:@media[^{]*|[#.]?[-_a-zA-Z][^{}]{0,160})\{[^{}]*\}/g,
        ' ',
      )
      .replace(/\s(?:@media[^{]*|[#.]?[-_a-zA-Z][^{}]{0,160})\{[^{}]*$/g, ' ');
    if (next === current) break;
    current = next;
  }
  return current;
}

function normalizeMailText(value: string): string {
  return value
    .replace(/\u00a0/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function isAllowedLinkHref(value: string): boolean {
  const trimmed = value.trim();
  if (!trimmed) return false;
  if (/^(https?:|mailto:|tel:)/i.test(trimmed)) return true;
  return false;
}

function isSafeEmbeddedResource(value: string): boolean {
  const trimmed = value.trim();
  return /^(data:image\/|cid:)/i.test(trimmed);
}

function shouldBlockImageSource(
  value: string,
  allowRemoteImages: boolean,
): boolean {
  const trimmed = value.trim();
  if (isSafeEmbeddedResource(trimmed)) return false;
  if (/^(https?:|\/\/)/i.test(trimmed)) return !allowRemoteImages;
  return true;
}
