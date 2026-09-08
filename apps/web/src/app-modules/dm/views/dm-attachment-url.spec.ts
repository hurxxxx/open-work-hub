import { describe, expect, it } from 'vitest';
import { downloadSpecForAttachment } from './dm-attachment-url';
describe('DM authenticated content download specs', () => {
  it('accepts only the shared header-grant content contract', () => {
    expect(
      downloadSpecForAttachment(
        { filename: 'report.pdf' },
        '/api/v1/content#grant=example',
      ),
    ).toEqual({
      href: '/api/v1/content#grant=example',
      filename: 'report.pdf',
    });
  });
  it.each([
    '/api/v1/dm/attachments/a/content?token=old',
    '/api/v1/dm/attachments/a/download',
    'https://external.test/file',
    'https://localhost/api/v1/content#grant=secret',
    '/api/v1/content?grant=secret',
    '/api/v1/content#grant=one&grant=two',
    null,
  ])('rejects URL %s', (value) => {
    expect(
      downloadSpecForAttachment({ filename: 'report.pdf' }, value),
    ).toBeNull();
  });
});
