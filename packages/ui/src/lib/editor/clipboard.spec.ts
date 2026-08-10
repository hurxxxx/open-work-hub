import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  blockNoteInteractionPolicy,
  type BlockNoteCopyEvent,
} from './blocknote-interaction-policy';
import {
  normalizeBlockNoteCopyPlainText,
  preferRichTextPaste,
} from './clipboard';

describe('BlockNote clipboard behavior', () => {
  afterEach(() => {
    document.getSelection()?.removeAllRanges();
  });

  it('writes selected visible text as text/plain instead of markdown payloads', () => {
    const host = document.createElement('div');
    host.textContent = 'Visible heading\nVisible list item';
    document.body.append(host);
    const range = document.createRange();
    range.selectNodeContents(host);
    const selection = document.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(range);
    const setData = vi.fn();

    normalizeBlockNoteCopyPlainText({
      clipboardData: { setData },
      currentTarget: host,
    });

    expect(setData).toHaveBeenCalledWith(
      'text/plain',
      'Visible heading\nVisible list item',
    );

    host.remove();
  });

  it('does nothing for collapsed copy selections', () => {
    const host = document.createElement('div');
    host.textContent = 'Visible heading';
    document.body.append(host);
    const range = document.createRange();
    const textNode = host.firstChild;
    if (!textNode) {
      throw new Error('Expected test text node');
    }
    range.setStart(textNode, 0);
    range.collapse(true);
    const selection = document.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(range);
    const setData = vi.fn();

    normalizeBlockNoteCopyPlainText({
      clipboardData: { setData },
      currentTarget: host,
    });

    expect(setData).not.toHaveBeenCalled();

    host.remove();
  });

  it('does nothing when the copy selection has no plain text', () => {
    const setData = vi.fn();

    normalizeBlockNoteCopyPlainText({
      clipboardData: { setData },
      currentTarget: {
        ownerDocument: {
          getSelection: () => ({
            isCollapsed: false,
            toString: () => '',
          }),
        },
      },
    } as unknown as BlockNoteCopyEvent);

    expect(setData).not.toHaveBeenCalled();
  });

  it('prefers rich HTML over markdown-looking plain text on paste', () => {
    const defaultPasteHandler = vi.fn(() => true);

    expect(preferRichTextPaste({ defaultPasteHandler })).toBe(true);

    expect(defaultPasteHandler).toHaveBeenCalledWith({
      plainTextAsMarkdown: false,
      prioritizeMarkdownOverHTML: false,
    });
  });

  it('keeps the rich paste preference stable through the interaction policy', () => {
    const defaultPasteHandler = vi.fn(() => false);

    expect(
      blockNoteInteractionPolicy.preferRichTextPaste({ defaultPasteHandler }),
    ).toBe(false);

    expect(defaultPasteHandler).toHaveBeenCalledWith({
      plainTextAsMarkdown: false,
      prioritizeMarkdownOverHTML: false,
    });
  });
});
