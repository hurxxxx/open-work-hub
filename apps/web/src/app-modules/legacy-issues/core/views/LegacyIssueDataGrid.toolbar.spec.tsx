import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  CompactSelection,
  GridCellKind,
  type DataEditorProps,
  type DataEditorRef,
  type EditableGridCell,
  type GridCell,
  type GridSelection,
  type Item,
} from '@glideapps/glide-data-grid';
import {
  createLegacyIssueTextCell,
  LegacyIssueDataGrid,
  LegacyIssueDateCellEditor,
} from './LegacyIssueDataGrid';

const dataEditorState = vi.hoisted(() => ({
  keyDownKeys: [] as string[],
  props: null as DataEditorProps | null,
  scrollTo: vi.fn(),
}));

function createMockGridSelection(cell: Item): GridSelection {
  return {
    columns: CompactSelection.empty(),
    current: {
      cell,
      range: { height: 1, width: 1, x: cell[0], y: cell[1] },
      rangeStack: [],
    },
    rows: CompactSelection.empty(),
  };
}

function createMockGridRangeSelection(
  anchor: Item,
  target: Item,
): GridSelection {
  const x = Math.min(anchor[0], target[0]);
  const y = Math.min(anchor[1], target[1]);
  return {
    ...createMockGridSelection(anchor),
    current: {
      cell: anchor,
      range: {
        height: Math.abs(anchor[1] - target[1]) + 1,
        width: Math.abs(anchor[0] - target[0]) + 1,
        x,
        y,
      },
      rangeStack: [],
    },
  };
}

vi.mock('@glideapps/glide-data-grid', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@glideapps/glide-data-grid')>();
  const {
    forwardRef,
    useImperativeHandle,
    useRef: useReactRef,
  } = await import('react');
  const MockDataEditor = forwardRef<DataEditorRef, DataEditorProps>(
    (props, ref) => {
      const canvasRef = useReactRef<HTMLCanvasElement | null>(null);
      useImperativeHandle(
        ref,
        () =>
          ({
            focus: () => canvasRef.current?.focus(),
            getBounds: () => ({
              height: 30,
              width: 160,
              x: 0,
              y: 0,
            }),
            scrollTo: dataEditorState.scrollTo,
          }) as DataEditorRef,
        [canvasRef],
      );
      dataEditorState.props = props;
      const currentCell = props.gridSelection?.current?.cell ?? [0, 0];

      function moveSelection(event: React.KeyboardEvent<HTMLCanvasElement>) {
        let [columnIndex, rowIndex] = currentCell;
        if (event.key === 'ArrowDown') rowIndex += 1;
        if (event.key === 'ArrowLeft') columnIndex -= 1;
        if (event.key === 'ArrowRight') columnIndex += 1;
        if (event.key === 'ArrowUp') rowIndex -= 1;
        if (event.key === 'Tab') columnIndex += event.shiftKey ? -1 : 1;
        const target: Item = [
          Math.max(0, Math.min(props.columns.length - 1, columnIndex)),
          Math.max(0, Math.min(props.rows - 1, rowIndex)),
        ];
        props.onGridSelectionChange?.(
          event.shiftKey
            ? createMockGridRangeSelection(currentCell, target)
            : createMockGridSelection(target),
        );
      }

      return (
        <div data-testid="data-editor">
          <canvas
            ref={canvasRef}
            data-testid="data-grid-canvas"
            tabIndex={0}
            onFocus={() => {
              if (!props.gridSelection?.current) {
                props.onGridSelectionChange?.(createMockGridSelection([0, 0]));
              }
            }}
            onKeyDown={(event) => {
              dataEditorState.keyDownKeys.push(event.key);
              let cancelled = false;
              props.onKeyDown?.({
                altKey: event.altKey,
                bounds: {
                  height: 30,
                  width: 160,
                  x: 0,
                  y: 0,
                },
                cancel: () => {
                  cancelled = true;
                },
                ctrlKey: event.ctrlKey,
                key: event.key,
                keyCode: event.keyCode,
                location: currentCell,
                metaKey: event.metaKey,
                preventDefault: () => event.preventDefault(),
                rawEvent: event,
                shiftKey: event.shiftKey,
                stopPropagation: () => event.stopPropagation(),
              });
              if (cancelled) return;
              if (
                [
                  'ArrowDown',
                  'ArrowLeft',
                  'ArrowRight',
                  'ArrowUp',
                  'Tab',
                ].includes(event.key)
              ) {
                moveSelection(event);
              }
            }}
            onKeyUp={(event) => {
              props.onKeyUp?.({
                altKey: event.altKey,
                bounds: {
                  height: 30,
                  width: 160,
                  x: 0,
                  y: 0,
                },
                cancel: () => undefined,
                ctrlKey: event.ctrlKey,
                key: event.key,
                keyCode: event.keyCode,
                location: currentCell,
                metaKey: event.metaKey,
                preventDefault: () => event.preventDefault(),
                rawEvent: event,
                shiftKey: event.shiftKey,
                stopPropagation: () => event.stopPropagation(),
              });
            }}
          />
        </div>
      );
    },
  );
  MockDataEditor.displayName = 'MockDataEditor';
  return {
    ...actual,
    default: MockDataEditor,
  };
});

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  dataEditorState.keyDownKeys = [];
  dataEditorState.props = null;
  dataEditorState.scrollTo.mockReset();
});

