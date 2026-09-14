import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { useState } from 'react';
import { beforeEach, expect, it, vi } from 'vitest';

import { ChatResultSurface } from './ChatResultSurface';

const feedback = vi.hoisted(() => ({ error: vi.fn() }));
vi.mock('@open-work-hub/ui', async (original) => ({
  ...(await original<typeof import('@open-work-hub/ui')>()),
  useFeedback: () => feedback,
}));

beforeEach(() =>
  vi.stubGlobal(
    'matchMedia',
    vi.fn().mockReturnValue({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }),
  ),
);

function Surface() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)}>Open result</button>
      <textarea aria-label="Question" />
      {open ? (
        <ChatResultSurface title="Result" onClose={() => setOpen(false)}>
          <button onClick={() => setOpen(false)}>Close result</button>
        </ChatResultSurface>
      ) : null}
    </>
  );
}

it('keeps the wide conversation accessible and returns focus on Escape', () => {
  render(<Surface />);
  const trigger = screen.getByRole('button', { name: 'Open result' });
  trigger.focus();
  fireEvent.click(trigger);
  const result = screen.getByRole('complementary', { name: 'Result' });
  expect(document.activeElement).toBe(result);
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(screen.getByRole('textbox', { name: 'Question' })).toBeTruthy();
  fireEvent.keyDown(result, { key: 'Escape' });
  expect(screen.queryByRole('complementary')).toBeNull();
  expect(document.activeElement).toBe(trigger);
});

it('uses the shared modal on narrow screens and returns focus on close', async () => {
  vi.stubGlobal(
    'matchMedia',
    vi.fn().mockReturnValue({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }),
  );
  render(<Surface />);
  const trigger = screen.getByRole('button', { name: 'Open result' });
  trigger.focus();
  fireEvent.click(trigger);
  expect(await screen.findByRole('dialog', { name: 'Result' })).toBeTruthy();
  expect(screen.queryByRole('textbox', { name: 'Question' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Close result' }));
  await waitFor(() => expect(document.activeElement).toBe(trigger));
});

it('expands in place and enters/exits browser fullscreen without remounting the result', async () => {
  render(<Surface />);
  fireEvent.click(screen.getByRole('button', { name: 'Open result' }));
  const result = screen.getByRole('complementary');
  fireEvent.click(screen.getByRole('button', { name: '결과 패널 확대' }));
  expect(result.getAttribute('data-expanded')).toBe('true');
  fireEvent.click(screen.getByRole('button', { name: '결과 패널 폭 복원' }));
  expect(result.getAttribute('data-expanded')).toBe('false');
  result.requestFullscreen = vi.fn().mockImplementation(async () => {
    Object.defineProperty(document, 'fullscreenElement', {
      value: result,
      configurable: true,
    });
    document.dispatchEvent(new Event('fullscreenchange'));
  });
  document.exitFullscreen = vi.fn().mockImplementation(async () => {
    Object.defineProperty(document, 'fullscreenElement', {
      value: null,
      configurable: true,
    });
    document.dispatchEvent(new Event('fullscreenchange'));
  });
  await act(async () =>
    fireEvent.click(screen.getByRole('button', { name: '결과 전체 화면' })),
  );
  expect(document.fullscreenElement).toBe(result);
  fireEvent.keyDown(result, { key: 'Escape' });
  expect(screen.getByRole('complementary')).toBe(result);
  await act(async () =>
    fireEvent.click(screen.getByRole('button', { name: '전체 화면 종료' })),
  );
  expect(document.fullscreenElement).toBeNull();
  expect(screen.getByRole('complementary')).toBe(result);
});

it('reports rejected fullscreen through global feedback and preserves the panel', async () => {
  render(<Surface />);
  fireEvent.click(screen.getByRole('button', { name: 'Open result' }));
  const result = screen.getByRole('complementary');
  result.requestFullscreen = vi
    .fn()
    .mockRejectedValue(new Error('Unavailable'));
  fireEvent.click(screen.getByRole('button', { name: '결과 전체 화면' }));
  await waitFor(() => expect(feedback.error).toHaveBeenCalled());
  expect(screen.getByRole('complementary')).toBe(result);
});
