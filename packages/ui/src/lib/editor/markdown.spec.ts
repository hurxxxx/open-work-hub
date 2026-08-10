import { describe, expect, it, vi } from 'vitest';

import {
  createBlockDocumentCodec,
  type BlockDocumentCodecEditor,
} from './block-document-codec';
import { blockContentToMarkdown, markdownToBlockContent } from './markdown';
import type { BlockContent } from './types';

describe('BlockNote Markdown conversion', () => {
  it('exports empty content as empty Markdown', () => {
    expect(blockContentToMarkdown([])).toBe('');
    expect(blockContentToMarkdown(null)).toBe('');
  });

  it('parses Markdown into block content and exports it back to Markdown', () => {
    const blocks = markdownToBlockContent(
      '# Heading\n\n- First item\n- Second item',
    );

    expect(blocks.length).toBeGreaterThan(0);

    const markdown = blockContentToMarkdown(blocks);

    expect(markdown).toContain('Heading');
    expect(markdown).toContain('First item');
    expect(markdown).toContain('Second item');
  });

  it('round-trips Markdown through block content stably', () => {
    const source = [
      '# Heading',
      '',
      'Paragraph with **bold** text.',
      '',
      '- First item',
      '- Second item',
    ].join('\n');

    const firstMarkdown = blockContentToMarkdown(
      markdownToBlockContent(source),
    );
    const secondMarkdown = blockContentToMarkdown(
      markdownToBlockContent(firstMarkdown),
    );

    expect(secondMarkdown).toBe(firstMarkdown);
    expect(secondMarkdown).toContain('Heading');
    expect(secondMarkdown).toContain('First item');
  });

  it('stably round-trips the supported Markdown subset used by documents', () => {
    const source = [
      '# 한국어 제목',
      '',
      '일반 문단과 **굵은 글씨**, *기울임*, [링크](https://example.com).',
      '',
      '- 상위 항목',
      '  - 하위 항목',
      '',
      '- [x] 완료 작업',
      '- [ ] 남은 작업',
      '',
      '| 이름 | 상태 |',
      '| --- | --- |',
      '| 문서 | 완료 |',
      '',
      '```ts',
      'const greeting = "안녕하세요";',
      '```',
    ].join('\n');

    const firstMarkdown = blockContentToMarkdown(
      markdownToBlockContent(source),
    );
    const secondMarkdown = blockContentToMarkdown(
      markdownToBlockContent(firstMarkdown),
    );

    expect(secondMarkdown).toBe(firstMarkdown);
    expect(secondMarkdown).toContain('한국어 제목');
    expect(secondMarkdown).toContain('하위 항목');
    expect(secondMarkdown).toContain('완료 작업');
    expect(secondMarkdown).toContain('문서');
    expect(secondMarkdown).toContain('const greeting');
  });

  it('runs the cleanup hook after using the temporary editor', () => {
    const blocks = [{ id: 'block-1' }] as unknown as BlockContent;
    const blocksToMarkdownLossy = vi.fn(() => 'encoded markdown');
    const tryParseMarkdownToBlocks = vi.fn(() => blocks);
    const editor = {
      blocksToMarkdownLossy,
      tryParseMarkdownToBlocks,
    } as unknown as BlockDocumentCodecEditor;
    const cleanupEditor = vi.fn();
    const codec = createBlockDocumentCodec({
      createEditor: () => editor,
      cleanupEditor,
    });

    expect(codec.blockContentToMarkdown(blocks)).toBe('encoded markdown');
    expect(blocksToMarkdownLossy).toHaveBeenCalledWith(blocks);
    expect(cleanupEditor).toHaveBeenCalledWith(editor);

    cleanupEditor.mockClear();

    expect(codec.markdownToBlockContent('**hello**')).toBe(blocks);
    expect(tryParseMarkdownToBlocks).toHaveBeenCalledWith('**hello**');
    expect(cleanupEditor).toHaveBeenCalledWith(editor);
  });
});
