import { act, fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { WhiteboardAccessBoundary } from './WhiteboardAccessBoundary';

const realtime = vi.hoisted(() => ({
  listeners: new Set<(event: { data: unknown }) => void>(),
  subscribe: vi.fn(() => vi.fn()),
  addEventListener: vi.fn(
    (_type: string, listener: (event: { data: unknown }) => void) => {
      realtime.listeners.add(listener);
      return () => {
        realtime.listeners.delete(listener);
      };
    },
  ),
}));
vi.mock('@/src/platform/realtime/realtime-provider', () => ({
  useRealtime: () => realtime,
}));

function Draft({ name }: { name: string }) {
  const [draft, setDraft] = useState('');
  return (
    <input
      aria-label={name}
      value={draft}
      onChange={(event) => setDraft(event.target.value)}
    />
  );
}
function emit(data: unknown) {
  act(() => {
    realtime.listeners.forEach((listener) => listener({ data }));
  });
}

beforeEach(() => {
  realtime.listeners.clear();
  vi.clearAllMocks();
});

describe('WhiteboardAccessBoundary', () => {
  it('discards only the changed board editor, keeps the subscription and unrelated form state', () => {
    render(
      <>
        <WhiteboardAccessBoundary boardId="changed" shareToken={null}>
          {() => <Draft name="changed" />}
        </WhiteboardAccessBoundary>
        <WhiteboardAccessBoundary boardId="unrelated" shareToken={null}>
          {() => <Draft name="unrelated" />}
        </WhiteboardAccessBoundary>
      </>,
    );
    fireEvent.change(screen.getByLabelText('changed'), {
      target: { value: 'protected draft' },
    });
    fireEvent.change(screen.getByLabelText('unrelated'), {
      target: { value: 'keep draft' },
    });
    emit({ whiteboard_id: 'changed' });
    expect((screen.getByLabelText('changed') as HTMLInputElement).value).toBe(
      '',
    );
    expect((screen.getByLabelText('unrelated') as HTMLInputElement).value).toBe(
      'keep draft',
    );
    expect(realtime.subscribe).toHaveBeenCalledTimes(2);
  });

  it('preserves the exact share-link lens on subscription and rejects unrelated/malformed events', () => {
    render(
      <WhiteboardAccessBoundary boardId="board" shareToken="link-lens">
        {() => <Draft name="draft" />}
      </WhiteboardAccessBoundary>,
    );
    expect(realtime.subscribe).toHaveBeenCalledWith({
      type: 'subscribe',
      topic: 'whiteboard.access',
      key: 'board',
      share_token: 'link-lens',
    });
    fireEvent.change(screen.getByLabelText('draft'), {
      target: { value: 'keep' },
    });
    for (const data of [null, {}, { whiteboard_id: 'other' }, 'board'])
      emit(data);
    expect((screen.getByLabelText('draft') as HTMLInputElement).value).toBe(
      'keep',
    );
  });

  it('fences callbacks synchronously on invalidation and when its access lens unmounts', () => {
    const callbacks: Array<() => boolean> = [];
    const { unmount } = render(
      <WhiteboardAccessBoundary boardId="board" shareToken={null}>
        {(isCurrent) => {
          callbacks.push(isCurrent);
          return <Draft name="draft" />;
        }}
      </WhiteboardAccessBoundary>,
    );
    const initial = callbacks.at(-1);
    if (!initial) throw new Error('Expected initial callback');
    expect(initial()).toBe(true);
    emit({ whiteboard_id: 'board' });
    expect(initial()).toBe(false);
    const current = callbacks.at(-1);
    if (!current) throw new Error('Expected current callback');
    expect(current()).toBe(true);
    unmount();
    expect(current()).toBe(false);
    expect(realtime.listeners.size).toBe(0);
  });
});
