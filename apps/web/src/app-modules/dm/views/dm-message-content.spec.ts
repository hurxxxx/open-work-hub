import { describe, expect, it } from 'vitest';

import { buildDmMessageContent } from './dm-message-content';

describe('dm message content', () => {
  it('splits text and links while preserving trailing punctuation as text', () => {
    expect(
      buildDmMessageContent('See https://example.com/path?x=1, thanks')
        .segments,
    ).toEqual([
      { kind: 'text', text: 'See ' },
      {
        kind: 'link',
        href: 'https://example.com/path?x=1',
        label: 'https://example.com/path?x=1',
      },
      { kind: 'text', text: ', thanks' },
    ]);
  });

  it('trims unmatched closing parentheses from link labels', () => {
    expect(buildDmMessageContent('(https://example.com/a).').segments).toEqual([
      { kind: 'text', text: '(' },
      {
        kind: 'link',
        href: 'https://example.com/a',
        label: 'https://example.com/a',
      },
      { kind: 'text', text: ').' },
    ]);
  });

  it('normalizes www links and derives preview display fields', () => {
    expect(buildDmMessageContent('www.example.com/docs').previews).toEqual([
      {
        key: 'https://www.example.com/docs',
        href: 'https://www.example.com/docs',
        label: 'www.example.com/docs',
        host: 'example.com',
        path: '/docs',
      },
    ]);
  });

  it('suppresses duplicate previews and caps previews at three links', () => {
    const content = buildDmMessageContent(
      [
        'https://one.example/a',
        'https://one.example/a',
        'https://two.example/b',
        'https://three.example/c',
        'https://four.example/d',
      ].join(' '),
    );

    expect(
      content.segments.filter((segment) => segment.kind === 'link'),
    ).toHaveLength(5);
    expect(content.previews.map((preview) => preview.host)).toEqual([
      'one.example',
      'two.example',
      'three.example',
    ]);
  });

  it('keeps messages without links as plain text', () => {
    expect(buildDmMessageContent('plain ftp://example.test message')).toEqual({
      segments: [{ kind: 'text', text: 'plain ftp://example.test message' }],
      previews: [],
    });
  });
});
