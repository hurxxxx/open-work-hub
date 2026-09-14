import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ChatComposer } from './ChatComposer';

describe('ChatComposer composition', () => {
  it('waits for Korean IME composition before submitting and keeps Shift+Enter for newlines', () => {
    const submit = vi.fn();
    render(
      <ChatComposer
        input="한글"
        onInputChange={vi.fn()}
        onSubmit={submit}
        onAbort={vi.fn()}
        isSending={false}
        isStreaming={false}
        chatError={null}
      />,
    );
    const input = screen.getByRole('textbox');
    fireEvent.keyDown(input, { key: 'Enter', isComposing: true });
    fireEvent.keyDown(input, { key: 'Enter', keyCode: 229 });
    fireEvent.keyDown(input, { key: 'Enter', shiftKey: true });
    expect(submit).not.toHaveBeenCalled();
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(submit).toHaveBeenCalledTimes(1);
  });
});
