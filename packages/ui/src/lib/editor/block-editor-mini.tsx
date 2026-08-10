import { useEffect, useCallback } from 'react';
import { MantineProvider } from '@mantine/core';
import { BlockNoteView } from '@blocknote/mantine';
import { useCreateBlockNote } from '@blocknote/react';
import '@mantine/core/styles.css';
import '@blocknote/core/fonts/inter.css';
import '@blocknote/mantine/style.css';
import { compactSchema } from './schema';
import { useResolvedTheme } from './use-theme';
import { blockNoteInteractionPolicy } from './blocknote-interaction-policy';
import type { BlockContent } from './types';

export interface BlockEditorMiniProps {
  onChange?: (content: BlockContent) => void;
  onSubmit?: (content: BlockContent) => void;
  placeholder?: string;
  className?: string;
}

/**
 * Compact block editor for comments and short-form input.
 * Reduced block set (no tables, code blocks, images).
 * Ctrl+Enter triggers onSubmit.
 */
export function BlockEditorMini({
  onChange,
  onSubmit,
  placeholder,
  className,
}: BlockEditorMiniProps) {
  const theme = useResolvedTheme();

  const editor = useCreateBlockNote({
    schema: compactSchema,
    ...(placeholder ? { placeholders: { default: placeholder } } : {}),
    pasteHandler: blockNoteInteractionPolicy.preferRichTextPaste,
  });

  useEffect(() => {
    if (!onChange) return;
    const unsubscribe = editor.onChange(() => {
      onChange(editor.document as unknown as BlockContent);
    });
    return unsubscribe;
  }, [editor, onChange]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter' && onSubmit) {
        e.preventDefault();
        onSubmit(editor.document as unknown as BlockContent);
        // Clear editor after submit
        editor.removeBlocks(editor.document);
      }
    },
    [editor, onSubmit],
  );

  return (
    <div
      className={`ui-block-editor [&_.bn-root]:!bg-transparent [&_.bn-container]:!bg-transparent [&_.bn-editor]:!bg-transparent ${className ?? ''}`}
    >
      <MantineProvider forceColorScheme={theme}>
        <BlockNoteView
          editor={editor}
          onKeyDown={handleKeyDown}
          onCopy={blockNoteInteractionPolicy.normalizeCopyPlainText}
          theme={theme}
        />
      </MantineProvider>
    </div>
  );
}
