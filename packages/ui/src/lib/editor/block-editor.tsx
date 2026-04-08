import { useEffect } from 'react';
import { MantineProvider } from '@mantine/core';
import { BlockNoteView } from '@blocknote/mantine';
import { useCreateBlockNote } from '@blocknote/react';
import '@blocknote/core/fonts/inter.css';
import '@blocknote/mantine/style.css';
import { fullSchema } from './schema';
import { useResolvedTheme } from './use-theme';
import type { BlockContent } from './types';

export interface BlockEditorProps {
  initialContent?: BlockContent;
  onChange?: (content: BlockContent) => void;
  editable?: boolean;
  placeholder?: string;
  className?: string;
  uploadFile?: (file: File) => Promise<string>;
  resolveFileUrl?: (url: string) => Promise<string>;
}

export function BlockEditor({
  initialContent,
  onChange,
  editable = true,
  placeholder,
  className,
  uploadFile,
  resolveFileUrl,
}: BlockEditorProps) {
  const theme = useResolvedTheme();

  const editor = useCreateBlockNote({
    schema: fullSchema,
    initialContent: initialContent?.length ? initialContent as any : undefined,
    ...(placeholder ? { placeholders: { default: placeholder } } : {}),
    uploadFile,
    resolveFileUrl,
  });

  useEffect(() => {
    if (!onChange) return;
    const unsubscribe = editor.onChange(() => {
      onChange(editor.document as unknown as BlockContent);
    });
    return unsubscribe;
  }, [editor, onChange]);

  return (
    <div className={`[&_.bn-container]:!bg-transparent [&_.bn-editor]:!bg-transparent ${className ?? ''}`}>
      <MantineProvider forceColorScheme={theme}>
        <BlockNoteView
          editor={editor}
          editable={editable}
          theme={theme}
        />
      </MantineProvider>
    </div>
  );
}