describe('LegacyIssueDataGrid toolbar', () => {
  it('renders optional dataset controls in the grid toolbar', () => {
    render(
      <LegacyIssueDataGrid
        columns={[{ key: 'symptom', title: 'Symptom', width: 120 }]}
        emptyLabel="Empty"
        getCellValue={(record: { symptom: string }) => record.symptom}
        loading={false}
        loadingLabel="Loading"
        records={[{ id: 'record-1', symptom: 'A' }]}
        layoutId="legacy-issue-toolbar-slot-test"
        toolbarLeading={<span>1 / 50건</span>}
        toolbarTrailing={<button type="button">그리드 확대</button>}
      />,
    );

    expect(screen.getByText('1 / 50건')).not.toBeNull();
    expect(screen.getByRole('button', { name: '그리드 확대' })).not.toBeNull();
  });

  it('keeps dataset toolbar controls available for an empty result', () => {
    render(
      <LegacyIssueDataGrid
        columns={[{ key: 'symptom', title: 'Symptom', width: 120 }]}
        emptyLabel="Empty"
        getCellValue={(record: { symptom: string }) => record.symptom}
        loading={false}
        loadingLabel="Loading"
        records={[]}
        layoutId="legacy-issue-empty-toolbar-test"
        toolbarLeading={<button type="button">검색 초기화</button>}
      />,
    );

    expect(screen.getByRole('button', { name: '검색 초기화' })).not.toBeNull();
    expect(screen.getByText('Empty')).not.toBeNull();
  });

  it('does not turn the administrator column order into a personal override when only hiding a column', () => {
    const onPreferenceChange = vi.fn();
    render(
      <LegacyIssueDataGrid
        columns={[
          { key: 'a', title: 'A', width: 120 },
          { key: 'b', title: 'B', width: 120 },
        ]}
        defaultColumnOrder={['b', 'a']}
        emptyLabel="Empty"
        getCellValue={(record: { a: string; b: string }, columnKey) =>
          record[columnKey as 'a' | 'b']
        }
        loading={false}
        loadingLabel="Loading"
        onPreferenceChange={onPreferenceChange}
        preference={null}
        records={[{ a: 'A', b: 'B', id: 'record-1' }]}
        layoutId="legacy-issue-personal-hidden-test"
      />,
    );

    fireEvent.click(
      screen.getByRole('button', { name: 'coreBusiness.grid.columns' }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'A' }));

    expect(onPreferenceChange).toHaveBeenLastCalledWith({
      columnOrder: [],
      frozenColumnCount: 0,
      hiddenColumnKeys: ['a'],
    });
  });

  it('ignores legacy persisted sorts and reports the current in-memory order', async () => {
    window.localStorage.setItem(
      'legacy-issue-row-order-test.sorts',
      JSON.stringify([{ columnKey: 'symptom', direction: 'desc' }]),
    );
    const onVisibleRowsChange = vi.fn();
    const gridProps = {
      columns: [{ key: 'symptom', title: 'Symptom', width: 120 }],
      emptyLabel: 'Empty',
      getCellValue: (record: { symptom: string }) => record.symptom,
      loading: false,
      loadingLabel: 'Loading',
      onVisibleRowsChange,
      layoutId: 'legacy-issue-row-order-test',
    };

    const rendered = render(
      <LegacyIssueDataGrid
        {...gridProps}
        records={[
          { id: 'record-1', symptom: 'A' },
          { id: 'record-2', symptom: 'B' },
        ]}
      />,
    );

    await waitFor(() =>
      expect(onVisibleRowsChange).toHaveBeenLastCalledWith({
        recordIds: ['record-1', 'record-2'],
        layoutId: 'legacy-issue-row-order-test',
        viewApplied: false,
      }),
    );

    onVisibleRowsChange.mockClear();
    rendered.rerender(
      <LegacyIssueDataGrid
        {...gridProps}
        records={[
          { id: 'record-1', symptom: 'A' },
          { id: 'record-3', symptom: 'C' },
        ]}
      />,
    );

    expect(onVisibleRowsChange).toHaveBeenLastCalledWith({
      recordIds: ['record-1', 'record-3'],
      layoutId: 'legacy-issue-row-order-test',
      viewApplied: false,
    });
  });

  it('shows a column tooltip only while its header is hovered', async () => {
    render(
      <LegacyIssueDataGrid
        columns={[
          {
            key: 'registrant',
            title: '대책 작성자',
            tooltip: '정의: 해당 내용을 가장 잘 아는 담당자',
            width: 120,
          },
        ]}
        emptyLabel="Empty"
        getCellValue={(record: { registrant: string }) => record.registrant}
        loading={false}
        loadingLabel="Loading"
        records={[{ id: 'row-1', registrant: '홍길동' }]}
        layoutId="legacy-issue-header-tooltip-test"
      />,
    );
    await waitFor(() => {
      expect(dataEditorState.props?.onItemHovered).toBeTypeOf('function');
    });

    act(() => {
      dataEditorState.props?.onItemHovered?.({
        bounds: { height: 32, width: 120, x: 48, y: 100 },
        button: 0,
        buttons: 0,
        ctrlKey: false,
        group: '',
        isEdge: false,
        isTouch: false,
        kind: 'header',
        localEventX: 60,
        localEventY: 16,
        location: [0, -1],
        metaKey: false,
        scrollEdge: [0, 0],
        shiftKey: false,
      });
    });

    expect(screen.getByRole('tooltip').textContent).toBe(
      '정의: 해당 내용을 가장 잘 아는 담당자',
    );

    act(() => {
      dataEditorState.props?.onItemHovered?.({
        bounds: { height: 30, width: 120, x: 48, y: 132 },
        button: 0,
        buttons: 0,
        ctrlKey: false,
        isEdge: false,
        isFillHandle: false,
        isTouch: false,
        kind: 'cell',
        localEventX: 60,
        localEventY: 15,
        location: [0, 0],
        metaKey: false,
        scrollEdge: [0, 0],
        shiftKey: false,
      });
    });

    expect(screen.queryByRole('tooltip')).toBeNull();
  });

  it('omits record-detail controls for read-only result grids', () => {
    render(
      <LegacyIssueDataGrid
        columns={[{ key: 'vehicle', title: 'Vehicle', width: 120 }]}
        emptyLabel="Empty"
        getCellValue={(record: { vehicle: string }) => record.vehicle}
        loading={false}
        loadingLabel="Loading"
        readonlyColumnKeys={['vehicle']}
        records={[{ id: 'row-1', vehicle: 'GV80' }]}
        layoutId="legacy-issue-readonly-report-grid"
      />,
    );

    expect(
      screen.queryByRole('button', {
        name: 'coreBusiness.grid.openDetails',
      }),
    ).toBeNull();
  });

  it('starts with automatic row height switched off when no preference is stored', async () => {
    render(
      <LegacyIssueDataGrid
        columns={[{ key: 'symptom', title: 'Symptom', width: 120 }]}
        emptyLabel="Empty"
        getCellValue={(record: { symptom: string }, columnKey: string) =>
          columnKey === 'symptom' ? record.symptom : null
        }
        loading={false}
        loadingLabel="Loading"
        onRecordOpen={vi.fn()}
        records={[{ id: 'record-1', symptom: 'first\nsecond\nthird' }]}
        layoutId="legacy-issue-grid-default-test"
      />,
    );

    expect(
      (
        screen.getByRole('checkbox', {
          name: 'coreBusiness.grid.autoRowHeight',
        }) as HTMLInputElement
      ).checked,
    ).toBe(false);
    await waitFor(() => {
      expect(resolveRenderedRowHeight(0)).toBe(30);
    });
  });

  it('keeps automatic row height and scroll state in memory only', async () => {
    window.localStorage.setItem('legacy-issue-grid-test.autoRowHeight', 'true');
    const props = {
      columns: [{ key: 'symptom', title: 'Symptom', width: 120 }],
      emptyLabel: 'Empty',
      getCellValue: (record: { symptom: string }, columnKey: string) =>
        columnKey === 'symptom' ? record.symptom : null,
      loading: false,
      loadingLabel: 'Loading',
      onRecordOpen: vi.fn(),
      records: [
        { id: 'record-1', symptom: 'first\nsecond\nthird' },
        { id: 'record-2', symptom: 'single line' },
      ],
      layoutId: 'legacy-issue-grid-test',
    };
    const firstRender = render(<LegacyIssueDataGrid {...props} />);
    const checkbox = screen.getByRole('checkbox', {
      name: 'coreBusiness.grid.autoRowHeight',
    }) as HTMLInputElement;

    expect(checkbox.checked).toBe(false);
    await waitFor(() => {
      expect(screen.getByTestId('data-editor')).not.toBeNull();
      expect(resolveRenderedRowHeight(0)).toBe(30);
    });
    fireEvent.click(checkbox);
    expect(checkbox.checked).toBe(true);
    await waitFor(() => {
      expect(resolveRenderedRowHeight(0)).toBe(66);
    });
    dataEditorState.props?.onVisibleRegionChanged?.(
      { height: 1, width: 1, x: 0, y: 1 },
      0,
      0,
      {},
    );

    fireEvent.click(checkbox);

    expect(checkbox.checked).toBe(false);
    await waitFor(() => {
      expect(resolveRenderedRowHeight(0)).toBe(30);
      expect(dataEditorState.scrollTo).toHaveBeenCalledWith(
        0,
        1,
        'vertical',
        0,
        0,
        { vAlign: 'start' },
      );
    });
    dataEditorState.props?.onVisibleRegionChanged?.(
      { height: 1, width: 1, x: 0, y: 1 },
      0,
      0,
      {},
    );
    expect(window.localStorage.getItem('legacy-issue-grid-test.scroll')).toBe(
      null,
    );
    expect(
      window.localStorage.getItem('legacy-issue-grid-test.autoRowHeight'),
    ).toBe('true');

    fireEvent.click(checkbox);
    await waitFor(() => {
      expect(resolveRenderedRowHeight(0)).toBe(66);
    });
    fireEvent.click(checkbox);

    firstRender.unmount();
    dataEditorState.props = null;
    render(<LegacyIssueDataGrid {...props} />);

    expect(
      (
        screen.getByRole('checkbox', {
          name: 'coreBusiness.grid.autoRowHeight',
        }) as HTMLInputElement
      ).checked,
    ).toBe(false);
    await waitFor(() => {
      expect(resolveRenderedRowHeight(0)).toBe(30);
    });
  });

  it('normalizes date-cell paste before committing and clears blank dates as null', async () => {
    const onCellEdit = vi.fn();
    render(
      <LegacyIssueDataGrid
        columns={[
          {
            inputKind: 'date',
            key: 'occurrence_date',
            title: '발생일',
            width: 140,
          },
        ]}
        emptyLabel="Empty"
        getCellValue={(record: { occurrence_date: string }) =>
          record.occurrence_date
        }
        loading={false}
        loadingLabel="Loading"
        onCellEdit={onCellEdit}
        onRecordOpen={vi.fn()}
        records={[{ id: 'record-1', occurrence_date: '2026-07-20' }]}
        layoutId="legacy-issue-date-paste-test"
      />,
    );
    await waitFor(() => {
      expect(dataEditorState.props?.getCellContent).toBeTypeOf('function');
    });

    const currentCell = dataEditorState.props?.getCellContent([0, 0]);
    expect(currentCell).toBeDefined();
    expect(dataEditorState.props?.onPaste?.([0, 0], [['2026.7.24']])).toBe(
      true,
    );
    const pastedDate = dataEditorState.props?.coercePasteValue?.(
      '2026.7.24',
      currentCell as GridCell,
    );
    dataEditorState.props?.onCellsEdited?.([
      {
        location: [0, 0],
        value: pastedDate as EditableGridCell,
      },
    ]);
    await waitFor(() => {
      expect(onCellEdit).toHaveBeenCalledWith(
        expect.objectContaining({
          columnKey: 'occurrence_date',
          value: '2026-07-24',
        }),
      );
    });

    const clearedDate = dataEditorState.props?.coercePasteValue?.(
      '',
      currentCell as GridCell,
    );
    dataEditorState.props?.onCellsEdited?.([
      {
        location: [0, 0],
        value: clearedDate as EditableGridCell,
      },
    ]);
    await waitFor(() => {
      expect(onCellEdit).toHaveBeenLastCalledWith(
        expect.objectContaining({
          columnKey: 'occurrence_date',
          value: null,
        }),
      );
    });
  });

  it('opens the default text editor on the first text key without using that key as data', async () => {
    const onCellEdit = vi.fn();
    render(
      <LegacyIssueDataGrid
        columns={[
          { key: 'symptom', title: '현상', width: 160 },
          { key: 'cause', title: '원인', width: 160 },
        ]}
        emptyLabel="Empty"
        getCellValue={(record: { cause: string; symptom: string }, key) =>
          record[key as keyof typeof record]
        }
        loading={false}
        loadingLabel="Loading"
        onCellEdit={onCellEdit}
        onRecordOpen={vi.fn()}
        records={[{ id: 'record-1', cause: '', symptom: '' }]}
        layoutId="legacy-issue-korean-ime-test"
      />,
    );
    await waitFor(() => {
      expect(dataEditorState.props?.getCellContent).toBeTypeOf('function');
    });

    const cell = dataEditorState.props?.getCellContent([0, 0]);
    expect(cell).toMatchObject({
      kind: GridCellKind.Text,
    });
    expect(cell).not.toHaveProperty('activationBehaviorOverride');
    expect(dataEditorState.props?.cellActivationBehavior).toBe('second-click');
    expect(dataEditorState.props?.editOnType).toBe(false);
    expect(
      dataEditorState.props?.provideEditor?.(cell as GridCell),
    ).toBeUndefined();

    const canvas = screen.getByTestId('data-grid-canvas');
    act(() => canvas.focus());
    fireEvent.keyDown(canvas, { key: 'ArrowRight' });
    dataEditorState.keyDownKeys = [];
    const firstKey = new KeyboardEvent('keydown', {
      bubbles: true,
      cancelable: true,
      code: 'KeyD',
      key: 'd',
    });
    const allowed = canvas.dispatchEvent(firstKey);

    expect(allowed).toBe(false);
    expect(firstKey.defaultPrevented).toBe(true);
    expect(dataEditorState.keyDownKeys).toEqual(['d', 'Enter']);

    dataEditorState.keyDownKeys = [];
    expect(fireEvent.keyDown(canvas, { key: 'Process', keyCode: 229 })).toBe(
      false,
    );
    expect(dataEditorState.keyDownKeys).toEqual(['Process', 'Enter']);
    expect(onCellEdit).not.toHaveBeenCalled();
    expect(screen.queryByRole('textbox')).toBeNull();
  });

  it('leaves F5 and keyboard navigation on the grid canvas', async () => {
    const onCellEdit = vi.fn();
    render(
      <LegacyIssueDataGrid
        columns={[
          { key: 'symptom', title: '현상', width: 160 },
          { key: 'cause', title: '원인', width: 160 },
        ]}
        emptyLabel="Empty"
        getCellValue={(record: { cause: string; symptom: string }, key) =>
          record[key as keyof typeof record]
        }
        loading={false}
        loadingLabel="Loading"
        onCellEdit={onCellEdit}
        records={[{ id: 'record-1', cause: 'B', symptom: 'A' }]}
        layoutId="legacy-issue-keyboard-navigation-test"
      />,
    );

    const canvas = await screen.findByTestId('data-grid-canvas');
    act(() => canvas.focus());
    const f5 = new KeyboardEvent('keydown', {
      bubbles: true,
      cancelable: true,
      code: 'F5',
      key: 'F5',
    });
    const allowed = canvas.dispatchEvent(f5);

    expect(allowed).toBe(true);
    expect(f5.defaultPrevented).toBe(false);
    expect(document.activeElement).toBe(canvas);
    fireEvent.keyDown(canvas, { key: 'ArrowRight' });
    expect(dataEditorState.props?.gridSelection?.current?.cell).toEqual([1, 0]);
    expect(onCellEdit).not.toHaveBeenCalled();
  });

  it('opens date and select editors while skipping readonly and reference cells', async () => {
    render(
      <LegacyIssueDataGrid
        columns={[
          { key: 'readonly', title: '읽기 전용', width: 160 },
          {
            inputKind: 'date',
            key: 'date',
            title: '날짜',
            width: 160,
          },
          {
            key: 'category',
            options: ['A', 'B'],
            title: '분류',
            width: 160,
          },
          {
            key: 'owner',
            referenceKind: 'user',
            title: '담당자',
            width: 160,
          },
        ]}
        emptyLabel="Empty"
        getCellValue={(
          record: {
            category: string;
            date: string;
            owner: string;
            readonly: string;
          },
          key,
        ) => record[key as keyof typeof record]}
        loading={false}
        loadingLabel="Loading"
        onCellEdit={vi.fn()}
        readonlyColumnKeys={['readonly']}
        records={[
          {
            category: 'A',
            date: '2026-07-31',
            id: 'record-1',
            owner: '홍길동',
            readonly: '고정',
          },
        ]}
        layoutId="legacy-issue-direct-input-cell-kind-test"
      />,
    );

    const canvas = await screen.findByTestId('data-grid-canvas');
    act(() => canvas.focus());
    for (let columnIndex = 0; columnIndex < 4; columnIndex += 1) {
      dataEditorState.keyDownKeys = [];
      fireEvent.keyDown(canvas, { key: 'Process', keyCode: 229 });
      expect(dataEditorState.keyDownKeys).toEqual(
        columnIndex === 1 || columnIndex === 2
          ? ['Process', 'Enter']
          : ['Process'],
      );
      if (columnIndex < 3) {
        fireEvent.keyDown(canvas, { key: 'ArrowRight' });
      }
    }
  });

  it('keeps Shift range selection, copy, and range paste in canvas selection mode', async () => {
    const onCellEdit = vi.fn();
    render(
      <LegacyIssueDataGrid
        columns={[
          { key: 'symptom', title: '현상', width: 160 },
          { key: 'cause', title: '원인', width: 160 },
        ]}
        emptyLabel="Empty"
        getCellValue={(record: { cause: string; symptom: string }, key) =>
          record[key as keyof typeof record]
        }
        loading={false}
        loadingLabel="Loading"
        onCellEdit={onCellEdit}
        records={[{ id: 'record-1', cause: 'B', symptom: 'A' }]}
        layoutId="legacy-issue-keyboard-range-selection-test"
      />,
    );

    const canvas = await screen.findByTestId('data-grid-canvas');
    act(() => canvas.focus());
    fireEvent.keyDown(canvas, { key: 'ArrowRight', shiftKey: true });

    await waitFor(() => {
      expect(
        dataEditorState.props?.gridSelection?.current?.range,
      ).toMatchObject({
        height: 1,
        width: 2,
        x: 0,
        y: 0,
      });
    });
    expect(document.activeElement).toBe(canvas);
    expect(screen.queryByTestId('legacy-issue-direct-text-entry')).toBeNull();
    expect(onCellEdit).not.toHaveBeenCalled();

    fireEvent.keyDown(canvas, { ctrlKey: true, key: 'c' });
    expect(document.activeElement).toBe(canvas);
    expect(dataEditorState.props?.gridSelection?.current?.range.width).toBe(2);

    expect(dataEditorState.props?.onPaste?.([0, 0], [['같은 값']])).toBe(false);
    await waitFor(() => {
      expect(onCellEdit).toHaveBeenCalledWith(
        expect.objectContaining({
          columnKey: 'symptom',
          value: '같은 값',
        }),
      );
      expect(onCellEdit).toHaveBeenCalledWith(
        expect.objectContaining({
          columnKey: 'cause',
          value: '같은 값',
        }),
      );
    });
  });
});

