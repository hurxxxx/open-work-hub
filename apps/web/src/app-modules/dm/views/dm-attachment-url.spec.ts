import { describe, expect, it } from 'vitest';

import {
  downloadSpecForAttachment,
  imagePreviewUrlForAttachment,
  imageViewerForAttachment,
  resolveWebDmAttachmentUrl,
} from './dm-attachment-url';

describe('web DM attachment URL helpers', () => {
  it('resolves only same-origin DM attachment URLs', () => {
    expect(
      resolveWebDmAttachmentUrl(
        '/api/v1/dm/attachments/a/preview',
        'https://workspace.example.test',
      ),
    ).toBe('https://workspace.example.test/api/v1/dm/attachments/a/preview');
    expect(
      resolveWebDmAttachmentUrl(
        'https://cdn.example.test/a.png',
        'https://workspace.example.test',
      ),
    ).toBeNull();
    expect(
      resolveWebDmAttachmentUrl('/api/v1/users/me', 'https://workspace.example.test'),
    ).toBeNull();
    expect(
      resolveWebDmAttachmentUrl(
        '/api/v1/dm/attachments/a%2Fb/preview',
        'https://workspace.example.test',
      ),
    ).toBeNull();
  });

  it('builds image preview and viewer state from safe attachment URLs', () => {
    expect(
      imagePreviewUrlForAttachment(
        { is_image: true, preview_url: '/api/v1/dm/attachments/a/preview' },
        'https://workspace.example.test',
      ),
    ).toBe('https://workspace.example.test/api/v1/dm/attachments/a/preview');
    expect(
      imagePreviewUrlForAttachment(
        { is_image: false, preview_url: '/api/v1/dm/attachments/a/preview' },
        'https://workspace.example.test',
      ),
    ).toBeNull();
    expect(
      imageViewerForAttachment(
        { filename: 'screen.png' },
        '/api/v1/dm/attachments/a/preview',
        'https://workspace.example.test',
      ),
    ).toEqual({
      filename: 'screen.png',
      url: 'https://workspace.example.test/api/v1/dm/attachments/a/preview',
    });
    expect(
      imageViewerForAttachment(
        { filename: 'screen.png' },
        'https://cdn.example.test/screen.png',
        'https://workspace.example.test',
      ),
    ).toBeNull();
  });

  it('builds download specs only for safe attachment URLs', () => {
    const scriptUrl = `java${'script'}:alert(1)`;

    expect(
      downloadSpecForAttachment(
        { filename: 'report.pdf' },
        '/api/v1/dm/attachments/a/download',
        'https://workspace.example.test',
      ),
    ).toEqual({
      href: 'https://workspace.example.test/api/v1/dm/attachments/a/download',
      filename: 'report.pdf',
      rel: 'noreferrer',
    });
    expect(
      downloadSpecForAttachment(
        { filename: 'report.pdf' },
        scriptUrl,
        'https://workspace.example.test',
      ),
    ).toBeNull();
  });
});
