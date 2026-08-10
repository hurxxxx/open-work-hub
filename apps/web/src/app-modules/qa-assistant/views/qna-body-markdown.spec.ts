import { describe, expect, it } from 'vitest';

import { formatQnaBodyMarkdown } from './qna-body-markdown';

describe('formatQnaBodyMarkdown', () => {
  it('turns extracted document markers into readable Markdown sections', () => {
    expect(
      formatQnaBodyMarkdown(
        [
          '[Attachment: guide.pdf]',
          '[p.1] Annual settlement',
          '- item one',
          '<!-- image -->',
          '[p.2]',
        ].join('\n'),
      ),
    ).toBe(
      [
        '### Attachment: guide.pdf',
        '',
        '#### p.1 Annual settlement',
        '',
        '- item one',
        '',
        '#### p.2',
      ].join('\n'),
    );
  });

  it('preserves ordinary bracketed text that is not an extraction marker', () => {
    expect(formatQnaBodyMarkdown('[Notice]\nbody')).toBe('[Notice]\nbody');
  });
});
