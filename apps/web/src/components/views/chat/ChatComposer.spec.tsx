import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ChatComposer } from './ChatComposer';

function defaultProps(overrides: Partial<Parameters<typeof ChatComposer>[0]> = {}) {
  return {
    input: '',
    onInputChange: vi.fn(),
    onSubmit: vi.fn(),
    onAbort: vi.fn(),
    isSending: false,
    isStreaming: false,
    chatError: null,
    ...overrides,
  };
}

describe('ChatComposer', () => {
  it('shows send button disabled when input is empty', () => {
    render(<ChatComposer {...defaultProps()} />);
    const button = screen.getByRole('button', { name: /전송/ });
    expect((button as HTMLButtonElement).disabled).toBe(true);
  });

  it('enables send button when input has non-whitespace text', () => {
    render(<ChatComposer {...defaultProps({ input: 'hello' })} />);
    const button = screen.getByRole('button', { name: /전송/ });
    expect((button as HTMLButtonElement).disabled).toBe(false);
  });

  it('fires onInputChange as user types', () => {
    const onInputChange = vi.fn();
    render(<ChatComposer {...defaultProps({ onInputChange })} />);
    fireEvent.change(screen.getByPlaceholderText('메시지를 입력하세요'), {
      target: { value: 'abc' },
    });
    expect(onInputChange).toHaveBeenCalledWith('abc');
  });

  it('calls onSubmit when the send button is clicked', () => {
    const onSubmit = vi.fn();
    render(<ChatComposer {...defaultProps({ input: 'hello', onSubmit })} />);
    fireEvent.click(screen.getByRole('button', { name: /전송/ }));
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it('submits via Enter key (without Shift)', () => {
    const onSubmit = vi.fn();
    render(<ChatComposer {...defaultProps({ input: 'hello', onSubmit })} />);
    fireEvent.keyDown(screen.getByPlaceholderText('메시지를 입력하세요'), {
      key: 'Enter',
    });
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it('does not submit when Shift+Enter is pressed', () => {
    const onSubmit = vi.fn();
    render(<ChatComposer {...defaultProps({ input: 'hello', onSubmit })} />);
    fireEvent.keyDown(screen.getByPlaceholderText('메시지를 입력하세요'), {
      key: 'Enter',
      shiftKey: true,
    });
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('does not submit via Enter when input is empty (mirrors disabled button)', () => {
    const onSubmit = vi.fn();
    render(<ChatComposer {...defaultProps({ input: '', onSubmit })} />);
    fireEvent.keyDown(screen.getByPlaceholderText('메시지를 입력하세요'), {
      key: 'Enter',
    });
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('does not submit via Enter when input is whitespace only', () => {
    const onSubmit = vi.fn();
    render(<ChatComposer {...defaultProps({ input: '   \n  ', onSubmit })} />);
    fireEvent.keyDown(screen.getByPlaceholderText('메시지를 입력하세요'), {
      key: 'Enter',
    });
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('does not submit via Enter while already sending', () => {
    const onSubmit = vi.fn();
    render(
      <ChatComposer
        {...defaultProps({ input: 'hello', isSending: true, onSubmit })}
      />,
    );
    // textarea is disabled while sending, but fireEvent.keyDown still dispatches
    // the event — the handler itself must bail out.
    fireEvent.keyDown(screen.getByPlaceholderText('메시지를 입력하세요'), {
      key: 'Enter',
    });
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('shows abort button while streaming', () => {
    const onAbort = vi.fn();
    render(
      <ChatComposer
        {...defaultProps({
          input: 'hello',
          isSending: true,
          isStreaming: true,
          onAbort,
        })}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /중단/ }));
    expect(onAbort).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('button', { name: /전송/ })).toBeNull();
  });

  it('shows processing indicator while sending non-stream', () => {
    render(
      <ChatComposer
        {...defaultProps({ input: 'hello', isSending: true, isStreaming: false })}
      />,
    );
    expect(screen.getByRole('button', { name: /처리 중/ })).not.toBeNull();
  });

  it('surfaces chatError banner above the textarea', () => {
    render(
      <ChatComposer {...defaultProps({ chatError: '전송 실패: 네트워크 오류' })} />,
    );
    expect(screen.getByText('전송 실패: 네트워크 오류')).not.toBeNull();
  });

  it('disables textarea while sending so user cannot edit mid-flight', () => {
    render(<ChatComposer {...defaultProps({ input: 'x', isSending: true })} />);
    const textarea = screen.getByPlaceholderText('메시지를 입력하세요');
    expect((textarea as HTMLTextAreaElement).disabled).toBe(true);
  });

  describe('slash command mode', () => {
    it('opens menu when input starts with "/"', () => {
      render(<ChatComposer {...defaultProps({ input: '/' })} />);
      expect(screen.getByRole('listbox')).not.toBeNull();
      // Should list AI tool options — sanity check a known one.
      expect(screen.getAllByText('아이두 통합검색').length).toBeGreaterThan(0);
    });

    it('filters items by query after "/"', () => {
      render(<ChatComposer {...defaultProps({ input: '/fmea' })} />);
      expect(screen.getByText('FMEA 비교')).not.toBeNull();
      expect(screen.queryByText('아이두 통합검색')).toBeNull();
    });

    it('hides the menu entirely when no tool matches (fall-through)', () => {
      // Palette must not remain visible for `/xyz-nope` — users might be
      // typing a literal slash prompt, not a command typo.
      render(<ChatComposer {...defaultProps({ input: '/xyz-nope' })} />);
      expect(screen.queryByRole('listbox')).toBeNull();
    });

    it('allows normal Enter-submit when slash buffer has no matches', () => {
      const onSubmit = vi.fn();
      render(
        <ChatComposer {...defaultProps({ input: '/xyz-nope', onSubmit })} />,
      );
      fireEvent.keyDown(screen.getByPlaceholderText('메시지를 입력하세요'), {
        key: 'Enter',
      });
      expect(onSubmit).toHaveBeenCalledTimes(1);
    });

    it('invokes onSelectTool on Enter with a matched item', () => {
      const onSelectTool = vi.fn();
      const onInputChange = vi.fn();
      render(
        <ChatComposer
          {...defaultProps({ input: '/fmea', onSelectTool, onInputChange })}
        />,
      );
      fireEvent.keyDown(screen.getByPlaceholderText('메시지를 입력하세요'), {
        key: 'Enter',
      });
      expect(onSelectTool).toHaveBeenCalledTimes(1);
      expect(onSelectTool.mock.calls[0][0].id).toBe('fmea-compare');
      // Always clears input so the menu closes deterministically.
      expect(onInputChange).toHaveBeenCalledWith('');
    });

    it('clears input on Escape to close the menu', () => {
      const onInputChange = vi.fn();
      render(
        <ChatComposer {...defaultProps({ input: '/fmea', onInputChange })} />,
      );
      fireEvent.keyDown(screen.getByPlaceholderText('메시지를 입력하세요'), {
        key: 'Escape',
      });
      expect(onInputChange).toHaveBeenCalledWith('');
    });

    it('selects on click and swallows blur so focus survives', () => {
      const onSelectTool = vi.fn();
      render(
        <ChatComposer {...defaultProps({ input: '/fmea', onSelectTool })} />,
      );
      fireEvent.click(screen.getByText('FMEA 비교'));
      expect(onSelectTool).toHaveBeenCalledTimes(1);
      expect(onSelectTool.mock.calls[0][0].id).toBe('fmea-compare');
    });

    it('moves highlight with ArrowDown and selects that item on Enter', () => {
      const onSelectTool = vi.fn();
      render(<ChatComposer {...defaultProps({ input: '/', onSelectTool })} />);
      const textarea = screen.getByPlaceholderText('메시지를 입력하세요');
      // Move from index 0 to 1.
      fireEvent.keyDown(textarea, { key: 'ArrowDown' });
      fireEvent.keyDown(textarea, { key: 'Enter' });
      // NAV_ITEMS AI section starts with 'chatbot' then 'search'.
      expect(onSelectTool.mock.calls[0][0].id).toBe('search');
    });

    it('wraps highlight upward with ArrowUp from index 0', () => {
      const onSelectTool = vi.fn();
      render(<ChatComposer {...defaultProps({ input: '/', onSelectTool })} />);
      const textarea = screen.getByPlaceholderText('메시지를 입력하세요');
      fireEvent.keyDown(textarea, { key: 'ArrowUp' });
      fireEvent.keyDown(textarea, { key: 'Enter' });
      // ArrowUp from 0 wraps to last AI item — assert it's a valid AI tool.
      const selected = onSelectTool.mock.calls[0][0];
      expect(selected.appId).toBe('ai');
    });

    it('does not open the menu for regular input', () => {
      render(<ChatComposer {...defaultProps({ input: 'hello world' })} />);
      expect(screen.queryByRole('listbox')).toBeNull();
    });

    it('disables the 전송 button in slash mode so mouse click cannot submit', () => {
      render(<ChatComposer {...defaultProps({ input: '/fmea' })} />);
      const sendButton = screen.getByRole('button', { name: /전송/ });
      expect((sendButton as HTMLButtonElement).disabled).toBe(true);
    });

    it('does not call onSubmit when form submit fires in slash mode', () => {
      // Covers the mouse/button submit path that bypasses the keydown handler.
      const onSubmit = vi.fn();
      render(<ChatComposer {...defaultProps({ input: '/fmea', onSubmit })} />);
      // Directly dispatch a submit event on the form to bypass the disabled button.
      const textarea = screen.getByPlaceholderText('메시지를 입력하세요');
      const form = textarea.closest('form');
      expect(form).not.toBeNull();
      fireEvent.submit(form as HTMLFormElement);
      expect(onSubmit).not.toHaveBeenCalled();
    });

    describe('literal slash-prefixed prompts (not commands)', () => {
      // Regression: any input starting with `/` used to open the palette and
      // block submission, making it impossible to send technical prompts like
      // `/api/v1/users`, `/tmp/log.txt`, or regex examples.

      it('treats "/api/v1/users" as a normal prompt (second slash bails out)', () => {
        const onSubmit = vi.fn();
        render(
          <ChatComposer {...defaultProps({ input: '/api/v1/users', onSubmit })} />,
        );
        expect(screen.queryByRole('listbox')).toBeNull();
        const sendButton = screen.getByRole('button', { name: /전송/ });
        expect((sendButton as HTMLButtonElement).disabled).toBe(false);
        fireEvent.click(sendButton);
        expect(onSubmit).toHaveBeenCalledTimes(1);
      });

      it('treats "/tmp/log.txt" as a normal prompt', () => {
        render(
          <ChatComposer {...defaultProps({ input: '/tmp/log.txt' })} />,
        );
        expect(screen.queryByRole('listbox')).toBeNull();
      });

      it('treats "/ fmea" (slash + space) as a normal prompt', () => {
        render(<ChatComposer {...defaultProps({ input: '/ fmea' })} />);
        expect(screen.queryByRole('listbox')).toBeNull();
      });

      it('treats a prompt starting with "/" followed by newline as normal', () => {
        render(<ChatComposer {...defaultProps({ input: '/\nmore text' })} />);
        expect(screen.queryByRole('listbox')).toBeNull();
      });

      it('still opens menu for identifier-only slash commands (/fmea, /fmea-compare)', () => {
        render(<ChatComposer {...defaultProps({ input: '/fmea-compare' })} />);
        expect(screen.getByRole('listbox')).not.toBeNull();
      });

      it('treats single-segment absolute paths like "/tmp" or "/etc" as normal prompts', () => {
        // Regression: the `^\/[^/\s]*$` heuristic on its own would classify
        // `/tmp` as a command buffer. Guarding on "at least one match" lets
        // these fall through to a normal chat submission.
        const onSubmit = vi.fn();
        render(<ChatComposer {...defaultProps({ input: '/tmp', onSubmit })} />);
        expect(screen.queryByRole('listbox')).toBeNull();
        const sendButton = screen.getByRole('button', { name: /전송/ });
        expect((sendButton as HTMLButtonElement).disabled).toBe(false);
        fireEvent.click(sendButton);
        expect(onSubmit).toHaveBeenCalledTimes(1);
      });

      it('allows "/etc" Enter submit when there are no matching tools', () => {
        const onSubmit = vi.fn();
        render(<ChatComposer {...defaultProps({ input: '/etc', onSubmit })} />);
        fireEvent.keyDown(screen.getByPlaceholderText('메시지를 입력하세요'), {
          key: 'Enter',
        });
        expect(onSubmit).toHaveBeenCalledTimes(1);
      });
    });
  });
});
