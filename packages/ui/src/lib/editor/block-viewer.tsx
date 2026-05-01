import { MantineProvider } from '@mantine/core';
import { BlockNoteView } from '@blocknote/mantine';
import { useCreateBlockNote } from '@blocknote/react';
import '@mantine/core/styles.css';
import '@blocknote/core/fonts/inter.css';
import '@blocknote/mantine/style.css';
import { fullSchema } from './schema';
import { useResolvedTheme } from './use-theme';
import type { BlockContent } from './types';

export interface BlockViewerProps {
  content?: BlockContent;
  className?: string;
  resolveFileUrl?: (url: string) => Promise<string>;
}

/**
 * Read-only block content renderer.
 * Used in list views, board cards, activity feeds.
 */
export function BlockViewer({ content, className, resolveFileUrl }: BlockViewerProps) {
  const theme = useResolvedTheme();

  const editor = useCreateBlockNote({
    schema: fullSchema,
    initialContent: content?.length ? content as any : undefined,
    resolveFileUrl,
  });

  return (
    <div className={`[&_.bn-container]:!bg-transparent [&_.bn-editor]:!bg-transparent ${className ?? ''}`}>
      <MantineProvider forceColorScheme={theme}>
        <BlockNoteView
          editor={editor}
          editable={false}
          theme={theme}
        />
      </MantineProvider>
    </div>
  );
}
