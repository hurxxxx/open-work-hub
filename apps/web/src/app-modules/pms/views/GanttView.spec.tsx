import { fireEvent, render, screen } from '@testing-library/react';
import { act } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { PmsTask } from '../api/pms-api';
import { GanttView } from './GanttView';

function task(overrides: Partial<PmsTask> = {}): PmsTask {
  return {
    id: 'task-1',
    title: 'Root',
    status: 'todo',
    start_date: '2026-06-10',
    due_date: '2026-06-12',
    parent_id: null,
    board_position: 1000,
    ...overrides,
  } as PmsTask;
}

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  const promise = new Promise<T>((innerResolve) => {
    resolve = innerResolve;
  });
  return { promise, resolve };
}

describe('GanttView', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 5, 15));
    vi.stubGlobal(
      'ResizeObserver',
      class ResizeObserver {
        disconnect = vi.fn();
        observe = vi.fn();
        unobserve = vi.fn();
      },
    );
    Object.defineProperty(Element.prototype, 'setPointerCapture', {
      configurable: true,
      value: vi.fn(),
    });
    Object.defineProperty(Element.prototype, 'releasePointerCapture', {
      configurable: true,
      value: vi.fn(),
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('keeps the resized bar length while the schedule update is saving', async () => {
    const update = deferred<void>();
    const onUpdateIssue = vi.fn(() => update.promise);

    render(
      <GanttView canEdit onUpdateIssue={onUpdateIssue} tasks={[task()]} />,
    );

    const bar = screen.getByRole('button', { name: 'Root 상세 보기' });
    expect((bar as HTMLElement).style.width).toBe('120px');

    await act(async () => {
      fireEvent.mouseDown(screen.getByLabelText('Root 종료일 변경'), {
        clientX: 0,
      });
    });

    await act(async () => {
      fireEvent.mouseMove(document, { clientX: 80 });
      fireEvent.mouseUp(document);
    });

    expect(onUpdateIssue).toHaveBeenCalledWith('task-1', {
      due_date: '2026-06-14',
      start_date: '2026-06-10',
    });
    expect((bar as HTMLElement).style.width).toBe('200px');

    await act(async () => {
      update.resolve();
      await update.promise;
    });
  });

  it('collapses and expands subtasks under a parent task', () => {
    render(
      <GanttView
        tasks={[
          task({ id: 'parent', title: 'Parent' }),
          task({
            board_position: 2000,
            id: 'child',
            parent_id: 'parent',
            title: 'Child',
          }),
        ]}
      />,
    );

    expect(screen.queryByText('Child')).not.toBeNull();

    fireEvent.click(
      screen.getByRole('button', { name: 'Parent 하위 태스크 접기' }),
    );

    expect(screen.queryByText('Child')).toBeNull();

    fireEvent.click(
      screen.getByRole('button', { name: 'Parent 하위 태스크 펼치기' }),
    );

    expect(screen.queryByText('Child')).not.toBeNull();
  });

  it('opens task detail from the task name and gantt bar', () => {
    const onSelectIssue = vi.fn();
    render(<GanttView onSelectIssue={onSelectIssue} tasks={[task()]} />);

    fireEvent.click(screen.getByRole('button', { name: 'Root' }));
    expect(onSelectIssue).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'task-1' }),
    );

    onSelectIssue.mockClear();
    fireEvent.click(screen.getByRole('button', { name: 'Root 상세 보기' }));
    expect(onSelectIssue).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'task-1' }),
    );
  });

  it('applies a custom visible date range for cross-month tasks', () => {
    render(
      <GanttView
        tasks={[
          task({
            due_date: '2026-07-04',
            start_date: '2026-07-02',
            title: 'July task',
          }),
        ]}
      />,
    );

    expect(
      screen.queryByRole('button', { name: 'July task 상세 보기' }),
    ).toBeNull();
    expect(screen.queryByLabelText('종료일')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: '사용자 지정' }));
    fireEvent.change(screen.getByLabelText('종료일'), {
      target: { value: '2026-07-31' },
    });
    fireEvent.click(screen.getByRole('button', { name: '적용' }));

    const bar = screen.getByRole('button', { name: 'July task 상세 보기' });
    expect((bar as HTMLElement).style.left).toBe('1240px');
    expect((bar as HTMLElement).style.width).toBe('120px');
  });

  it('changes the visible range from month presets', () => {
    render(
      <GanttView
        tasks={[
          task({
            due_date: '2026-07-04',
            start_date: '2026-07-02',
            title: 'July task',
          }),
        ]}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '2개월' }));
    fireEvent.click(screen.getByRole('button', { name: '사용자 지정' }));

    expect((screen.getByLabelText('시작일') as HTMLInputElement).value).toBe(
      '2026-06-01',
    );
    expect((screen.getByLabelText('종료일') as HTMLInputElement).value).toBe(
      '2026-07-31',
    );
    expect(
      screen.queryByRole('button', { name: 'July task 상세 보기' }),
    ).not.toBeNull();
  });

  it('limits custom visible ranges to six months', () => {
    render(<GanttView tasks={[task()]} />);

    fireEvent.click(screen.getByRole('button', { name: '사용자 지정' }));
    fireEvent.change(screen.getByLabelText('종료일'), {
      target: { value: '2027-01-31' },
    });
    fireEvent.click(screen.getByRole('button', { name: '적용' }));
    fireEvent.click(screen.getByRole('button', { name: '사용자 지정' }));

    expect((screen.getByLabelText('시작일') as HTMLInputElement).value).toBe(
      '2026-06-01',
    );
    expect((screen.getByLabelText('종료일') as HTMLInputElement).value).toBe(
      '2026-11-30',
    );
  });

  it('moves the start date forward when dragging a max range end later', () => {
    render(<GanttView tasks={[task()]} />);

    fireEvent.click(screen.getByRole('button', { name: '6개월' }));
    fireEvent.click(screen.getByRole('button', { name: '사용자 지정' }));

    const endSlider = screen.getByLabelText('조회 종료 날짜 조정');
    endSlider.focus();
    for (let index = 0; index < 32; index += 1) {
      fireEvent.keyDown(endSlider, { key: 'ArrowRight' });
    }

    expect(
      (screen.getByLabelText('시작일') as HTMLInputElement).value >
        '2026-06-01',
    ).toBe(true);
    expect(
      (screen.getByLabelText('종료일') as HTMLInputElement).value >
        '2026-11-30',
    ).toBe(true);
  });

  it('moves the selected custom date range by dragging the range body', () => {
    render(<GanttView tasks={[task()]} />);

    fireEvent.click(screen.getByRole('button', { name: '사용자 지정' }));

    vi.spyOn(
      screen.getByTestId('pms-gantt-date-slider'),
      'getBoundingClientRect',
    ).mockReturnValue({
      bottom: 10,
      height: 10,
      left: 0,
      right: 546,
      toJSON: () => ({}),
      top: 0,
      width: 546,
      x: 0,
      y: 0,
    });

    const rangeBody = screen.getByTestId('pms-gantt-range-drag-handle');
    act(() => {
      rangeBody.dispatchEvent(
        new MouseEvent('pointerdown', {
          bubbles: true,
          button: 0,
          clientX: 196,
        }),
      );
      window.dispatchEvent(
        new MouseEvent('pointermove', { bubbles: true, clientX: 226 }),
      );
      window.dispatchEvent(
        new MouseEvent('pointerup', { bubbles: true, clientX: 226 }),
      );
    });

    expect((screen.getByLabelText('시작일') as HTMLInputElement).value).toBe(
      '2026-07-01',
    );
    expect((screen.getByLabelText('종료일') as HTMLInputElement).value).toBe(
      '2026-07-30',
    );
  });

  it('keeps the date slider in the custom panel and applies previous months', () => {
    render(
      <GanttView
        tasks={[
          task({
            due_date: '2026-04-04',
            start_date: '2026-04-02',
            title: 'April task',
          }),
        ]}
      />,
    );

    expect(screen.queryByLabelText('조회 시작 날짜 조정')).toBeNull();
    expect(
      screen.queryByRole('button', { name: 'April task 상세 보기' }),
    ).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: '사용자 지정' }));
    const startSlider = screen.getByLabelText('조회 시작 날짜 조정');
    startSlider.focus();
    for (let index = 0; index < 61; index += 1) {
      fireEvent.keyDown(startSlider, { key: 'ArrowLeft' });
    }

    expect((screen.getByLabelText('시작일') as HTMLInputElement).value).toBe(
      '2026-04-01',
    );
    expect((screen.getByLabelText('종료일') as HTMLInputElement).value).toBe(
      '2026-06-30',
    );
    expect(
      screen.queryByRole('button', { name: 'April task 상세 보기' }),
    ).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: '적용' }));

    expect(
      screen.queryByRole('button', { name: 'April task 상세 보기' }),
    ).not.toBeNull();
  });

  it('keeps the date header and rows in one horizontal scroll viewport', () => {
    render(<GanttView tasks={[task()]} />);

    const viewport = screen.getByTestId('pms-gantt-scroll-viewport');

    expect(viewport.querySelector('.sticky.top-0')).not.toBeNull();
    expect(
      viewport.contains(screen.getByRole('button', { name: 'Root 상세 보기' })),
    ).toBe(true);
  });

  it('does not open task detail when the gantt bar was dragged', async () => {
    const onSelectIssue = vi.fn();
    const onUpdateIssue = vi.fn();
    render(
      <GanttView
        canEdit
        onSelectIssue={onSelectIssue}
        onUpdateIssue={onUpdateIssue}
        tasks={[task()]}
      />,
    );

    const bar = screen.getByRole('button', { name: 'Root 상세 보기' });
    await act(async () => {
      fireEvent.mouseDown(bar, { clientX: 0 });
    });

    await act(async () => {
      fireEvent.mouseMove(document, { clientX: 40 });
      fireEvent.mouseUp(document);
    });

    fireEvent.click(bar);

    expect(onSelectIssue).not.toHaveBeenCalled();
    expect(onUpdateIssue).toHaveBeenCalledWith('task-1', {
      due_date: '2026-06-13',
      start_date: '2026-06-11',
    });
  });
});
