import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { listCalendarEvents } from './calendar-api';
import { CALENDAR_EVENTS_CHANGED_EVENT } from './calendar-events-changed';
import type { CalendarEvent } from './calendar-types';
import { useCalendarEvents } from './use-calendar-events';

vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({ token: 'token' }),
}));

vi.mock('./calendar-api', () => ({
  buildMockCalendarEvents: vi.fn(() => []),
  listCalendarEvents: vi.fn(),
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

function event(overrides: Partial<CalendarEvent> = {}): CalendarEvent {
  return {
    id: 'planner-event-event-1',
    title: 'Planning',
    start: '2026-08-29T01:00:00Z',
    end: '2026-08-29T02:00:00Z',
    allDay: false,
    sourceType: 'planner_event',
    sourceId: 'event-1',
    color: '#14b8a6',
    workspace: null,
    metadata: { plannerEventId: 'event-1' },
    ...overrides,
  };
}

function renderCalendarEvents() {
  return renderHook(() =>
    useCalendarEvents({
      from: '2026-08-01',
      to: '2026-09-01',
      useMockData: false,
    }),
  );
}

describe('useCalendarEvents mutation fencing', () => {
  beforeEach(() => {
    vi.mocked(listCalendarEvents).mockReset();
  });

  it('keeps an immediate upsert when an older list request resolves', async () => {
    const staleRequest = deferred<{ items: CalendarEvent[] }>();
    const canonicalRequest = deferred<{ items: CalendarEvent[] }>();
    vi.mocked(listCalendarEvents)
      .mockReturnValueOnce(staleRequest.promise)
      .mockReturnValueOnce(canonicalRequest.promise);
    const { result } = renderCalendarEvents();
    await waitFor(() => expect(listCalendarEvents).toHaveBeenCalledTimes(1));

    const localEvent = event({ title: 'Saved locally' });
    act(() => {
      result.current.upsertEvent(localEvent);
      result.current.refresh();
    });
    expect(result.current.events).toEqual([localEvent]);
    await waitFor(() => expect(listCalendarEvents).toHaveBeenCalledTimes(2));

    await act(async () => staleRequest.resolve({ items: [] }));
    expect(result.current.events).toEqual([localEvent]);

    const canonicalEvent = event({ title: 'Saved canonically' });
    await act(async () =>
      canonicalRequest.resolve({ items: [canonicalEvent] }),
    );
    await waitFor(() =>
      expect(result.current.events).toEqual([canonicalEvent]),
    );
  });

  it('keeps an immediate removal when an older list request resolves', async () => {
    const existingEvent = event();
    const staleRequest = deferred<{ items: CalendarEvent[] }>();
    const canonicalRequest = deferred<{ items: CalendarEvent[] }>();
    vi.mocked(listCalendarEvents)
      .mockResolvedValueOnce({ items: [existingEvent] })
      .mockReturnValueOnce(staleRequest.promise)
      .mockReturnValueOnce(canonicalRequest.promise);
    const { result } = renderCalendarEvents();
    await waitFor(() => expect(result.current.events).toEqual([existingEvent]));

    act(() => result.current.refresh());
    await waitFor(() => expect(listCalendarEvents).toHaveBeenCalledTimes(2));
    act(() => {
      result.current.removeEvent(existingEvent.id);
      result.current.refresh();
    });
    expect(result.current.events).toEqual([]);
    await waitFor(() => expect(listCalendarEvents).toHaveBeenCalledTimes(3));

    await act(async () => staleRequest.resolve({ items: [existingEvent] }));
    expect(result.current.events).toEqual([]);

    await act(async () => canonicalRequest.resolve({ items: [] }));
    await waitFor(() => expect(result.current.events).toEqual([]));
  });

  it('keeps the usable snapshot when a canonical refresh fails', async () => {
    const existingEvent = event();
    vi.mocked(listCalendarEvents)
      .mockResolvedValueOnce({ items: [existingEvent] })
      .mockRejectedValueOnce(new Error('Canonical refresh failed'));
    const { result } = renderCalendarEvents();
    await waitFor(() => expect(result.current.events).toEqual([existingEvent]));

    act(() => result.current.refresh());

    await waitFor(() =>
      expect(result.current.error).toBe('Canonical refresh failed'),
    );
    expect(result.current.events).toEqual([existingEvent]);
    expect(result.current.hasUsableSnapshot).toBe(true);
  });

  it('notifies independent calendar consumers after local mutations', async () => {
    vi.mocked(listCalendarEvents).mockResolvedValue({ items: [] });
    const listener = vi.fn();
    window.addEventListener(CALENDAR_EVENTS_CHANGED_EVENT, listener);
    const { result } = renderCalendarEvents();
    await waitFor(() => expect(listCalendarEvents).toHaveBeenCalledOnce());

    act(() => {
      result.current.upsertEvent(event());
      result.current.removeEvent('planner-event-event-1');
    });

    expect(listener).toHaveBeenCalledTimes(2);
    window.removeEventListener(CALENDAR_EVENTS_CHANGED_EVENT, listener);
  });
});
