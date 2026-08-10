import { BlockNoteEditor } from '@blocknote/core';

import { fullSchema } from './schema';
import type { BlockContent } from './types';

type CreatedBlockNoteEditor = ReturnType<typeof BlockNoteEditor.create>;

export type BlockDocumentCodecEditor = Pick<
  CreatedBlockNoteEditor,
  'blocksToMarkdownLossy' | 'tryParseMarkdownToBlocks'
>;

type DisposableBlockDocumentCodecEditor = BlockDocumentCodecEditor & {
  _tiptapEditor?: { destroy?: () => void };
};

interface BlockDocumentCodec {
  blockContentToMarkdown: (content?: BlockContent | null) => string;
  markdownToBlockContent: (markdown: string) => BlockContent;
}

interface BlockDocumentCodecDependencies {
  createEditor?: () => BlockDocumentCodecEditor;
  cleanupEditor?: (editor: BlockDocumentCodecEditor) => void;
}

function createDefaultCodecEditor(): BlockDocumentCodecEditor {
  return BlockNoteEditor.create({ schema: fullSchema });
}

function cleanupBlockDocumentCodecEditor(
  editor: BlockDocumentCodecEditor,
): void {
  (editor as DisposableBlockDocumentCodecEditor)._tiptapEditor?.destroy?.();
}

export function createBlockDocumentCodec({
  createEditor = createDefaultCodecEditor,
  cleanupEditor = cleanupBlockDocumentCodecEditor,
}: BlockDocumentCodecDependencies = {}): BlockDocumentCodec {
  function withCodecEditor<T>(
    callback: (editor: BlockDocumentCodecEditor) => T,
  ): T {
    const editor = createEditor();
    try {
      return callback(editor);
    } finally {
      cleanupEditor(editor);
    }
  }

  return {
    blockContentToMarkdown(content) {
      if (!content?.length) {
        return '';
      }
      return withCodecEditor((editor) =>
        editor.blocksToMarkdownLossy(content as never),
      );
    },
    markdownToBlockContent(markdown) {
      return withCodecEditor(
        (editor) =>
          editor.tryParseMarkdownToBlocks(markdown) as unknown as BlockContent,
      );
    },
  };
}

const defaultBlockDocumentCodec = createBlockDocumentCodec();

export function blockContentToMarkdown(content?: BlockContent | null): string {
  return defaultBlockDocumentCodec.blockContentToMarkdown(content);
}

export function markdownToBlockContent(markdown: string): BlockContent {
  return defaultBlockDocumentCodec.markdownToBlockContent(markdown);
}
