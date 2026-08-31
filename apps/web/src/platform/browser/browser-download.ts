import { apiFetchBinary } from '@/src/platform/api/client';
import { i18n } from '@/src/platform/i18n';

export type BrowserDownloadAnchor = {
  href: string;
  download: string;
  click: () => void;
  remove: () => void;
};

export type BrowserDownloadAdapter = {
  createObjectUrl: (blob: Blob) => string;
  revokeObjectUrl: (url: string) => void;
  createAnchor: () => BrowserDownloadAnchor;
  appendAnchor: (anchor: BrowserDownloadAnchor) => void;
  openUrl: (url: string) => void;
};

export type BrowserBlobOpenAdapter = {
  createObjectUrl: (blob: Blob) => string;
  revokeObjectUrl: (url: string) => void;
  openObjectUrl: (url: string) => void;
  scheduleRevoke: (callback: () => void, delayMs: number) => void;
};

export interface AuthenticatedContentRequest {
  grant: string;
  url: string;
}

export function parseAuthenticatedContentUrl(
  value: string,
): AuthenticatedContentRequest {
  const fragmentIndex = value.indexOf('#');
  const hasSingleFragment =
    fragmentIndex >= 0 && value.indexOf('#', fragmentIndex + 1) === -1;
  const url = hasSingleFragment ? value.slice(0, fragmentIndex) : '';
  const fragment = hasSingleFragment ? value.slice(fragmentIndex + 1) : '';
  const params = new URLSearchParams(fragment);
  const grants = params.getAll('grant');
  const grant = grants[0];
  if (
    url !== '/api/v1/content' ||
    !grant ||
    grants.length !== 1 ||
    Array.from(params.keys()).some((key) => key !== 'grant')
  ) {
    throw new Error(i18n.t('apps:files.errors.downloadFailed'));
  }
  return { grant, url };
}

async function fetchAuthenticatedContent(token: string, url: string) {
  const request = parseAuthenticatedContentUrl(url);
  return apiFetchBinary(request.url, token, {
    headers: {
      'X-Open-Work-Hub-Content-Grant': request.grant,
    },
  });
}

export const defaultBrowserDownloadAdapter: BrowserDownloadAdapter = {
  createObjectUrl: (blob) => URL.createObjectURL(blob),
  revokeObjectUrl: (url) => URL.revokeObjectURL(url),
  createAnchor: () => document.createElement('a'),
  appendAnchor: (anchor) => {
    document.body.appendChild(anchor as HTMLAnchorElement);
  },
  openUrl: (url) => {
    window.location.assign(url);
  },
};

export const defaultBrowserBlobOpenAdapter: BrowserBlobOpenAdapter = {
  createObjectUrl: (blob) => URL.createObjectURL(blob),
  revokeObjectUrl: (url) => URL.revokeObjectURL(url),
  openObjectUrl: (url) => {
    window.open(url, '_blank', 'noopener,noreferrer');
  },
  scheduleRevoke: (callback, delayMs) => {
    window.setTimeout(callback, delayMs);
  },
};

export function downloadBlobAsFile(
  blob: Blob,
  filename: string,
  adapter: BrowserDownloadAdapter = defaultBrowserDownloadAdapter,
): void {
  const url = adapter.createObjectUrl(blob);
  const anchor = adapter.createAnchor();
  anchor.href = url;
  anchor.download = filename;
  adapter.appendAnchor(anchor);
  try {
    anchor.click();
  } finally {
    anchor.remove();
    adapter.revokeObjectUrl(url);
  }
}

export function openDownloadUrl(
  url: string,
  adapter: BrowserDownloadAdapter = defaultBrowserDownloadAdapter,
): void {
  adapter.openUrl(url);
}

export function openBlobInNewTab(
  blob: Blob,
  adapter: BrowserBlobOpenAdapter = defaultBrowserBlobOpenAdapter,
  revokeDelayMs = 60_000,
): void {
  const url = adapter.createObjectUrl(blob);
  adapter.openObjectUrl(url);
  adapter.scheduleRevoke(() => adapter.revokeObjectUrl(url), revokeDelayMs);
}

export function contentDispositionFilename(
  value: string | null,
  fallback: string,
): string {
  if (!value) return fallback;
  const encoded = value.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  if (encoded) {
    try {
      return decodeURIComponent(encoded);
    } catch {
      return fallback;
    }
  }
  return value.match(/filename="?([^";]+)"?/i)?.[1] || fallback;
}

export async function downloadAuthenticatedContent(
  token: string,
  url: string,
  fallbackFilename: string,
  adapter: BrowserDownloadAdapter = defaultBrowserDownloadAdapter,
): Promise<void> {
  const content = await fetchAuthenticatedContent(token, url);
  downloadBlobAsFile(
    content.blob,
    contentDispositionFilename(content.contentDisposition, fallbackFilename),
    adapter,
  );
}

export async function authenticatedContentObjectUrl(
  token: string,
  url: string,
): Promise<string> {
  const content = await fetchAuthenticatedContent(token, url);
  return URL.createObjectURL(content.blob);
}

export async function openAuthenticatedContent(
  token: string,
  url: string,
  adapter: BrowserBlobOpenAdapter = defaultBrowserBlobOpenAdapter,
): Promise<void> {
  const content = await fetchAuthenticatedContent(token, url);
  openBlobInNewTab(content.blob, adapter);
}
