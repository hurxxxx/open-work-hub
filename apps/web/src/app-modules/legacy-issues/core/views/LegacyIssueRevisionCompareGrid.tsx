import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MutableRefObject,
} from 'react';
import { ChevronLeft, ChevronRight, Link2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import DataEditor, {
  GridCellKind,
  type DataEditorProps,
  type DataEditorRef,
  type GridCell,
  type GridColumn as GlideGridColumn,
} from '@glideapps/glide-data-grid';
import '@glideapps/glide-data-grid/dist/index.css';

import { APP_GRID_HIGHLIGHT_COLORS } from '@/src/platform/theme/app-color-fallbacks';
import {
  buildLegacyIssueRevisionCompareGridModel,
  getLegacyIssueRevisionCompareGridCellValue,
  getLegacyIssueRevisionCompareGridHighlight,
  getLegacyIssueRevisionCompareGridScrollOffset,
  LEGACY_ISSUE_COMPARE_ROW_FIELD_KEY,
  type LegacyIssueRevisionCompareGridChange,
  type LegacyIssueRevisionCompareGridModel,
  type LegacyIssueRevisionCompareGridScrollOffset,
  type LegacyIssueRevisionCompareGridSide,
  type LegacyIssueRevisionCompareView,
} from './legacy-issue-revision-compare-grid-model';

const COMPARE_GRID_ROW_HEIGHT = 32;
const COMPARE_GRID_HEADER_HEIGHT = 34;
const COMPARE_GRID_FROZEN_COLUMNS = 1;
const COMPARE_GRID_EMPTY_CELL: GridCell = {
  allowOverlay: false,
  copyData: '',
  data: '',
  displayData: '',
  kind: GridCellKind.Text,
  readonly: true,
};

const COMPARE_GRID_HIGHLIGHT_BG = {
  added: APP_GRID_HIGHLIGHT_COLORS.revisionAddedBg,
  modified: APP_GRID_HIGHLIGHT_COLORS.revisionModifiedBg,
  removed: APP_GRID_HIGHLIGHT_COLORS.revisionRemovedBg,
} as const;

export function LegacyIssueRevisionCompareGrid({
  compareResult,
  leftTitle,
  rightTitle,
}: {
  compareResult: LegacyIssueRevisionCompareView;
  leftTitle: string;
  rightTitle: string;
}) {
  const { t } = useTranslation(['apps']);
  const model = useMemo(
    () => buildLegacyIssueRevisionCompareGridModel(compareResult),
    [compareResult],
  );
  const [activeChangeIndex, setActiveChangeIndex] = useState(0);
  const [syncScroll, setSyncScroll] = useState(true);
  const [scrollOffsets, setScrollOffsets] = useState<
    Partial<
      Record<
        LegacyIssueRevisionCompareGridSide,
        LegacyIssueRevisionCompareGridScrollOffset
      >
    >
  >({});
  const leftGridRef = useRef<DataEditorRef | null>(null);
  const rightGridRef = useRef<DataEditorRef | null>(null);
  const syncingSideRef = useRef<LegacyIssueRevisionCompareGridSide | null>(
    null,
  );
  const columns = useMemo(
    () =>
      model.columns.map<GlideGridColumn>((column) => ({
        id: column.fieldKey,
        title:
          column.fieldKey === LEGACY_ISSUE_COMPARE_ROW_FIELD_KEY
            ? t('coreBusiness.revision.row')
            : column.title,
        width: column.width,
      })),
    [model.columns, t],
  );
  const activeChange =
    model.changes.length > 0
      ? model.changes[Math.min(activeChangeIndex, model.changes.length - 1)]
      : null;

  const scrollToChange = useCallback(
    (change: LegacyIssueRevisionCompareGridChange | null) => {
      if (!change) return;
      leftGridRef.current?.scrollTo(
        change.columnIndex,
        change.rowIndex,
        'both',
        24,
        24,
        { hAlign: 'center', vAlign: 'center' },
      );
      rightGridRef.current?.scrollTo(
        change.columnIndex,
        change.rowIndex,
        'both',
        24,
        24,
        { hAlign: 'center', vAlign: 'center' },
      );
    },
    [],
  );

  useEffect(() => {
    if (model.changes.length === 0) {
      setActiveChangeIndex(0);
      return;
    }
    setActiveChangeIndex(0);
    const firstChange = model.changes[0] ?? null;
    let innerFrameId: number | null = null;
    const outerFrameId = window.requestAnimationFrame(() => {
      innerFrameId = window.requestAnimationFrame(() => {
        scrollToChange(firstChange);
      });
    });
    return () => {
      window.cancelAnimationFrame(outerFrameId);
      if (innerFrameId !== null) {
        window.cancelAnimationFrame(innerFrameId);
      }
    };
  }, [model.changes, scrollToChange]);

  const moveChange = useCallback(
    (direction: -1 | 1) => {
      if (model.changes.length === 0) return;
      setActiveChangeIndex((current) => {
        const next =
          (current + direction + model.changes.length) % model.changes.length;
        scrollToChange(model.changes[next] ?? null);
        return next;
      });
    },
    [model.changes, scrollToChange],
  );

  const selectChange = useCallback(
    (index: number) => {
      const change = model.changes[index] ?? null;
      setActiveChangeIndex(index);
      scrollToChange(change);
    },
    [model.changes, scrollToChange],
  );

  const updateSyncedScrollOffset = useCallback(
    (
      side: LegacyIssueRevisionCompareGridSide,
      offset: LegacyIssueRevisionCompareGridScrollOffset,
    ) => {
      setScrollOffsets((current) => {
        const currentOffset = current[side];
        if (
          currentOffset?.scrollLeft === offset.scrollLeft &&
          currentOffset.scrollTop === offset.scrollTop
        ) {
          return current;
        }
        return { ...current, [side]: offset };
      });
    },
    [],
  );

  const handleVisibleRegionChanged = useCallback(
    (side: LegacyIssueRevisionCompareGridSide) =>
      ((range, tx, ty) => {
        if (!syncScroll) return;
        if (syncingSideRef.current === side) {
          syncingSideRef.current = null;
          return;
        }
        const targetSide: LegacyIssueRevisionCompareGridSide =
          side === 'left' ? 'right' : 'left';
        const offset = getLegacyIssueRevisionCompareGridScrollOffset({
          columns: model.columns,
          frozenColumnCount: COMPARE_GRID_FROZEN_COLUMNS,
          range,
          rowHeight: COMPARE_GRID_ROW_HEIGHT,
          tx,
          ty,
        });
        syncingSideRef.current = targetSide;
        updateSyncedScrollOffset(targetSide, offset);
        window.setTimeout(() => {
          if (syncingSideRef.current === targetSide) {
            syncingSideRef.current = null;
          }
        }, 100);
      }) satisfies NonNullable<DataEditorProps['onVisibleRegionChanged']>,
    [model.columns, syncScroll, updateSyncedScrollOffset],
  );

  return (
    <div className="grid h-full min-h-0 flex-1 gap-3 xl:grid-cols-[18rem_minmax(0,1fr)]">
      <aside className="flex min-h-44 min-w-0 flex-col overflow-hidden rounded-md border border-app-border bg-app-bg">
        <div className="flex h-9 shrink-0 items-center justify-between gap-2 border-b border-app-border bg-app-surface-sidebar px-3">
          <h3 className="app-text-caption font-semibold text-app-ink/75">
            {t('coreBusiness.revision.changeList')}
          </h3>
          <span className="app-text-micro text-app-ink/45">
            {t('coreBusiness.revision.changedCellCount', {
              count: model.changedCellCount,
            })}
          </span>
        </div>
        <div className="min-h-0 flex-1 overflow-auto p-1.5">
          {model.changes.map((change, index) => {
            const active = activeChange === change;
            const positionLabel = t(
              change.kind === 'row'
                ? 'coreBusiness.revision.changePositionRow'
                : 'coreBusiness.revision.changePositionCell',
              {
                column: change.columnIndex + 1,
                row: change.rowIndex + 1,
              },
            );
            return (
              <button
                key={`${change.stableRecordId}:${change.fieldKey}`}
                className={[
                  'mb-0.5 grid w-full gap-0.5 rounded-md px-2 py-1 text-left app-text-micro',
                  active
                    ? 'bg-app-accent/10 text-app-accent'
                    : 'text-app-ink/70 hover:bg-app-surface-hover',
                ].join(' ')}
                type="button"
                onClick={() => selectChange(index)}
              >
                <span className="flex min-w-0 items-center justify-between gap-2">
                  <span className="truncate font-semibold">{change.label}</span>
                  <span className="shrink-0 rounded border border-app-border bg-app-surface-sidebar px-1 font-mono text-[10px] leading-4 text-app-ink/55">
                    {positionLabel}
                  </span>
                </span>
                <span className="flex min-w-0 items-center gap-1 text-app-ink/45">
                  <span className="truncate">
                    {change.kind === 'row'
                      ? t('coreBusiness.revision.wholeRow')
                      : change.fieldLabel}
                  </span>
                  <span className="text-app-ink/25">/</span>
                  <span className="shrink-0">
                    {t(`coreBusiness.revision.diffStatus.${change.status}`, {
                      defaultValue: change.status,
                    })}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      </aside>

      <div className="flex min-h-0 min-w-0 flex-col gap-3">
        <div className="flex flex-wrap items-center justify-end gap-2">
          <label className="inline-flex h-8 items-center gap-1.5 rounded-md border border-app-border bg-app-bg px-2.5 app-text-caption text-app-ink/70">
            <input
              checked={syncScroll}
              className="size-4 accent-app-accent"
              type="checkbox"
              onChange={(event) => setSyncScroll(event.target.checked)}
            />
            <Link2 size={14} />
            <span>{t('coreBusiness.revision.syncScroll')}</span>
          </label>
          <button
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-app-border bg-app-bg px-2.5 app-text-caption text-app-ink/70 hover:bg-app-surface-hover disabled:opacity-45"
            disabled={model.changes.length === 0}
            type="button"
            onClick={() => moveChange(-1)}
          >
            <ChevronLeft size={14} />
            <span>{t('coreBusiness.revision.previousChange')}</span>
          </button>
          <button
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-app-border bg-app-bg px-2.5 app-text-caption text-app-ink/70 hover:bg-app-surface-hover disabled:opacity-45"
            disabled={model.changes.length === 0}
            type="button"
            onClick={() => moveChange(1)}
          >
            <span>{t('coreBusiness.revision.nextChange')}</span>
            <ChevronRight size={14} />
          </button>
        </div>
        <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-2">
          <CompareGridPane
            activeChange={activeChange}
            columns={columns}
            emptyValueLabel={t('coreBusiness.grid.emptyValue')}
            gridRef={leftGridRef}
            model={model}
            scrollOffset={scrollOffsets.left}
            side="left"
            title={leftTitle}
            onVisibleRegionChanged={handleVisibleRegionChanged('left')}
          />
          <CompareGridPane
            activeChange={activeChange}
            columns={columns}
            emptyValueLabel={t('coreBusiness.grid.emptyValue')}
            gridRef={rightGridRef}
            model={model}
            scrollOffset={scrollOffsets.right}
            side="right"
            title={rightTitle}
            onVisibleRegionChanged={handleVisibleRegionChanged('right')}
          />
        </div>
      </div>
    </div>
  );
}

function CompareGridPane({
  activeChange,
  columns,
  emptyValueLabel,
  gridRef,
  model,
  onVisibleRegionChanged,
  scrollOffset,
  side,
  title,
}: {
  activeChange: LegacyIssueRevisionCompareGridChange | null;
  columns: GlideGridColumn[];
  emptyValueLabel: string;
  gridRef: MutableRefObject<DataEditorRef | null>;
  model: LegacyIssueRevisionCompareGridModel;
  onVisibleRegionChanged: NonNullable<
    DataEditorProps['onVisibleRegionChanged']
  >;
  scrollOffset?: LegacyIssueRevisionCompareGridScrollOffset;
  side: LegacyIssueRevisionCompareGridSide;
  title: string;
}) {
  const getCellContent = useCallback<DataEditorProps['getCellContent']>(
    ([columnIndex, rowIndex]) => {
      const column = model.columns[columnIndex];
      const row = model.rows[rowIndex];
      if (!column || !row) return COMPARE_GRID_EMPTY_CELL;
      const value = getLegacyIssueRevisionCompareGridCellValue({
        column,
        row,
        side,
      });
      const highlight = getLegacyIssueRevisionCompareGridHighlight({
        column,
        row,
        side,
      });
      const active =
        activeChange?.rowIndex === rowIndex &&
        activeChange.columnIndex === columnIndex;
      return createCompareGridTextCell({
        active,
        emptyValueLabel,
        highlight,
        value,
      });
    },
    [activeChange, emptyValueLabel, model.columns, model.rows, side],
  );

  return (
    <section className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden rounded-md border border-app-border bg-app-bg">
      <header className="flex h-9 shrink-0 items-center border-b border-app-border bg-app-surface-sidebar px-3 app-text-caption font-semibold text-app-ink/70">
        {title}
      </header>
      <div className="min-h-0 flex-1">
        <DataEditor
          ref={gridRef}
          columns={columns}
          freezeColumns={1}
          getCellContent={getCellContent}
          headerHeight={COMPARE_GRID_HEADER_HEIGHT}
          height="100%"
          maxColumnWidth={460}
          minColumnWidth={96}
          onVisibleRegionChanged={onVisibleRegionChanged}
          rowHeight={COMPARE_GRID_ROW_HEIGHT}
          rowMarkers={{ kind: 'number', startIndex: 1, width: 48 }}
          rows={model.rows.length}
          smoothScrollX
          smoothScrollY
          scrollOffsetX={scrollOffset?.scrollLeft}
          scrollOffsetY={scrollOffset?.scrollTop}
          verticalBorder
          width="100%"
        />
      </div>
    </section>
  );
}

function createCompareGridTextCell({
  active,
  emptyValueLabel,
  highlight,
  value,
}: {
  active: boolean;
  emptyValueLabel: string;
  highlight: ReturnType<typeof getLegacyIssueRevisionCompareGridHighlight>;
  value: string | null;
}): GridCell {
  const rawValue = value ?? '';
  const displayData = rawValue.trim() ? rawValue : emptyValueLabel;
  const bgCell = active
    ? APP_GRID_HIGHLIGHT_COLORS.revisionActiveBg
    : highlight
      ? COMPARE_GRID_HIGHLIGHT_BG[highlight]
      : undefined;
  return {
    allowOverlay: true,
    allowWrapping: false,
    copyData: rawValue,
    data: displayData,
    displayData: displayData.replace(/\s+/g, ' ').slice(0, 1_000),
    kind: GridCellKind.Text,
    readonly: true,
    themeOverride: bgCell ? { bgCell } : undefined,
  };
}