describe('LegacyIssueDateCellEditor', () => {
  it('commits a native date value and exposes the configured column label', () => {
    const onChange = vi.fn();
    const onFinishedEditing = vi.fn();
    const value = createLegacyIssueTextCell('2026-07-20', false, {
      inputKind: 'date',
      inputLabel: '접수일',
    });

    render(
      <LegacyIssueDateCellEditor
        onChange={onChange}
        onFinishedEditing={onFinishedEditing}
        target={{ height: 30, width: 140, x: 0, y: 0 }}
        value={value}
      />,
    );
    const input = screen.getByLabelText('접수일') as HTMLInputElement;

    expect(input.type).toBe('date');
    fireEvent.change(input, { target: { value: '2026-07-24' } });
    fireEvent.blur(input);

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ data: '2026-07-24' }),
    );
    expect(onFinishedEditing).toHaveBeenCalledWith(
      expect.objectContaining({ data: '2026-07-24' }),
    );
  });

  it('commits an empty value for nullable dates and restores on Escape', () => {
    const onChange = vi.fn();
    const onFinishedEditing = vi.fn();
    const value = createLegacyIssueTextCell('2026-07-20', false, {
      inputKind: 'date',
      inputLabel: '접수일',
    });

    render(
      <LegacyIssueDateCellEditor
        onChange={onChange}
        onFinishedEditing={onFinishedEditing}
        target={{ height: 30, width: 140, x: 0, y: 0 }}
        value={value}
      />,
    );
    const input = screen.getByLabelText('접수일') as HTMLInputElement;

    fireEvent.change(input, { target: { value: '' } });
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ data: '' }),
    );
    fireEvent.keyDown(input, { key: 'Escape' });
    expect(onFinishedEditing).toHaveBeenCalledWith(value as GridCell);
  });

  it('commits an ISO date copied from another occurrence-date cell', () => {
    const onChange = vi.fn();
    const onFinishedEditing = vi.fn();
    const value = createLegacyIssueTextCell('2026-06-01', false, {
      inputKind: 'date',
      inputLabel: '발생일',
    });

    render(
      <LegacyIssueDateCellEditor
        onChange={onChange}
        onFinishedEditing={onFinishedEditing}
        target={{ height: 30, width: 140, x: 0, y: 0 }}
        value={value}
      />,
    );
    const input = screen.getByLabelText('발생일') as HTMLInputElement;

    fireEvent.paste(input, {
      clipboardData: {
        getData: (format: string) =>
          format === 'text/plain' ? '2026-07-24' : '',
      },
    });

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ data: '2026-07-24' }),
    );
    expect(onFinishedEditing).toHaveBeenCalledWith(
      expect.objectContaining({ data: '2026-07-24' }),
    );
  });
});

function resolveRenderedRowHeight(rowIndex: number): number | null {
  const rowHeight = dataEditorState.props?.rowHeight;
  if (typeof rowHeight === 'number') return rowHeight;
  if (typeof rowHeight === 'function') return rowHeight(rowIndex);
  return null;
}
