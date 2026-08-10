import { describe, expect, it } from 'vitest';

import {
  downloadBlobAsFile,
  openBlobInNewTab,
  openDownloadUrl,
  type BrowserBlobOpenAdapter,
  type BrowserDownloadAdapter,
  type BrowserDownloadAnchor,
} from './browser-download';

function createFakeAdapter() {
  const calls: string[] = [];
  const anchors: BrowserDownloadAnchor[] = [];
  const adapter: BrowserDownloadAdapter = {
    createObjectUrl: () => {
      calls.push('createObjectUrl');
      return 'blob:download-url';
    },
    revokeObjectUrl: (url) => {
      calls.push(`revokeObjectUrl:${url}`);
    },
    createAnchor: () => {
      calls.push('createAnchor');
      const anchor: BrowserDownloadAnchor = {
        href: '',
        download: '',
        click: () => {
          calls.push('click');
        },
        remove: () => {
          calls.push('remove');
        },
      };
      anchors.push(anchor);
      return anchor;
    },
    appendAnchor: () => {
      calls.push('appendAnchor');
    },
    openUrl: (url) => {
      calls.push(`openUrl:${url}`);
    },
  };

  return { adapter, anchors, calls };
}

describe('browser download', () => {
  it('downloads a blob with a temporary object URL and filename', () => {
    const fake = createFakeAdapter();

    downloadBlobAsFile(
      new Blob(['hello'], { type: 'text/plain' }),
      'hello.txt',
      fake.adapter,
    );

    expect(fake.anchors[0]).toMatchObject({
      href: 'blob:download-url',
      download: 'hello.txt',
    });
    expect(fake.calls).toEqual([
      'createObjectUrl',
      'createAnchor',
      'appendAnchor',
      'click',
      'remove',
      'revokeObjectUrl:blob:download-url',
    ]);
  });

  it('cleans up the temporary object URL when clicking fails', () => {
    const fake = createFakeAdapter();
    fake.adapter.createAnchor = () => ({
      href: '',
      download: '',
      click: () => {
        fake.calls.push('click');
        throw new Error('blocked');
      },
      remove: () => {
        fake.calls.push('remove');
      },
    });

    expect(() =>
      downloadBlobAsFile(new Blob(['blocked']), 'blocked.txt', fake.adapter),
    ).toThrow('blocked');
    expect(fake.calls).toEqual([
      'createObjectUrl',
      'appendAnchor',
      'click',
      'remove',
      'revokeObjectUrl:blob:download-url',
    ]);
  });

  it('opens direct download URLs through the adapter', () => {
    const fake = createFakeAdapter();

    openDownloadUrl('/download/file', fake.adapter);

    expect(fake.calls).toEqual(['openUrl:/download/file']);
  });

  it('opens a blob in a new tab and schedules object URL cleanup', () => {
    const calls: string[] = [];
    let scheduledCallback: (() => void) | null = null;
    const adapter: BrowserBlobOpenAdapter = {
      createObjectUrl: () => {
        calls.push('createObjectUrl');
        return 'blob:preview-url';
      },
      revokeObjectUrl: (url) => {
        calls.push(`revokeObjectUrl:${url}`);
      },
      openObjectUrl: (url) => {
        calls.push(`openObjectUrl:${url}`);
      },
      scheduleRevoke: (callback, delayMs) => {
        calls.push(`scheduleRevoke:${delayMs}`);
        scheduledCallback = callback;
      },
    };

    openBlobInNewTab(new Blob(['preview']), adapter, 30_000);

    expect(calls).toEqual([
      'createObjectUrl',
      'openObjectUrl:blob:preview-url',
      'scheduleRevoke:30000',
    ]);

    scheduledCallback?.();

    expect(calls.at(-1)).toBe('revokeObjectUrl:blob:preview-url');
  });
});
