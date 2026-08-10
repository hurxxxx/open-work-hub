export interface BlockNoteCopyEvent {
  currentTarget: Pick<HTMLElement, 'ownerDocument'>;
  clipboardData: Pick<DataTransfer, 'setData'>;
}

interface BlockNotePasteContext {
  defaultPasteHandler: (context?: {
    prioritizeMarkdownOverHTML?: boolean;
    plainTextAsMarkdown?: boolean;
  }) => boolean | undefined;
}

interface BlockNoteInteractionPolicy {
  normalizeCopyPlainText: (event: BlockNoteCopyEvent) => void;
  preferRichTextPaste: (context: BlockNotePasteContext) => boolean | undefined;
}

export function normalizeBlockNoteCopyPlainText(
  event: BlockNoteCopyEvent,
): void {
  const selection = event.currentTarget.ownerDocument.getSelection();
  if (!selection || selection.isCollapsed) {
    return;
  }

  const plainText = selection.toString();
  if (!plainText) {
    return;
  }

  event.clipboardData.setData('text/plain', plainText);
}

export function preferRichTextPaste({
  defaultPasteHandler,
}: BlockNotePasteContext): boolean | undefined {
  return defaultPasteHandler({
    plainTextAsMarkdown: false,
    prioritizeMarkdownOverHTML: false,
  });
}

export const blockNoteInteractionPolicy: BlockNoteInteractionPolicy = {
  normalizeCopyPlainText: normalizeBlockNoteCopyPlainText,
  preferRichTextPaste,
};
