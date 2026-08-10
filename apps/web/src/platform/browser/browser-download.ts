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
