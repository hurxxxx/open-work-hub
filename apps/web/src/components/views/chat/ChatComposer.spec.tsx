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
});
