import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
  type SetStateAction,
} from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import {
  Check,
  ChevronDown,
  ChevronUp,
  Columns3,
  Filter,
  Loader2,
  Minus,
  PanelRightOpen,
  Pin,
  PinOff,
  Plus,
  RotateCcw,
  Search,
  Trash2,
  X,
} from 'lucide-react';
import DataEditor, {
  GridCellKind,
  type DataEditorProps,
  type DataEditorRef,
  type DrawCellCallback,
  type EditableGridCell,
  type GetRowThemeCallback,
  type GridCell,
  type GridColumn as GlideGridColumn,
  type GridMouseEventArgs,
  type Item,
  type Rectangle,
  type TextCell,
  type Theme as GlideTheme,
} from '@glideapps/glide-data-grid';
import '@glideapps/glide-data-grid/dist/index.css';

import { cn } from '@/src/lib/utils';
import {
  APP_COLOR_FALLBACKS,
  APP_GRID_HIGHLIGHT_COLORS,
} from '@/src/platform/theme/app-color-fallbacks';
import {
  buildLegacyIssuePastePlan,
  expandLegacyIssuePasteValuesForSelection,
  normalizeLegacyIssueDateInput,
} from './legacy-issue-grid-paste-model';

export type LegacyIssueGridColumn = {
  allowMultiple?: boolean;
  group?: string;
  inputKind?: 'date';
  key: string;
  options?: string[];
  referenceKind?: LegacyIssueGridReferenceKind;
  required?: boolean;
  title: string;
  tooltip?: string;
  width: number;
};

export type LegacyIssueGridReferenceKind = 'orgUnit' | 'user';

export type LegacyIssueGridSort = {
  columnKey: string;
  direction: 'asc' | 'desc';
  emptyPlacement?: 'first' | 'last';
};

export type LegacyIssueGridColumnLayout = {
  columnKeys: string[];
  layoutId: string;
};

export type LegacyIssueGridRowLayout = {
  layoutId: string;
  recordIds: string[];
  viewApplied: boolean;
};

export type LegacyIssueGridPreferenceValue = {
  columnOrder: string[];
  frozenColumnCount: number;
  hiddenColumnKeys: string[];
};

export type LegacyIssueGridPreferenceStatus =
  | 'error'
  | 'idle'
  | 'loading'
  | 'saving';

type LegacyIssueGridFilter = {
  selectedValues: string[] | null;
  text: string;
};

type LegacyIssueActiveCell = {
  columnKey: string;
  recordId: string;
} | null;

type LegacyIssueGridScrollPreference = {
  columnIndex: number;
  rowIndex: number;
  scrollLeft: number;
  scrollTop: number;
};

type LegacyIssueGridContextMenu = {
  columnCount: number | null;
  rowIndex: number | null;
  rowIndexes: number[];
  x: number;
  y: number;
} | null;

type LegacyIssueGridHeaderTooltip = {
  content: string;
  left: number;
  top: number;
} | null;

type LegacyIssueGridSelectionLike = {
  current?: {
    range: {
      height: number;
      width: number;
      x: number;
      y: number;
    };
  };
  rows?: {
    toArray: () => number[];
  };
} | null;

type LegacyIssueDataGridProps<TRecord> = {
  blankRowDefaultValues?: Record<string, string | null>;
  changedCellKeys?: readonly string[];
  columns: LegacyIssueGridColumn[];
  detailOpen?: boolean;
  emptyLabel: string;
  getCellValue: (
    record: TRecord,
    columnKey: string,
  ) => string | null | undefined;
  loading: boolean;
  loadingLabel: string;
  onCellClick?: (params: {
    columnKey: string;
    record: TRecord;
  }) => boolean | void;
  onCellEdit?: (params: {
    columnKey: string;
    record: TRecord;
    value: string | null;
  }) => void | Promise<void>;
  onCellBatchEdit?: (params: {
    edits: Array<{
      columnKey: string;
      record: TRecord;
      value: string | null;
    }>;
  }) => void | Promise<void>;
  onReferenceCellEditRequest?: (params: {
    allowMultiple: boolean;
    columnKey: string;
    record: TRecord;
    referenceKind: LegacyIssueGridReferenceKind;
  }) => void;
  onCreateRows?: (params: {
    values: Array<Record<string, string | null>>;
  }) => number | void | Promise<number | void>;
  onDeleteRows?: (records: TRecord[]) => void | Promise<void>;
  onPreferenceChange?: (preference: LegacyIssueGridPreferenceValue) => void;
  onPreferenceReset?: () => void;
  onPreferenceRetry?: () => void;
  onVisibleColumnKeysChange?: (layout: LegacyIssueGridColumnLayout) => void;
  onVisibleRowsChange?: (layout: LegacyIssueGridRowLayout) => void;
  onRecordOpen?: (record: TRecord) => void;
  highlightedColumnKeys?: readonly string[];
  recordOpenIcon?: ReactNode;
  recordOpenLabel?: string;
  readonlyColumnKeys?: string[];
  defaultColumnOrder?: string[];
  onAddBlankRows?: (count?: number) => void;
  onRemoveBlankRows?: (rowIndexes: number[]) => void;
  blankRowCount?: number;
  records: TRecord[];
  revisionKey?: string | null;
  layoutId: string;
  preference?: LegacyIssueGridPreferenceValue | null;
  preferenceControlsDisabled?: boolean;
  preferenceStatus?: LegacyIssueGridPreferenceStatus;
  toolbarLeading?: ReactNode;
  toolbarTrailing?: ReactNode;
};

const GRID_GROUP_HEADER_HEIGHT = 30;
const GRID_HEADER_HEIGHT = 32;
const GRID_ROW_HEIGHT = 30;
const GRID_TEXT_HORIZONTAL_PADDING = 18;
const GRID_TEXT_LINE_HEIGHT = 18;
const GRID_TEXT_VERTICAL_PADDING = 12;
const GRID_MAX_AUTO_LINE_COUNT = 12;
const GRID_MAX_AUTO_ROW_HEIGHT =
  GRID_TEXT_VERTICAL_PADDING + GRID_MAX_AUTO_LINE_COUNT * GRID_TEXT_LINE_HEIGHT;
const GRID_ROW_MARKER_WIDTH = 48;
const GRID_MIN_COLUMN_WIDTH = 64;
const GRID_MAX_COLUMN_WIDTH = 900;
const LEGACY_GRID_BOUNDARY_SHADOW = 'var(--ui-shadow-legacy-grid-boundary)';

const EMPTY_GRID_CELL: TextCell = {
  allowOverlay: false,
  data: '',
  displayData: '',
  kind: GridCellKind.Text,
  readonly: true,
};
const EMPTY_BLANK_ROW_DEFAULT_VALUES: Record<string, string | null> = {};
export function LegacyIssueDataGrid<TRecord>({
  blankRowDefaultValues = EMPTY_BLANK_ROW_DEFAULT_VALUES,
  changedCellKeys = [],
  columns,
  detailOpen = false,
  emptyLabel,
  getCellValue,
  loading,
  loadingLabel,
  onCellClick,
  onCellBatchEdit,
  onCellEdit,
  onReferenceCellEditRequest,
  onCreateRows,
  onDeleteRows,
  onPreferenceChange,
  onPreferenceReset,
  onPreferenceRetry,
  onVisibleColumnKeysChange,
  onVisibleRowsChange,
  onAddBlankRows,
  onRemoveBlankRows,
  onRecordOpen,
  highlightedColumnKeys = [],
  recordOpenIcon,
  recordOpenLabel,
  readonlyColumnKeys = [],
  defaultColumnOrder = [],
  blankRowCount = 0,
  records,
  revisionKey = null,
  layoutId,
  preference,
  preferenceControlsDisabled: preferenceControlsExplicitlyDisabled = false,
  preferenceStatus = 'idle',
  toolbarLeading,
  toolbarTrailing,
}: LegacyIssueDataGridProps<TRecord>) {
  const { t } = useTranslation(['apps']);
  const dataEditorRef = useRef<DataEditorRef | null>(null);
  const [dataEditorContainerElement, setDataEditorContainerElement] =
    useState<HTMLDivElement | null>(null);
  const [dataEditorHeight, setDataEditorHeight] = useState<number | null>(null);
  const readonlyColumnKeySet = useMemo(
    () => new Set(readonlyColumnKeys),
    [readonlyColumnKeys],
  );
  const highlightedColumnKeySet = useMemo(
    () => new Set(highlightedColumnKeys),
    [highlightedColumnKeys],
  );
  const changedCellKeySet = useMemo(
    () => new Set(changedCellKeys),
    [changedCellKeys],
  );
  const [columnWidths, setColumnWidths] = useState<Record<string, number>>({});
  const [autoRowHeightColumnWidths, setAutoRowHeightColumnWidths] = useState<
    Record<string, number>
  >({});
  const [autoRowHeightEnabled, setAutoRowHeightEnabled] = useState(false);
  const [hiddenColumnKeys, setHiddenColumnKeys] = useState<string[]>(
    preference?.hiddenColumnKeys ?? [],
  );
  const [columnOrder, setColumnOrder] = useState<string[]>(
    resolveLegacyIssueGridPersonalizedColumnOrder({
      columns,
      defaultColumnOrder,
      personalizedColumnOrder: preference?.columnOrder ?? null,
    }),
  );
  const [columnOrderUserOverride, setColumnOrderUserOverride] = useState(
    Boolean(preference?.columnOrder.length),
  );
  const [frozenColumnCount, setFrozenColumnCount] = useState(
    preference?.frozenColumnCount ?? 0,
  );
  const [sorts, setSorts] = useState<LegacyIssueGridSort[]>([]);
  const [filters, setFilters] = useState<Record<string, LegacyIssueGridFilter>>(
    {},
  );
  const [filterMenu, setFilterMenu] = useState<{
    columnKey: string;
    x: number;
    y: number;
  } | null>(null);
  const [filterSearch, setFilterSearch] = useState('');
  const [columnsMenuOpen, setColumnsMenuOpen] = useState(false);
  const [gridSearchOpen, setGridSearchOpen] = useState(false);
  const [contextMenu, setContextMenu] =
    useState<LegacyIssueGridContextMenu>(null);
  const [headerTooltip, setHeaderTooltip] =
    useState<LegacyIssueGridHeaderTooltip>(null);
  const [gridSelection, setGridSelection] = useState<
    | Parameters<NonNullable<DataEditorProps['onGridSelectionChange']>>[0]
    | undefined
  >(undefined);
  const gridSelectionRef = useRef<
    Parameters<NonNullable<DataEditorProps['onGridSelectionChange']>>[0] | null
  >(null);
  const [blankRowDrafts, setBlankRowDrafts] = useState<
    Array<Record<string, string | null>>
  >([]);
  const [activeSearchCell, setActiveSearchCell] = useState<Item | null>(null);
  const [dirtyCells, setDirtyCells] = useState<Record<string, string>>({});
  const [activeCell, setActiveCell] = useState<LegacyIssueActiveCell>(null);
  const [selectedRecordId, setSelectedRecordId] = useState<string | null>(null);
  const gridTheme = useLegacyIssueGridTheme();
  const columnsRef = useRef(columns);
  columnsRef.current = columns;
  const defaultColumnOrderRef = useRef(defaultColumnOrder);
  const preferenceRef = useRef(preference);
  preferenceRef.current = preference;
  const onVisibleColumnKeysChangeRef = useRef(onVisibleColumnKeysChange);
  const onVisibleRowsChangeRef = useRef(onVisibleRowsChange);
  const lastVisibleColumnLayoutRef = useRef<LegacyIssueGridColumnLayout | null>(
    null,
  );
  const lastVisibleRowLayoutRef = useRef<LegacyIssueGridRowLayout | null>(null);
  const latestScrollPreferenceRef =
    useRef<LegacyIssueGridScrollPreference | null>(null);
  const pendingAutoRowHeightScrollRef =
    useRef<LegacyIssueGridScrollPreference | null>(null);

  onVisibleColumnKeysChangeRef.current = onVisibleColumnKeysChange;
  onVisibleRowsChangeRef.current = onVisibleRowsChange;

  useEffect(() => {
    defaultColumnOrderRef.current = defaultColumnOrder;
  }, [defaultColumnOrder]);

  useLayoutEffect(() => {
    const element = dataEditorContainerElement;
    if (!element) return;

    const updateHeight = () => {
      const nextHeight = Math.max(
        1,
        Math.floor(element.getBoundingClientRect().height),
      );
      setDataEditorHeight((current) =>
        current === nextHeight ? current : nextHeight,
      );
    };

    updateHeight();
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', updateHeight);
      return () => window.removeEventListener('resize', updateHeight);
    }

    const observer = new ResizeObserver(updateHeight);
    observer.observe(element);
    return () => observer.disconnect();
  }, [dataEditorContainerElement]);

  useEffect(() => {
    setColumnWidths({});
    setAutoRowHeightColumnWidths({});
    setAutoRowHeightEnabled(false);
    setHiddenColumnKeys(preferenceRef.current?.hiddenColumnKeys ?? []);
    setColumnOrder(
      resolveLegacyIssueGridPersonalizedColumnOrder({
        columns: columnsRef.current,
        defaultColumnOrder: defaultColumnOrderRef.current,
        personalizedColumnOrder: preferenceRef.current?.columnOrder ?? null,
      }),
    );
    setColumnOrderUserOverride(
      Boolean(preferenceRef.current?.columnOrder.length),
    );
    setFrozenColumnCount(preferenceRef.current?.frozenColumnCount ?? 0);
    setSorts([]);
    setFilters({});
    setFilterMenu(null);
    setColumnsMenuOpen(false);
    setGridSearchOpen(false);
    setContextMenu(null);
    setHeaderTooltip(null);
    setGridSelection(undefined);
    gridSelectionRef.current = null;
    setSelectedRecordId(null);
    setBlankRowDrafts([]);
    setActiveSearchCell(null);
    setDirtyCells({});
    setActiveCell(null);
    latestScrollPreferenceRef.current = null;
    pendingAutoRowHeightScrollRef.current = null;
  }, [layoutId]);

  useEffect(() => {
    if (preference === undefined) return;
    setHiddenColumnKeys(
      resolveLegacyIssueGridHiddenColumnKeys(
        columns,
        preference?.hiddenColumnKeys ?? [],
      ),
    );
    setColumnOrder(
      resolveLegacyIssueGridPersonalizedColumnOrder({
        columns,
        defaultColumnOrder,
        personalizedColumnOrder: preference?.columnOrder ?? null,
      }),
    );
    setColumnOrderUserOverride(Boolean(preference?.columnOrder.length));
    setFrozenColumnCount(preference?.frozenColumnCount ?? 0);
  }, [columns, defaultColumnOrder, preference]);

  useEffect(() => {
    if (columnOrderUserOverride) {
      setColumnOrder((current) =>
        appendMissingLegacyIssueGridColumnKeys(current, columns),
      );
      return;
    }
    setColumnOrder((current) =>
      resolveLegacyIssueGridColumnOrderState(
        current,
        resolveLegacyIssueGridPersonalizedColumnOrder({
          columns,
          defaultColumnOrder,
          personalizedColumnOrder: null,
        }),
      ),
    );
  }, [columnOrderUserOverride, columns, defaultColumnOrder]);

  const updateSorts = useCallback(
    (nextSorts: SetStateAction<LegacyIssueGridSort[]>) => {
      setSorts((current) => {
        const resolved =
          typeof nextSorts === 'function' ? nextSorts(current) : nextSorts;
        return normalizeGridSortPreferences(resolved);
      });
    },
    [],
  );

  useEffect(() => {
    setDirtyCells({});
    setActiveCell(null);
    setGridSelection(undefined);
    gridSelectionRef.current = null;
    setSelectedRecordId(null);
    setBlankRowDrafts([]);
  }, [revisionKey]);

  const hiddenColumnKeySet = useMemo(
    () => new Set(hiddenColumnKeys),
    [hiddenColumnKeys],
  );
  const orderedColumns = useMemo(
    () => applyGridColumnOrder(columns, columnOrder),
    [columnOrder, columns],
  );

  const visibleColumns = useMemo(
    () =>
      resolveLegacyIssueVisibleGridColumns({
        columns: orderedColumns,
        hiddenColumnKeys: hiddenColumnKeySet,
      }),
    [hiddenColumnKeySet, orderedColumns],
  );

  const visibleColumnKeysChangeEnabled = Boolean(onVisibleColumnKeysChange);
  useEffect(() => {
    if (!visibleColumnKeysChangeEnabled) {
      lastVisibleColumnLayoutRef.current = null;
      return;
    }
    const nextLayout = {
      columnKeys: visibleColumns.map((column) => column.key),
      layoutId,
    };
    if (
      isLegacyIssueGridColumnLayoutEqual(
        lastVisibleColumnLayoutRef.current,
        nextLayout,
      )
    ) {
      return;
    }
    lastVisibleColumnLayoutRef.current = nextLayout;
    onVisibleColumnKeysChangeRef.current?.(nextLayout);
  }, [layoutId, visibleColumnKeysChangeEnabled, visibleColumns]);

  const visibleRecords = useMemo(
    () =>
      applyGridView({
        columns,
        filters,
        getCellValue,
        records,
        sorts,
      }),
    [columns, filters, getCellValue, records, sorts],
  );

  const visibleRowsChangeEnabled = Boolean(onVisibleRowsChange);
  useLayoutEffect(() => {
    if (!visibleRowsChangeEnabled) {
      lastVisibleRowLayoutRef.current = null;
      return;
    }
    const nextLayout = {
      layoutId,
      recordIds: visibleRecords
        .map(getRecordGridId)
        .filter((recordId): recordId is string => recordId !== null),
      viewApplied:
        sorts.length > 0 || Object.values(filters).some(isFilterActive),
    };
    if (
      isLegacyIssueGridRowLayoutEqual(
        lastVisibleRowLayoutRef.current,
        nextLayout,
      )
    ) {
      return;
    }
    lastVisibleRowLayoutRef.current = nextLayout;
    onVisibleRowsChangeRef.current?.(nextLayout);
  }, [filters, layoutId, sorts, visibleRecords, visibleRowsChangeEnabled]);

  const hasCreateRows = Boolean(onCreateRows) && blankRowCount > 0;
  const blankRowsBefore = hasCreateRows ? blankRowCount : 0;
  const requiredColumnKeySet = useMemo(
    () =>
      new Set(
        columns
          .filter((column) => Boolean(column.required))
          .map((column) => column.key),
      ),
    [columns],
  );
  useEffect(() => {
    setBlankRowDrafts((current) =>
      resizeBlankRowDrafts(current, blankRowsBefore),
    );
  }, [blankRowsBefore]);
  const draftRowsWithData = useMemo(
    () =>
      blankRowDrafts
        .map((values, rowIndex) => ({
          missingColumnKeys: getRequiredMissingColumnKeysForBlankRowDraft({
            requiredColumnKeys: requiredColumnKeySet,
            values: {
              ...blankRowDefaultValues,
              ...values,
            },
          }),
          rowIndex,
          values,
        }))
        .filter((draft) => blankRowDraftHasData(draft.values)),
    [blankRowDefaultValues, blankRowDrafts, requiredColumnKeySet],
  );
  const draftRowsReadyToApply = useMemo(
    () =>
      draftRowsWithData.filter((draft) => draft.missingColumnKeys.length === 0),
    [draftRowsWithData],
  );
  const hasInvalidDraftRows =
    draftRowsWithData.length > draftRowsReadyToApply.length;
  const canApplyDraftRows =
    Boolean(onCreateRows) &&
    draftRowsReadyToApply.length > 0 &&
    !hasInvalidDraftRows;
  const rows = visibleRecords.length + blankRowsBefore;
  const autoRowHeightColumns = useMemo(
    () =>
      visibleColumns.map((column) => ({
        key: column.key,
        width: autoRowHeightColumnWidths[column.key] ?? column.width,
      })),
    [autoRowHeightColumnWidths, visibleColumns],
  );
  const rowHeights = useMemo(() => {
    if (!autoRowHeightEnabled) {
      return Array.from({ length: rows }, () => GRID_ROW_HEIGHT);
    }
    const heights: number[] = [];
    for (let rowIndex = 0; rowIndex < blankRowsBefore; rowIndex += 1) {
      const values = {
        ...blankRowDefaultValues,
        ...(blankRowDrafts[rowIndex] ?? {}),
      };
      heights.push(
        getLegacyIssueGridRowHeight({
          columns: autoRowHeightColumns,
          getCellValue: (columnKey) => values[columnKey],
        }),
      );
    }
    for (const record of visibleRecords) {
      heights.push(
        getLegacyIssueGridRowHeight({
          columns: autoRowHeightColumns,
          getCellValue: (columnKey) => getCellValue(record, columnKey),
        }),
      );
    }
    return heights;
  }, [
    autoRowHeightEnabled,
    autoRowHeightColumns,
    blankRowDefaultValues,
    blankRowsBefore,
    blankRowDrafts,
    getCellValue,
    rows,
    visibleRecords,
  ]);
  const rowOffsets = useMemo(
    () => buildLegacyIssueGridRowOffsets(rowHeights),
    [rowHeights],
  );
  const rowHeightsRef = useRef(rowHeights);
  rowHeightsRef.current = rowHeights;
  const getRowHeight = useCallback(
    (rowIndex: number) => rowHeightsRef.current[rowIndex] ?? GRID_ROW_HEIGHT,
    [],
  );
  useLayoutEffect(() => {
    const preference = pendingAutoRowHeightScrollRef.current;
    if (
      !preference ||
      dataEditorHeight === null ||
      rows === 0 ||
      visibleColumns.length === 0
    ) {
      return;
    }
    pendingAutoRowHeightScrollRef.current = null;
    dataEditorRef.current?.scrollTo(
      Math.min(preference.columnIndex, Math.max(0, visibleColumns.length - 1)),
      Math.min(preference.rowIndex, rows - 1),
      'vertical',
      0,
      0,
      { vAlign: 'start' },
    );
  }, [autoRowHeightEnabled, dataEditorHeight, rows, visibleColumns.length]);
  const maxFrozenColumnCount = visibleColumns.length;
  const preferenceControlsDisabled =
    preferenceControlsExplicitlyDisabled || preferenceStatus === 'loading';
  const effectiveFrozenColumnCount = Math.min(
    Math.max(0, frozenColumnCount),
    maxFrozenColumnCount,
  );
  const frozenColumnBoundaryX =
    effectiveFrozenColumnCount > 0
      ? GRID_ROW_MARKER_WIDTH +
        sumGridColumnWidths(
          visibleColumns.slice(0, effectiveFrozenColumnCount).map((column) => ({
            width: columnWidths[column.key] ?? column.width,
          })),
        )
      : null;
  const activeFilterCount = useMemo(
    () => Object.values(filters).filter(isFilterActive).length,
    [filters],
  );
  const activeDirtyCell = useMemo(
    () =>
      activeCell
        ? {
            ...activeCell,
            originalValue:
              dirtyCells[
                legacyIssueGridCellKey(
                  activeCell.recordId,
                  activeCell.columnKey,
                )
              ],
          }
        : null,
    [activeCell, dirtyCells],
  );
  const selectedDetailRecord = useMemo(
    () =>
      selectedRecordId
        ? (visibleRecords.find(
            (record) => getRecordGridId(record) === selectedRecordId,
          ) ?? null)
        : null,
    [selectedRecordId, visibleRecords],
  );
  const resolvedRecordOpenLabel =
    recordOpenLabel ?? t('coreBusiness.grid.openDetails');
  const resolvedRecordOpenIcon = recordOpenIcon ?? <PanelRightOpen size={14} />;

  const gridColumns = useMemo<GlideGridColumn[]>(
    () => [
      ...visibleColumns.map((column) => {
        const activeFilter = filters[column.key];
        const sortIndex = sorts.findIndex(
          (item) => item.columnKey === column.key,
        );
        const activeSort = sortIndex >= 0 ? sorts[sortIndex] : null;
        const sortSuffix = activeSort
          ? ` ${activeSort.direction === 'asc' ? '▲' : '▼'}${
              sorts.length > 1 ? sortIndex + 1 : ''
            }`
          : '';
        const filterSuffix = isFilterActive(activeFilter) ? ' *' : '';
        return {
          group: column.group,
          hasMenu: true,
          id: column.key,
          title: `${column.title}${sortSuffix}${filterSuffix}`,
          width: columnWidths[column.key] ?? column.width,
        };
      }),
    ],
    [columnWidths, filters, sorts, visibleColumns],
  );

  const handleVisibleRegionChanged = useCallback<
    NonNullable<DataEditorProps['onVisibleRegionChanged']>
  >(
    (range, tx, ty) => {
      const preference = getGridScrollPreferenceFromVisibleRegion({
        columns: gridColumns,
        range,
        rowStartOffset:
          rowOffsets[Math.max(0, Math.floor(range.y))] ??
          rowOffsets.at(-1) ??
          0,
        tx,
        ty,
      });
      latestScrollPreferenceRef.current = preference;
    },
    [gridColumns, rowOffsets],
  );

  const handleItemHovered = useCallback(
    (args: GridMouseEventArgs) => {
      if (args.kind !== 'header') {
        setHeaderTooltip(null);
        return;
      }
      const content = visibleColumns[args.location[0]]?.tooltip;
      if (!content) {
        setHeaderTooltip(null);
        return;
      }
      const tooltipWidth = 320;
      const viewportWidth =
        typeof window === 'undefined' ? tooltipWidth : window.innerWidth;
      const viewportHeight =
        typeof window === 'undefined'
          ? args.bounds.y + args.bounds.height + 8
          : window.innerHeight;
      setHeaderTooltip({
        content,
        left: Math.max(
          8,
          Math.min(
            args.bounds.x + args.bounds.width / 2 - tooltipWidth / 2,
            viewportWidth - tooltipWidth - 8,
          ),
        ),
        top: Math.max(
          8,
          Math.min(args.bounds.y + args.bounds.height + 6, viewportHeight - 64),
        ),
      });
    },
    [visibleColumns],
  );

  const getCellContent = useCallback<DataEditorProps['getCellContent']>(
    ([columnIndex, rowIndex]) => {
      const isBlankRow = rowIndex < blankRowsBefore;
      const column = visibleColumns[columnIndex];
      if (!column) return EMPTY_GRID_CELL;
      if (isBlankRow) {
        const draft = blankRowDrafts[rowIndex] ?? {};
        const draftWithDefaults = {
          ...blankRowDefaultValues,
          ...draft,
        };
        return createLegacyIssueTextCell(
          draftWithDefaults[column.key],
          !isEditableColumn(column.key, readonlyColumnKeySet),
          {
            bgCell: highlightedColumnKeySet.has(column.key)
              ? gridTheme.editableColumnBg
              : undefined,
            requiredMissing:
              blankRowDraftHasData(draft) &&
              isBlankRowRequiredCellMissing({
                columnKey: column.key,
                requiredColumnKeys: requiredColumnKeySet,
                values: draftWithDefaults,
              }),
            selectOptions: column.options,
            inputKind: column.inputKind,
            inputLabel: column.title,
            textOverlay: !column.referenceKind,
          },
        );
      }
      const record = visibleRecords[rowIndex - blankRowsBefore];
      if (!record) return EMPTY_GRID_CELL;
      const recordId = getRecordGridId(record);
      return createLegacyIssueTextCell(
        getCellValue(record, column.key),
        !isEditableColumn(column.key, readonlyColumnKeySet),
        {
          bgCell: highlightedColumnKeySet.has(column.key)
            ? gridTheme.editableColumnBg
            : undefined,
          dirty: Boolean(
            recordId &&
              isLegacyIssueGridCellChanged({
                changedCellKeys: changedCellKeySet,
                columnKey: column.key,
                dirtyCells,
                recordId,
              }),
          ),
          dirtyBg: gridTheme.editedCellBg,
          searchActive:
            activeSearchCell?.[0] === columnIndex &&
            activeSearchCell?.[1] === rowIndex,
          searchBg: gridTheme.searchCellBg,
          selectOptions: column.options,
          inputKind: column.inputKind,
          inputLabel: column.title,
          textOverlay: !column.referenceKind,
        },
      );
    },
    [
      activeSearchCell,
      blankRowDefaultValues,
      blankRowsBefore,
      blankRowDrafts,
      changedCellKeySet,
      dirtyCells,
      getCellValue,
      gridTheme.editedCellBg,
      gridTheme.editableColumnBg,
      gridTheme.searchCellBg,
      highlightedColumnKeySet,
      requiredColumnKeySet,
      readonlyColumnKeySet,
      visibleColumns,
      visibleRecords,
    ],
  );

  const provideCellEditor = useCallback<
    NonNullable<DataEditorProps['provideEditor']>
  >((cell) => provideLegacyIssueCellEditor(cell), []);

  const handleDataEditorKeyDown = useCallback<
    NonNullable<DataEditorProps['onKeyDown']>
  >(
    (event) => {
      if (
        !isLegacyIssueEditorOpenKey(event) ||
        !event.location ||
        !event.rawEvent
      ) {
        return;
      }
      const cell = getCellContent(event.location);
      if (!isLegacyIssueEditableTextCell(cell)) return;
      const canvas = event.rawEvent.currentTarget;
      if (!(canvas instanceof HTMLCanvasElement)) return;

      event.cancel();
      event.preventDefault();
      event.stopPropagation();
      canvas.dispatchEvent(
        new KeyboardEvent('keydown', {
          bubbles: true,
          cancelable: true,
          code: 'Enter',
          key: 'Enter',
        }),
      );
    },
    [getCellContent],
  );

  const handleColumnResize = useCallback<
    NonNullable<DataEditorProps['onColumnResize']>
  >((column, newSize) => {
    if (!column.id) return;
    setColumnWidths((current) => ({
      ...current,
      [String(column.id)]: Math.round(newSize),
    }));
  }, []);
  const handleColumnResizeEnd = useCallback<
    NonNullable<DataEditorProps['onColumnResizeEnd']>
  >((column, newSize) => {
    if (!column.id) return;
    const resolvedSize = Math.round(newSize);
    setColumnWidths((current) => ({
      ...current,
      [String(column.id)]: resolvedSize,
    }));
    setAutoRowHeightColumnWidths((current) => ({
      ...current,
      [String(column.id)]: resolvedSize,
    }));
  }, []);

  const handleColumnMoved = useCallback<
    NonNullable<DataEditorProps['onColumnMoved']>
  >(
    (startIndex, endIndex) => {
      const next = moveVisibleGridColumn({
        columns,
        currentOrder: columnOrder,
        fromVisibleIndex: startIndex,
        toVisibleIndex: endIndex,
        visibleColumns,
      });
      setColumnOrderUserOverride(true);
      setColumnOrder(next);
      onPreferenceChange?.({
        columnOrder: next,
        frozenColumnCount,
        hiddenColumnKeys,
      });
    },
    [
      columnOrder,
      columns,
      frozenColumnCount,
      hiddenColumnKeys,
      onPreferenceChange,
      visibleColumns,
    ],
  );

  const handleSearchResultsChanged = useCallback<
    NonNullable<DataEditorProps['onSearchResultsChanged']>
  >((results, navIndex) => {
    setActiveSearchCell(results[navIndex] ?? null);
  }, []);

  const closeGridSearch = useCallback(() => {
    setGridSearchOpen(false);
    setActiveSearchCell(null);
  }, []);

  const openGridContextMenu = useCallback(
    ({
      columnCount,
      event,
      rowIndex,
    }: {
      columnCount: number | null;
      event: {
        bounds: { x: number; y: number };
        localEventX: number;
        localEventY: number;
        preventDefault: () => void;
      };
      rowIndex: number | null;
    }) => {
      event.preventDefault();
      setContextMenu({
        columnCount,
        rowIndexes: getLegacyIssueContextRowIndexes({
          rowCount: rows,
          rowIndex,
          selection: gridSelectionRef.current,
        }),
        rowIndex,
        x: Math.round(event.bounds.x + event.localEventX),
        y: Math.round(event.bounds.y + event.localEventY),
      });
      setColumnsMenuOpen(false);
      setFilterMenu(null);
    },
    [rows],
  );
  const handleHeaderContextMenu = useCallback<
    NonNullable<DataEditorProps['onHeaderContextMenu']>
  >(
    (columnIndex, event) => {
      openGridContextMenu({
        columnCount: columnIndex + 1,
        event,
        rowIndex: null,
      });
    },
    [openGridContextMenu],
  );

  const handleGroupHeaderContextMenu = useCallback<
    NonNullable<DataEditorProps['onGroupHeaderContextMenu']>
  >(
    (columnIndex, event) => {
      openGridContextMenu({
        columnCount: columnIndex + 1,
        event,
        rowIndex: null,
      });
    },
    [openGridContextMenu],
  );

  const handleCellContextMenu = useCallback<
    NonNullable<DataEditorProps['onCellContextMenu']>
  >(
    ([columnIndex, rowIndex], event) => {
      openGridContextMenu({
        columnCount: columnIndex + 1,
        event,
        rowIndex,
      });
    },
    [openGridContextMenu],
  );

  const removeBlankRowsAt = useCallback(
    (rowIndexes: number[]) => {
      const blankRowIndexes = normalizeLegacyIssueRowIndexes(
        rowIndexes.filter((rowIndex) => rowIndex < blankRowsBefore),
        blankRowsBefore,
      );
      if (blankRowIndexes.length === 0) return;
      setBlankRowDrafts((current) =>
        removeBlankRowDraftsAt(current, blankRowIndexes),
      );
      onRemoveBlankRows?.(blankRowIndexes);
    },
    [blankRowsBefore, onRemoveBlankRows],
  );

  const handleCellClicked = useCallback<
    NonNullable<DataEditorProps['onCellClicked']>
  >(
    ([columnIndex, rowIndex]) => {
      if (rowIndex < blankRowsBefore) return;
      const record = visibleRecords[rowIndex - blankRowsBefore];
      if (!record) return;
      const column = visibleColumns[columnIndex];
      if (!column) return;
      const recordId = getRecordGridId(record);
      if (
        recordId &&
        column.referenceKind &&
        activeCell?.recordId === recordId &&
        activeCell.columnKey === column.key &&
        isEditableColumn(column.key, readonlyColumnKeySet)
      ) {
        onReferenceCellEditRequest?.({
          allowMultiple: Boolean(column.allowMultiple),
          columnKey: column.key,
          record,
          referenceKind: column.referenceKind,
        });
        return;
      }
      setActiveCell(recordId ? { columnKey: column.key, recordId } : null);
      const handled = onCellClick?.({ columnKey: column.key, record });
      if (handled) return;
      if (detailOpen && onRecordOpen) {
        onRecordOpen(record);
      }
    },
    [
      activeCell,
      detailOpen,
      blankRowsBefore,
      onCellClick,
      onRecordOpen,
      onReferenceCellEditRequest,
      readonlyColumnKeySet,
      visibleColumns,
      visibleRecords,
    ],
  );

  const handleCellActivated = useCallback<
    NonNullable<DataEditorProps['onCellActivated']>
  >(
    ([columnIndex, rowIndex]) => {
      const recordIndex = rowIndex - blankRowsBefore;
      if (rowIndex < blankRowsBefore || recordIndex >= visibleRecords.length) {
        setActiveCell(null);
        return;
      }
      const column = visibleColumns[columnIndex];
      const record = visibleRecords[recordIndex];
      const recordId = getRecordGridId(record);
      setActiveCell(
        column && recordId ? { columnKey: column.key, recordId } : null,
      );
      if (
        column?.referenceKind &&
        recordId &&
        isEditableColumn(column.key, readonlyColumnKeySet)
      ) {
        onReferenceCellEditRequest?.({
          allowMultiple: Boolean(column.allowMultiple),
          columnKey: column.key,
          record,
          referenceKind: column.referenceKind,
        });
      }
    },
    [
      blankRowsBefore,
      onReferenceCellEditRequest,
      readonlyColumnKeySet,
      visibleColumns,
      visibleRecords,
    ],
  );

  const commitExistingCellValues = useCallback(
    async (
      edits: Array<{
        columnKey: string;
        record: TRecord;
        value: string | null;
      }>,
    ) => {
      if ((!onCellEdit && !onCellBatchEdit) || edits.length === 0) return;
      const committedEdits = edits
        .map((edit) => {
          if (!isEditableColumn(edit.columnKey, readonlyColumnKeySet)) {
            return null;
          }
          const previous = normalizeGridValue(
            getCellValue(edit.record, edit.columnKey),
          );
          const committedValue = normalizeGridValue(edit.value);
          if (previous === committedValue) return null;
          const recordId = getRecordGridId(edit.record);
          if (!recordId) return null;
          return {
            ...edit,
            committedValue,
            previous,
            recordId,
          };
        })
        .filter(
          (
            edit,
          ): edit is {
            columnKey: string;
            committedValue: string;
            previous: string;
            record: TRecord;
            recordId: string;
            value: string | null;
          } => Boolean(edit),
        );
      if (committedEdits.length === 0) return;
      if (onCellBatchEdit) {
        await onCellBatchEdit({
          edits: committedEdits.map(({ columnKey, record, value }) => ({
            columnKey,
            record,
            value,
          })),
        });
      } else if (onCellEdit) {
        for (const edit of committedEdits) {
          await onCellEdit({
            columnKey: edit.columnKey,
            record: edit.record,
            value: edit.value,
          });
        }
      }
      setDirtyCells((current) => {
        const next = { ...current };
        for (const edit of committedEdits) {
          const key = legacyIssueGridCellKey(edit.recordId, edit.columnKey);
          const originalValue = current[key] ?? edit.previous;
          if (originalValue === edit.committedValue) {
            delete next[key];
          } else {
            next[key] = originalValue;
          }
        }
        return next;
      });
    },
    [getCellValue, onCellBatchEdit, onCellEdit, readonlyColumnKeySet],
  );

  const commitExistingCellValue = useCallback(
    async ({
      columnKey,
      record,
      value,
    }: {
      columnKey: string;
      record: TRecord;
      value: string | null;
    }) => {
      await commitExistingCellValues([{ columnKey, record, value }]);
    },
    [commitExistingCellValues],
  );

  const updateBlankRowDraftValues = useCallback(
    (rowIndex: number, values: Record<string, string | null>): void => {
      if (rowIndex < 0 || rowIndex >= blankRowsBefore) return;
      const nextDraft = mergeBlankRowDraftValues(
        blankRowDrafts[rowIndex] ?? {},
        values,
      );
      setBlankRowDrafts((current) =>
        replaceBlankRowDraftAt(current, rowIndex, nextDraft, blankRowsBefore),
      );
    },
    [blankRowsBefore, blankRowDrafts],
  );

  const commitCellEdits = useCallback(
    async (
      items: Parameters<NonNullable<DataEditorProps['onCellsEdited']>>[0],
    ) => {
      const existingEdits: Array<{
        columnKey: string;
        record: TRecord;
        value: string | null;
      }> = [];
      const blankRowPatches = new Map<number, Record<string, string | null>>();
      for (const item of items) {
        const [columnIndex, rowIndex] = item.location;
        const column = visibleColumns[columnIndex];
        if (!column || !isEditableColumn(column.key, readonlyColumnKeySet)) {
          continue;
        }
        const value = editableCellToText(item.value);
        const nextValue = value.trim() ? value : null;
        if (rowIndex < blankRowsBefore) {
          const patch = blankRowPatches.get(rowIndex) ?? {};
          patch[column.key] = nextValue;
          blankRowPatches.set(rowIndex, patch);
          continue;
        }
        const record = visibleRecords[rowIndex - blankRowsBefore];
        if (!record) continue;
        existingEdits.push({
          columnKey: column.key,
          record,
          value: nextValue,
        });
      }
      for (const [rowIndex, patch] of blankRowPatches.entries()) {
        updateBlankRowDraftValues(rowIndex, patch);
      }
      await commitExistingCellValues(existingEdits);
    },
    [
      commitExistingCellValues,
      updateBlankRowDraftValues,
      blankRowsBefore,
      readonlyColumnKeySet,
      visibleColumns,
      visibleRecords,
    ],
  );

  const handleCellEdited = useCallback<
    NonNullable<DataEditorProps['onCellEdited']>
  >(
    (cell, nextCell) => {
      void commitCellEdits([{ location: cell, value: nextCell }]);
    },
    [commitCellEdits],
  );

  const handleCellsEdited = useCallback<
    NonNullable<DataEditorProps['onCellsEdited']>
  >(
    (items) => {
      void commitCellEdits(items);
      return true;
    },
    [commitCellEdits],
  );

  const handlePaste = useCallback(
    (target: Item, values: readonly (readonly string[])[]) => {
      const expandedValues = expandLegacyIssuePasteValuesForSelection({
        selection: gridSelectionRef.current?.current?.range ?? null,
        target,
        values,
      });
      const plan = buildLegacyIssuePastePlan({
        getCellValue,
        blankRowCount: blankRowsBefore,
        readonlyColumnKeys: readonlyColumnKeySet,
        target,
        values: expandedValues,
        visibleColumns,
        visibleRecords,
      });
      if (plan.creates.length === 0 && plan.edits.length === 0) return false;
      if (expandedValues !== values) {
        void (async () => {
          for (const create of [...plan.creates].sort(
            (left, right) => right.rowIndex - left.rowIndex,
          )) {
            updateBlankRowDraftValues(create.rowIndex, create.values);
          }
          await commitExistingCellValues(plan.edits);
        })();
        return false;
      }
      return true;
    },
    [
      commitExistingCellValues,
      updateBlankRowDraftValues,
      getCellValue,
      blankRowsBefore,
      readonlyColumnKeySet,
      visibleColumns,
      visibleRecords,
    ],
  );

  const revertActiveCell = useCallback(async () => {
    if (
      !activeDirtyCell ||
      activeDirtyCell.originalValue === undefined ||
      (!onCellEdit && !onCellBatchEdit)
    ) {
      return;
    }
    const record = records.find(
      (item) => getRecordGridId(item) === activeDirtyCell.recordId,
    );
    if (!record) return;
    await commitExistingCellValue({
      columnKey: activeDirtyCell.columnKey,
      record,
      value: activeDirtyCell.originalValue.trim()
        ? activeDirtyCell.originalValue
        : null,
    });
    setDirtyCells((current) => {
      const next = { ...current };
      delete next[
        legacyIssueGridCellKey(
          activeDirtyCell.recordId,
          activeDirtyCell.columnKey,
        )
      ];
      return next;
    });
  }, [
    activeDirtyCell,
    commitExistingCellValue,
    onCellBatchEdit,
    onCellEdit,
    records,
  ]);

  const handleHeaderMenuClick = useCallback<
    NonNullable<DataEditorProps['onHeaderMenuClick']>
  >(
    (columnIndex, bounds) => {
      const column = visibleColumns[columnIndex];
      if (!column) return;
      setFilterSearch('');
      setFilterMenu({
        columnKey: column.key,
        x: Math.round(bounds.x),
        y: Math.round(bounds.y + bounds.height + 4),
      });
      setColumnsMenuOpen(false);
    },
    [visibleColumns],
  );

  const getRowThemeOverride = useCallback<GetRowThemeCallback>(
    (row) => {
      if (row < blankRowsBefore) {
        return { bgCell: gridTheme.newRowBg };
      }
      if ((row - blankRowsBefore) % 2 === 1) {
        return { bgCell: gridTheme.stripedRowBg };
      }
      return undefined;
    },
    [blankRowsBefore, gridTheme.newRowBg, gridTheme.stripedRowBg],
  );

  const toggleColumnVisibility = useCallback(
    (columnKey: string) => {
      if (hiddenColumnKeys.includes(columnKey)) {
        const next = hiddenColumnKeys.filter((key) => key !== columnKey);
        setHiddenColumnKeys(next);
        onPreferenceChange?.({
          columnOrder: columnOrderUserOverride ? columnOrder : [],
          frozenColumnCount,
          hiddenColumnKeys: next,
        });
        return;
      }
      const visibleCount = columns.filter(
        (column) => !hiddenColumnKeys.includes(column.key),
      ).length;
      if (visibleCount <= 1) return;
      const next = [...hiddenColumnKeys, columnKey];
      const nextFrozenColumnCount = Math.min(
        frozenColumnCount,
        Math.max(0, visibleCount - 1),
      );
      setHiddenColumnKeys(next);
      setFrozenColumnCount(nextFrozenColumnCount);
      onPreferenceChange?.({
        columnOrder: columnOrderUserOverride ? columnOrder : [],
        frozenColumnCount: nextFrozenColumnCount,
        hiddenColumnKeys: next,
      });
    },
    [
      columnOrder,
      columnOrderUserOverride,
      columns,
      frozenColumnCount,
      hiddenColumnKeys,
      onPreferenceChange,
    ],
  );

  const resetGridLayout = useCallback(() => {
    setColumnWidths({});
    setAutoRowHeightColumnWidths({});
    setHiddenColumnKeys([]);
    setColumnOrder(
      resolveLegacyIssueGridPersonalizedColumnOrder({
        columns,
        defaultColumnOrder,
        personalizedColumnOrder: null,
      }),
    );
    setColumnOrderUserOverride(false);
    setFrozenColumnCount(0);
    onPreferenceReset?.();
  }, [columns, defaultColumnOrder, onPreferenceReset]);

  const resetHiddenColumns = useCallback(() => {
    setHiddenColumnKeys([]);
    onPreferenceChange?.({
      columnOrder: columnOrderUserOverride ? columnOrder : [],
      frozenColumnCount,
      hiddenColumnKeys: [],
    });
  }, [
    columnOrder,
    columnOrderUserOverride,
    frozenColumnCount,
    onPreferenceChange,
  ]);

  const handleFrozenColumnCountChange = useCallback(
    (count: number) => {
      const next = Math.min(Math.max(0, count), maxFrozenColumnCount);
      setFrozenColumnCount(next);
      onPreferenceChange?.({
        columnOrder: columnOrderUserOverride ? columnOrder : [],
        frozenColumnCount: next,
        hiddenColumnKeys,
      });
    },
    [
      columnOrder,
      columnOrderUserOverride,
      hiddenColumnKeys,
      maxFrozenColumnCount,
      onPreferenceChange,
    ],
  );

  const handleAutoRowHeightChange = useCallback((enabled: boolean) => {
    pendingAutoRowHeightScrollRef.current = latestScrollPreferenceRef.current;
    setAutoRowHeightEnabled(enabled);
  }, []);

  const handleGridKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLDivElement>) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'f') {
        event.preventDefault();
        setGridSearchOpen(true);
        setColumnsMenuOpen(false);
        setFilterMenu(null);
      }
    },
    [],
  );

  const applyDraftRows = useCallback(() => {
    if (!onCreateRows || !canApplyDraftRows) return;
    const rowsToApply = draftRowsReadyToApply.map((draft) => ({
      rowIndex: draft.rowIndex,
      values: draft.values,
    }));
    void (async () => {
      const createdCount =
        (await onCreateRows({
          values: rowsToApply.map((draft) => draft.values),
        })) ?? rowsToApply.length;
      const appliedCount = Math.min(
        rowsToApply.length,
        Math.max(0, Math.floor(createdCount)),
      );
      if (appliedCount <= 0) return;
      setBlankRowDrafts((current) =>
        removeBlankRowDraftsAt(
          current,
          rowsToApply.slice(0, appliedCount).map((draft) => draft.rowIndex),
        ),
      );
    })();
  }, [canApplyDraftRows, draftRowsReadyToApply, onCreateRows]);

  const handleGridSelectionChange = useCallback<
    NonNullable<DataEditorProps['onGridSelectionChange']>
  >(
    (selection) => {
      gridSelectionRef.current = selection;
      setGridSelection(selection);
      const rowIndex = selection.current?.cell[1] ?? null;
      const record =
        rowIndex !== null && rowIndex >= blankRowsBefore
          ? (visibleRecords[rowIndex - blankRowsBefore] ?? null)
          : null;
      setSelectedRecordId(record ? getRecordGridId(record) : null);
    },
    [blankRowsBefore, visibleRecords],
  );

  const drawCell = useCallback<DrawCellCallback>(
    (args, drawContent) => {
      drawContent();
      if (!isLegacyIssueRequiredMissingCell(args.cell)) return;
      const { ctx, rect } = args;
      ctx.save();
      ctx.strokeStyle = gridTheme.requiredMissingBorder;
      ctx.lineWidth = 2;
      ctx.strokeRect(
        Math.floor(rect.x) + 1,
        Math.floor(rect.y) + 1,
        Math.ceil(rect.width) - 2,
        Math.ceil(rect.height) - 2,
      );
      ctx.restore();
    },
    [gridTheme.requiredMissingBorder],
  );

  const contextRowIndexes = contextMenu?.rowIndexes ?? [];
  const contextBlankRowIndexes = contextRowIndexes.filter(
    (rowIndex) => rowIndex < blankRowsBefore,
  );
  const contextRowRecords = contextRowIndexes
    .filter((rowIndex) => rowIndex >= blankRowsBefore)
    .map((rowIndex) => visibleRecords[rowIndex - blankRowsBefore])
    .filter((record): record is TRecord => Boolean(record));

  const canDeleteContextRow = Boolean(
    contextMenu &&
      ((contextBlankRowIndexes.length > 0 && onRemoveBlankRows) ||
        (contextRowRecords.length > 0 && onDeleteRows)),
  );

  const handleContextAddRow = useCallback(() => {
    onAddBlankRows?.(Math.max(1, contextMenu?.rowIndexes.length ?? 0));
    setContextMenu(null);
  }, [contextMenu, onAddBlankRows]);

  const handleContextDeleteRow = useCallback(() => {
    if (!contextMenu) return;
    const rowIndexes = contextMenu.rowIndexes;
    const blankRowIndexes = rowIndexes.filter(
      (rowIndex) => rowIndex < blankRowsBefore,
    );
    if (blankRowIndexes.length > 0) {
      removeBlankRowsAt(blankRowIndexes);
    }
    const recordsToDelete = rowIndexes
      .filter((rowIndex) => rowIndex >= blankRowsBefore)
      .map((rowIndex) => visibleRecords[rowIndex - blankRowsBefore])
      .filter((record): record is TRecord => Boolean(record));
    if (recordsToDelete.length > 0 && onDeleteRows) {
      void onDeleteRows(recordsToDelete);
    }
    setContextMenu(null);
  }, [
    blankRowsBefore,
    contextMenu,
    onDeleteRows,
    removeBlankRowsAt,
    visibleRecords,
  ]);

  const showGridLoading = loading && records.length === 0 && !hasCreateRows;
  const showGridEmpty = !loading && records.length === 0 && !hasCreateRows;
  const keepToolbarWhenEmpty = Boolean(toolbarLeading || toolbarTrailing);

  if (showGridLoading && !keepToolbarWhenEmpty) {
    return <LegacyIssueGridLoadingBlock label={loadingLabel} />;
  }
  if (showGridEmpty && !keepToolbarWhenEmpty) {
    return <LegacyIssueGridEmptyBlock label={emptyLabel} />;
  }

  const filterColumn = filterMenu
    ? (columns.find((column) => column.key === filterMenu.columnKey) ?? null)
    : null;

  return (
    <div
      className="relative flex min-h-[30rem] flex-1 flex-col overflow-hidden bg-app-bg"
      onKeyDown={handleGridKeyDown}
    >
      <div className="flex h-9 shrink-0 items-center justify-between gap-2 overflow-x-auto whitespace-nowrap border-b border-app-border bg-app-surface-sidebar px-2">
        <div className="flex shrink-0 items-center gap-1">
          {toolbarLeading}
          {sorts.map((sort, index) => {
            const columnTitle =
              columns.find((column) => column.key === sort.columnKey)?.title ??
              sort.columnKey;
            const baseLabel =
              sorts.length > 1
                ? t('coreBusiness.grid.sortPill', {
                    column: columnTitle,
                    priority: index + 1,
                  })
                : columnTitle;
            return (
              <GridPill
                key={sort.columnKey}
                icon={
                  sort.direction === 'asc' ? (
                    <ChevronUp size={13} />
                  ) : (
                    <ChevronDown size={13} />
                  )
                }
                label={
                  sort.emptyPlacement
                    ? t(
                        `coreBusiness.grid.emptyPlacement.${sort.emptyPlacement}`,
                        { column: baseLabel },
                      )
                    : baseLabel
                }
                onClear={() =>
                  updateSorts((current) =>
                    removeGridSort(current, sort.columnKey),
                  )
                }
              />
            );
          })}
          {activeFilterCount > 0 ? (
            <GridPill
              icon={<Filter size={13} />}
              label={t('coreBusiness.grid.activeFilters', {
                count: activeFilterCount,
              })}
              onClear={() => setFilters({})}
            />
          ) : null}
          {activeDirtyCell?.originalValue !== undefined ? (
            <button
              className="inline-flex h-7 shrink-0 items-center gap-1.5 rounded-md border border-app-warning-border bg-app-warning-bg px-2 app-text-caption font-medium text-app-warning-text hover:bg-amber-100"
              type="button"
              onClick={() => {
                void revertActiveCell();
              }}
            >
              <RotateCcw size={13} />
              <span>{t('coreBusiness.grid.revertCell')}</span>
            </button>
          ) : null}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <label className="inline-flex h-7 shrink-0 cursor-pointer items-center gap-1.5 rounded-md border border-app-border bg-app-bg px-2 app-text-caption text-app-ink/70 hover:bg-app-surface-hover">
            <input
              checked={autoRowHeightEnabled}
              className="size-4 shrink-0 accent-app-accent"
              type="checkbox"
              onChange={(event) =>
                handleAutoRowHeightChange(event.currentTarget.checked)
              }
            />
            <span>{t('coreBusiness.grid.autoRowHeight')}</span>
          </label>
          {onRecordOpen ? (
            <button
              className={cn(
                'inline-flex h-7 shrink-0 items-center gap-1.5 rounded-md border px-2 app-text-caption font-medium',
                selectedDetailRecord
                  ? 'border-app-accent/40 bg-app-accent/10 text-app-accent hover:bg-app-accent/15'
                  : 'border-app-border bg-app-bg text-app-ink/70 hover:bg-app-surface-hover disabled:bg-app-surface-muted disabled:text-app-ink/35',
              )}
              disabled={!selectedDetailRecord}
              type="button"
              onClick={() => {
                if (!selectedDetailRecord) return;
                onRecordOpen(selectedDetailRecord);
              }}
            >
              {resolvedRecordOpenIcon}
              <span>{resolvedRecordOpenLabel}</span>
            </button>
          ) : null}
          {onAddBlankRows ? (
            <button
              className="inline-flex h-7 shrink-0 items-center gap-1.5 rounded-md border border-app-border bg-app-bg px-2 app-text-caption text-app-ink/70 hover:bg-app-surface-hover"
              type="button"
              onClick={() => onAddBlankRows()}
            >
              <Plus size={14} />
              <span>{t('coreBusiness.grid.addRows')}</span>
            </button>
          ) : null}
          {onCreateRows && blankRowsBefore > 0 ? (
            <button
              className={cn(
                'inline-flex h-7 shrink-0 items-center gap-1.5 rounded-md border px-2 app-text-caption font-medium',
                canApplyDraftRows
                  ? 'border-app-accent bg-app-accent text-app-accent-fg hover:bg-app-accent/90'
                  : 'border-app-border bg-app-surface-muted text-app-ink/35',
              )}
              type="button"
              disabled={!canApplyDraftRows}
              onClick={applyDraftRows}
            >
              <Check size={14} />
              <span>{t('coreBusiness.grid.applyRows')}</span>
            </button>
          ) : null}
          <button
            aria-pressed={gridSearchOpen}
            className={cn(
              'inline-flex h-7 shrink-0 items-center gap-1.5 rounded-md border px-2 app-text-caption hover:bg-app-surface-hover',
              gridSearchOpen
                ? 'border-app-accent bg-app-accent/10 text-app-accent'
                : 'border-app-border bg-app-bg text-app-ink/70',
            )}
            type="button"
            onClick={() => {
              setGridSearchOpen(true);
              setColumnsMenuOpen(false);
              setFilterMenu(null);
            }}
          >
            <Search size={14} />
            <span>{t('coreBusiness.grid.find')}</span>
          </button>
          <button
            className="inline-flex h-7 shrink-0 items-center gap-1.5 rounded-md border border-app-border bg-app-bg px-2 app-text-caption text-app-ink/70 hover:bg-app-surface-hover"
            type="button"
            onClick={() => {
              setColumnsMenuOpen((current) => !current);
              setFilterMenu(null);
            }}
          >
            <Columns3 size={14} />
            <span>{t('coreBusiness.grid.columns')}</span>
          </button>
          {toolbarTrailing}
        </div>
      </div>

      <div
        ref={setDataEditorContainerElement}
        className="relative flex min-h-0 flex-1 overflow-hidden"
      >
        {showGridLoading ? (
          <LegacyIssueGridLoadingBlock label={loadingLabel} />
        ) : showGridEmpty ? (
          <LegacyIssueGridEmptyBlock label={emptyLabel} />
        ) : dataEditorHeight !== null ? (
          <DataEditor
            ref={dataEditorRef}
            key={dataEditorHeight}
            columns={gridColumns}
            drawFocusRing
            drawCell={drawCell}
            editOnType={false}
            cellActivationBehavior="second-click"
            freezeColumns={effectiveFrozenColumnCount}
            getCellContent={getCellContent}
            getCellsForSelection
            gridSelection={gridSelection}
            coercePasteValue={coerceLegacyIssuePasteCellValue}
            getRowThemeOverride={getRowThemeOverride}
            groupHeaderHeight={GRID_GROUP_HEADER_HEIGHT}
            headerHeight={GRID_HEADER_HEIGHT}
            height={dataEditorHeight}
            maxColumnWidth={GRID_MAX_COLUMN_WIDTH}
            minColumnWidth={GRID_MIN_COLUMN_WIDTH}
            onCellActivated={handleCellActivated}
            onCellContextMenu={handleCellContextMenu}
            onCellClicked={handleCellClicked}
            onCellEdited={handleCellEdited}
            onCellsEdited={handleCellsEdited}
            onColumnMoved={
              preferenceControlsDisabled ? undefined : handleColumnMoved
            }
            onColumnResize={handleColumnResize}
            onColumnResizeEnd={handleColumnResizeEnd}
            onGroupHeaderContextMenu={handleGroupHeaderContextMenu}
            onGridSelectionChange={handleGridSelectionChange}
            onHeaderContextMenu={handleHeaderContextMenu}
            onHeaderMenuClick={handleHeaderMenuClick}
            onItemHovered={handleItemHovered}
            onKeyDown={handleDataEditorKeyDown}
            onPaste={handlePaste}
            onVisibleRegionChanged={handleVisibleRegionChanged}
            provideEditor={provideCellEditor}
            onSearchClose={closeGridSearch}
            onSearchResultsChanged={handleSearchResultsChanged}
            rangeSelect="multi-rect"
            rowHeight={autoRowHeightEnabled ? getRowHeight : GRID_ROW_HEIGHT}
            rowMarkers={{
              kind: 'number',
              startIndex: 1,
              width: GRID_ROW_MARKER_WIDTH,
            }}
            rows={rows}
            showSearch={gridSearchOpen}
            smoothScrollX
            smoothScrollY
            theme={gridTheme.theme}
            verticalBorder
            width="100%"
          />
        ) : null}
        {!showGridLoading &&
        !showGridEmpty &&
        frozenColumnBoundaryX !== null ? (
          <div
            className="pointer-events-none absolute bottom-0 top-0 z-10 w-px"
            style={{
              backgroundColor: gridTheme.frozenBoundaryColor,
              left: frozenColumnBoundaryX - 1,
              boxShadow: LEGACY_GRID_BOUNDARY_SHADOW,
            }}
          />
        ) : null}
      </div>

      <LegacyIssueGridHeaderTooltip tooltip={headerTooltip} />

      {columnsMenuOpen ? (
        <div className="absolute right-2 top-10 z-20 w-72 rounded-md border border-app-border bg-app-bg p-2 shadow-lg">
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="min-w-0">
              <span className="app-text-caption font-semibold text-app-ink/70">
                {t('coreBusiness.grid.columns')}
              </span>
              {preferenceStatus === 'saving' ? (
                <span className="ml-2 inline-flex items-center gap-1 app-text-caption text-app-ink/50">
                  <Loader2 size={11} className="animate-spin" />
                  {t('coreBusiness.grid.preferenceSaving')}
                </span>
              ) : null}
              {preferenceStatus === 'error' && onPreferenceRetry ? (
                <button
                  className="ml-2 rounded px-1 py-0.5 app-text-caption text-app-danger hover:bg-app-danger/10"
                  type="button"
                  onClick={onPreferenceRetry}
                >
                  {t('coreBusiness.grid.preferenceRetry')}
                </button>
              ) : null}
            </div>
            <button
              className="rounded px-1.5 py-1 app-text-caption text-app-ink/60 hover:bg-app-surface-hover"
              disabled={preferenceControlsDisabled}
              type="button"
              onClick={resetGridLayout}
            >
              {t('coreBusiness.grid.resetLayout')}
            </button>
          </div>
          <div className="mb-2 grid gap-1.5 rounded-md border border-app-border bg-app-surface p-2">
            <GridNumberStepper
              decreaseLabel={t('coreBusiness.grid.decreaseFrozenColumns')}
              disabled={preferenceControlsDisabled}
              increaseLabel={t('coreBusiness.grid.increaseFrozenColumns')}
              label={t('coreBusiness.grid.freezeColumns')}
              max={maxFrozenColumnCount}
              min={0}
              onChange={handleFrozenColumnCountChange}
              value={effectiveFrozenColumnCount}
            />
          </div>
          <div className="mb-2 flex justify-end">
            <button
              className="rounded px-1.5 py-1 app-text-caption text-app-ink/60 hover:bg-app-surface-hover"
              disabled={preferenceControlsDisabled}
              type="button"
              onClick={resetHiddenColumns}
            >
              {t('coreBusiness.grid.reset')}
            </button>
          </div>
          <div className="max-h-72 overflow-y-auto pr-1">
            {orderedColumns.map((column) => {
              const checked = !hiddenColumnKeySet.has(column.key);
              return (
                <button
                  key={column.key}
                  className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left app-text-caption hover:bg-app-surface-hover"
                  disabled={preferenceControlsDisabled}
                  type="button"
                  onClick={() => toggleColumnVisibility(column.key)}
                >
                  <span
                    className={cn(
                      'flex size-4 items-center justify-center rounded border',
                      checked
                        ? 'border-app-accent bg-app-accent text-app-accent-fg'
                        : 'border-app-border',
                    )}
                  >
                    {checked ? <Check size={12} /> : null}
                  </span>
                  <span className="truncate">{column.title}</span>
                </button>
              );
            })}
          </div>
        </div>
      ) : null}

      {filterMenu && filterColumn ? (
        <GridFilterMenu
          column={filterColumn}
          filters={filters}
          getCellValue={getCellValue}
          menu={filterMenu}
          records={records}
          search={filterSearch}
          sorts={sorts}
          onClose={() => setFilterMenu(null)}
          onFiltersChange={setFilters}
          onSearchChange={setFilterSearch}
          onSortsChange={updateSorts}
        />
      ) : null}
      {contextMenu ? (
        <GridContextMenu
          canAddRow={Boolean(onAddBlankRows)}
          canDeleteRow={canDeleteContextRow}
          columnCount={contextMenu.columnCount}
          frozenColumnCount={effectiveFrozenColumnCount}
          maxFrozenColumnCount={maxFrozenColumnCount}
          preferenceControlsDisabled={preferenceControlsDisabled}
          x={contextMenu.x}
          y={contextMenu.y}
          onClose={() => setContextMenu(null)}
          onAddRow={handleContextAddRow}
          onDeleteRow={handleContextDeleteRow}
          onFreezeColumns={(count) => {
            if (preferenceControlsDisabled) {
              setContextMenu(null);
              return;
            }
            handleFrozenColumnCountChange(count);
            setContextMenu(null);
          }}
        />
      ) : null}
    </div>
  );
}

function LegacyIssueGridHeaderTooltip({
  tooltip,
}: {
  tooltip: LegacyIssueGridHeaderTooltip;
}) {
  if (!tooltip || typeof document === 'undefined') return null;
  return createPortal(
    <div
      className="pointer-events-none fixed z-[var(--ui-z-popover)] max-w-80 rounded-md border border-app-border bg-app-ink px-3 py-2 app-text-caption text-app-bg shadow-lg"
      role="tooltip"
      style={{ left: tooltip.left, top: tooltip.top }}
    >
      {tooltip.content}
    </div>,
    document.body,
  );
}

function GridContextMenu({
  canAddRow,
  canDeleteRow,
  columnCount,
  frozenColumnCount,
  maxFrozenColumnCount,
  preferenceControlsDisabled,
  x,
  y,
  onAddRow,
  onClose,
  onDeleteRow,
  onFreezeColumns,
}: {
  canAddRow: boolean;
  canDeleteRow: boolean;
  columnCount: number | null;
  frozenColumnCount: number;
  maxFrozenColumnCount: number;
  preferenceControlsDisabled: boolean;
  x: number;
  y: number;
  onAddRow: () => void;
  onClose: () => void;
  onDeleteRow: () => void;
  onFreezeColumns: (count: number) => void;
}) {
  const { t } = useTranslation(['apps']);
  if (typeof document === 'undefined') return null;

  const menuLeft =
    typeof window === 'undefined' ? x : Math.min(x, window.innerWidth - 220);
  const menuTop =
    typeof window === 'undefined' ? y : Math.min(y, window.innerHeight - 180);
  const canFreezeColumns = columnCount !== null && maxFrozenColumnCount > 0;
  if (
    !canAddRow &&
    !canDeleteRow &&
    !canFreezeColumns &&
    frozenColumnCount === 0
  ) {
    return null;
  }

  return createPortal(
    <>
      <button
        aria-label={t('coreBusiness.grid.closeContextMenu')}
        className="fixed inset-0 z-[9998] cursor-default bg-transparent"
        type="button"
        onClick={onClose}
      />
      <div
        className="fixed z-[9999] w-52 rounded-lg border border-app-border bg-app-bg py-1 shadow-xl"
        style={{
          left: Math.max(8, menuLeft),
          top: Math.max(8, menuTop),
        }}
      >
        {canAddRow ? (
          <button
            className="flex w-full items-center gap-2 px-3 py-2 text-left app-text-control-sm text-app-ink hover:bg-app-surface-hover"
            type="button"
            onClick={onAddRow}
          >
            <Plus size={14} className="text-app-ink/45" />
            <span>{t('coreBusiness.grid.addRows')}</span>
          </button>
        ) : null}
        {canDeleteRow ? (
          <button
            className="flex w-full items-center gap-2 px-3 py-2 text-left app-text-control-sm text-app-danger hover:bg-app-danger/10"
            type="button"
            onClick={onDeleteRow}
          >
            <Trash2 size={14} className="text-app-danger" />
            <span>{t('coreBusiness.grid.deleteRow')}</span>
          </button>
        ) : null}
        {(canAddRow || canDeleteRow) &&
        (canFreezeColumns || frozenColumnCount > 0) ? (
          <div className="my-1 border-t border-app-border" />
        ) : null}
        {canFreezeColumns ? (
          <button
            className="flex w-full items-center gap-2 px-3 py-2 text-left app-text-control-sm text-app-ink hover:bg-app-surface-hover"
            disabled={preferenceControlsDisabled}
            type="button"
            onClick={() =>
              onFreezeColumns(Math.min(columnCount ?? 0, maxFrozenColumnCount))
            }
          >
            <Pin size={14} className="text-app-ink/45" />
            <span>{t('coreBusiness.grid.freezeColumnsToHere')}</span>
          </button>
        ) : null}
        {frozenColumnCount > 0 ? (
          <button
            className="flex w-full items-center gap-2 px-3 py-2 text-left app-text-control-sm text-app-ink hover:bg-app-surface-hover"
            disabled={preferenceControlsDisabled}
            type="button"
            onClick={() => onFreezeColumns(0)}
          >
            <PinOff size={14} className="text-app-ink/45" />
            <span>{t('coreBusiness.grid.unfreezeColumns')}</span>
          </button>
        ) : null}
      </div>
    </>,
    document.body,
  );
}

function GridFilterMenu<TRecord>({
  column,
  filters,
  getCellValue,
  menu,
  records,
  search,
  sorts,
  onClose,
  onFiltersChange,
  onSearchChange,
  onSortsChange,
}: {
  column: LegacyIssueGridColumn;
  filters: Record<string, LegacyIssueGridFilter>;
  getCellValue: (
    record: TRecord,
    columnKey: string,
  ) => string | null | undefined;
  menu: { x: number; y: number };
  records: TRecord[];
  search: string;
  sorts: LegacyIssueGridSort[];
  onClose: () => void;
  onFiltersChange: (filters: Record<string, LegacyIssueGridFilter>) => void;
  onSearchChange: (value: string) => void;
  onSortsChange: (sorts: LegacyIssueGridSort[]) => void;
}) {
  const { t } = useTranslation(['apps']);
  const filter = filters[column.key] ?? { selectedValues: null, text: '' };
  const uniqueValues = useMemo(
    () => getUniqueColumnValues(records, column.key, getCellValue),
    [column.key, getCellValue, records],
  );
  const filteredValues = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase();
    return needle
      ? uniqueValues.filter((value) =>
          value.toLocaleLowerCase().includes(needle),
        )
      : uniqueValues;
  }, [search, uniqueValues]);
  const visibleValues = useMemo(
    () => filteredValues.slice(0, 250),
    [filteredValues],
  );
  const selectedValueSet = filter.selectedValues
    ? new Set(filter.selectedValues)
    : null;
  const selectedFilteredValueCount =
    selectedValueSet === null
      ? filteredValues.length
      : filteredValues.filter((value) => selectedValueSet.has(value)).length;
  const allFilteredValuesSelected =
    filteredValues.length > 0 &&
    selectedFilteredValueCount === filteredValues.length;
  const someFilteredValuesSelected =
    selectedFilteredValueCount > 0 && !allFilteredValuesSelected;
  const activeSortForColumn =
    sorts.find((sort) => sort.columnKey === column.key) ?? null;

  const updateFilter = (nextFilter: LegacyIssueGridFilter) => {
    onFiltersChange({
      ...filters,
      [column.key]: nextFilter,
    });
  };

  const clearFilter = () => {
    const next = { ...filters };
    delete next[column.key];
    onFiltersChange(next);
    onClose();
  };

  const updateSortDirection = (direction: 'asc' | 'desc') => {
    onSortsChange(
      upsertGridSort(sorts, {
        columnKey: column.key,
        direction,
        emptyPlacement: activeSortForColumn?.emptyPlacement,
      }),
    );
  };

  const updateEmptyPlacement = (emptyPlacement: 'first' | 'last') => {
    onSortsChange(
      upsertGridSort(sorts, {
        columnKey: column.key,
        direction: activeSortForColumn?.direction ?? 'asc',
        emptyPlacement,
      }),
    );
  };

  const clearColumnSort = () => {
    onSortsChange(removeGridSort(sorts, column.key));
  };

  const toggleValue = (value: string) => {
    const current = filter.selectedValues ?? uniqueValues;
    const nextValues = current.includes(value)
      ? current.filter((item) => item !== value)
      : [...current, value];
    updateFilter({
      ...filter,
      selectedValues:
        nextValues.length === uniqueValues.length ? null : nextValues,
    });
  };

  const toggleAllFilteredValues = () => {
    if (filteredValues.length === 0) return;
    updateFilter({
      ...filter,
      selectedValues: toggleGridFilterSelectedValues({
        allValues: uniqueValues,
        filteredValues,
        selectedValues: filter.selectedValues,
      }),
    });
  };

  return (
    <div
      className="fixed z-30 w-80 rounded-md border border-app-border bg-app-bg p-3 shadow-xl"
      style={{ left: menu.x, top: menu.y }}
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="truncate app-text-caption font-semibold">
          {column.title}
        </span>
        <button
          aria-label={t('coreBusiness.grid.close')}
          className="flex size-6 items-center justify-center rounded hover:bg-app-surface-hover"
          type="button"
          onClick={onClose}
        >
          <X size={14} />
        </button>
      </div>
      <div className="mb-2 grid grid-cols-2 gap-2">
        <button
          className={cn(
            'inline-flex h-8 items-center justify-center gap-1 rounded-md border px-2 app-text-caption',
            activeSortForColumn?.direction === 'asc'
              ? 'border-app-accent bg-app-accent/10 text-app-accent'
              : 'border-app-border hover:bg-app-surface-hover',
          )}
          type="button"
          onClick={() => updateSortDirection('asc')}
        >
          <ChevronUp size={14} />
          {t('coreBusiness.grid.sortAsc')}
        </button>
        <button
          className={cn(
            'inline-flex h-8 items-center justify-center gap-1 rounded-md border px-2 app-text-caption',
            activeSortForColumn?.direction === 'desc'
              ? 'border-app-accent bg-app-accent/10 text-app-accent'
              : 'border-app-border hover:bg-app-surface-hover',
          )}
          type="button"
          onClick={() => updateSortDirection('desc')}
        >
          <ChevronDown size={14} />
          {t('coreBusiness.grid.sortDesc')}
        </button>
      </div>
      <div className="mb-2 grid grid-cols-2 gap-2">
        <button
          className="inline-flex h-8 items-center justify-center rounded-md border border-app-border px-2 app-text-caption text-app-ink/65 hover:bg-app-surface-hover disabled:opacity-40"
          disabled={!activeSortForColumn}
          type="button"
          onClick={clearColumnSort}
        >
          {t('coreBusiness.grid.clearSort')}
        </button>
        <button
          className="inline-flex h-8 items-center justify-center rounded-md border border-app-border px-2 app-text-caption text-app-ink/65 hover:bg-app-surface-hover disabled:opacity-40"
          disabled={sorts.length === 0}
          type="button"
          onClick={() => onSortsChange([])}
        >
          {t('coreBusiness.grid.clearAllSorts')}
        </button>
      </div>
      <div className="mb-2 rounded-md border border-app-border bg-app-surface px-2 py-2">
        <div className="mb-1 app-text-micro font-medium text-app-ink/55">
          {t('coreBusiness.grid.emptySortTitle')}
        </div>
        <div className="grid grid-cols-2 gap-2">
          <button
            className={cn(
              'inline-flex h-7 items-center justify-center rounded-md border px-2 app-text-caption',
              activeSortForColumn?.emptyPlacement === 'first'
                ? 'border-app-accent bg-app-accent/10 text-app-accent'
                : 'border-app-border bg-app-bg hover:bg-app-surface-hover',
            )}
            type="button"
            onClick={() => updateEmptyPlacement('first')}
          >
            {t('coreBusiness.grid.emptyFirst')}
          </button>
          <button
            className={cn(
              'inline-flex h-7 items-center justify-center rounded-md border px-2 app-text-caption',
              activeSortForColumn?.emptyPlacement === 'last'
                ? 'border-app-accent bg-app-accent/10 text-app-accent'
                : 'border-app-border bg-app-bg hover:bg-app-surface-hover',
            )}
            type="button"
            onClick={() => updateEmptyPlacement('last')}
          >
            {t('coreBusiness.grid.emptyLast')}
          </button>
        </div>
      </div>
      <input
        className="mb-2 h-8 w-full rounded-md border border-app-border bg-app-bg px-2 app-text-caption outline-none focus:border-app-accent"
        placeholder={t('coreBusiness.grid.filterPlaceholder')}
        value={filter.text}
        onChange={(event) =>
          updateFilter({ ...filter, text: event.target.value })
        }
      />
      <div className="mb-2 flex items-center justify-end gap-2">
        <button
          className="rounded px-1.5 py-1 app-text-caption text-app-ink/60 hover:bg-app-surface-hover"
          type="button"
          onClick={clearFilter}
        >
          {t('coreBusiness.grid.clear')}
        </button>
      </div>
      <input
        className="mb-2 h-8 w-full rounded-md border border-app-border bg-app-bg px-2 app-text-caption outline-none focus:border-app-accent"
        placeholder={t('coreBusiness.grid.valueSearchPlaceholder')}
        value={search}
        onChange={(event) => onSearchChange(event.target.value)}
      />
      <div className="max-h-56 overflow-y-auto rounded border border-app-border">
        <button
          className="sticky top-0 z-10 flex w-full items-center gap-2 border-b border-app-border bg-app-bg px-2 py-1.5 text-left app-text-caption hover:bg-app-surface-hover disabled:opacity-45"
          disabled={filteredValues.length === 0}
          type="button"
          onClick={toggleAllFilteredValues}
        >
          <span
            className={cn(
              'flex size-4 items-center justify-center rounded border',
              allFilteredValuesSelected || someFilteredValuesSelected
                ? 'border-app-accent bg-app-accent text-app-accent-fg'
                : 'border-app-border',
            )}
          >
            {allFilteredValuesSelected ? <Check size={12} /> : null}
            {someFilteredValuesSelected ? <Minus size={12} /> : null}
          </span>
          <span className="truncate">{t('coreBusiness.grid.selectAll')}</span>
        </button>
        {visibleValues.length === 0 ? (
          <div className="px-3 py-4 app-text-caption text-app-ink/50">
            {t('coreBusiness.grid.noValues')}
          </div>
        ) : (
          visibleValues.map((value) => {
            const checked =
              selectedValueSet === null || selectedValueSet.has(value);
            return (
              <button
                key={value}
                className="flex w-full items-center gap-2 px-2 py-1.5 text-left app-text-caption hover:bg-app-surface-hover"
                type="button"
                onClick={() => toggleValue(value)}
              >
                <span
                  className={cn(
                    'flex size-4 items-center justify-center rounded border',
                    checked
                      ? 'border-app-accent bg-app-accent text-app-accent-fg'
                      : 'border-app-border',
                  )}
                >
                  {checked ? <Check size={12} /> : null}
                </span>
                <span className="truncate">
                  {value || t('coreBusiness.grid.emptyValue')}
                </span>
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}

function GridNumberStepper({
  decreaseLabel,
  disabled = false,
  increaseLabel,
  label,
  max,
  min,
  onChange,
  value,
}: {
  decreaseLabel: string;
  disabled?: boolean;
  increaseLabel: string;
  label: string;
  max: number;
  min: number;
  onChange: (value: number) => void;
  value: number;
}) {
  const nextValue = Math.min(max, Math.max(min, value));
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="min-w-0 truncate app-text-caption text-app-ink/70">
        {label}
      </span>
      <div className="flex shrink-0 items-center rounded-md border border-app-border bg-app-bg">
        <button
          aria-label={decreaseLabel}
          className="flex size-7 items-center justify-center text-app-ink/55 hover:bg-app-surface-hover disabled:opacity-35"
          disabled={disabled || nextValue <= min}
          type="button"
          onClick={() => onChange(nextValue - 1)}
        >
          <Minus size={13} />
        </button>
        <span className="w-8 border-x border-app-border text-center app-text-caption tabular-nums text-app-ink">
          {nextValue}
        </span>
        <button
          aria-label={increaseLabel}
          className="flex size-7 items-center justify-center text-app-ink/55 hover:bg-app-surface-hover disabled:opacity-35"
          disabled={disabled || nextValue >= max}
          type="button"
          onClick={() => onChange(nextValue + 1)}
        >
          <Plus size={13} />
        </button>
      </div>
    </div>
  );
}

function GridPill({
  icon,
  label,
  onClear,
}: {
  icon: ReactNode;
  label: string;
  onClear: () => void;
}) {
  return (
    <span className="inline-flex max-w-56 items-center gap-1 rounded border border-app-border bg-app-bg px-1.5 py-0.5 app-text-caption text-app-ink/65">
      {icon}
      <span className="truncate">{label}</span>
      <button
        className="rounded hover:bg-app-surface-hover"
        type="button"
        onClick={onClear}
      >
        <X size={12} />
      </button>
    </span>
  );
}

function LegacyIssueGridLoadingBlock({ label }: { label: string }) {
  return (
    <div className="flex min-h-72 flex-1 items-center justify-center gap-2 app-text-body-sm text-app-ink/50">
      <Loader2 size={16} className="animate-spin" />
      <span>{label}</span>
    </div>
  );
}

function LegacyIssueGridEmptyBlock({ label }: { label: string }) {
  return (
    <div className="flex min-h-72 flex-1 items-center justify-center px-6 text-center app-text-body-sm text-app-ink/50">
      {label}
    </div>
  );
}

export function applyGridView<TRecord>({
  columns,
  filters,
  getCellValue,
  records,
  sorts,
}: {
  columns: LegacyIssueGridColumn[];
  filters: Record<string, LegacyIssueGridFilter>;
  getCellValue: (
    record: TRecord,
    columnKey: string,
  ) => string | null | undefined;
  records: TRecord[];
  sorts: readonly LegacyIssueGridSort[];
}): TRecord[] {
  const filtered = records.filter((record) =>
    columns.every((column) => {
      const filter = filters[column.key];
      if (!isFilterActive(filter)) return true;
      const value = normalizeGridValue(getCellValue(record, column.key));
      if (filter.text.trim()) {
        const needle = filter.text.trim().toLocaleLowerCase();
        if (!value.toLocaleLowerCase().includes(needle)) return false;
      }
      if (
        filter.selectedValues !== null &&
        !filter.selectedValues.includes(value)
      ) {
        return false;
      }
      return true;
    }),
  );
  if (sorts.length === 0) return filtered;
  return [...filtered].sort((left, right) => {
    for (const sort of sorts) {
      const result = compareRecordsByGridSort({
        getCellValue,
        left,
        right,
        sort,
      });
      if (result !== 0) return result;
    }
    return 0;
  });
}

function compareRecordsByGridSort<TRecord>({
  getCellValue,
  left,
  right,
  sort,
}: {
  getCellValue: (
    record: TRecord,
    columnKey: string,
  ) => string | null | undefined;
  left: TRecord;
  right: TRecord;
  sort: LegacyIssueGridSort;
}): number {
  const leftRawValue = getCellValue(left, sort.columnKey);
  const rightRawValue = getCellValue(right, sort.columnKey);
  const leftValue = normalizeGridValue(leftRawValue);
  const rightValue = normalizeGridValue(rightRawValue);
  if (sort.emptyPlacement) {
    const leftEmpty = isEmptyGridValue(leftRawValue);
    const rightEmpty = isEmptyGridValue(rightRawValue);
    if (leftEmpty !== rightEmpty) {
      return compareEmptyGridValues({
        emptyPlacement: sort.emptyPlacement,
        leftEmpty,
        rightEmpty,
      });
    }
  }
  return (
    leftValue.localeCompare(rightValue, undefined, {
      numeric: true,
      sensitivity: 'base',
    }) * (sort.direction === 'asc' ? 1 : -1)
  );
}

function upsertGridSort(
  sorts: readonly LegacyIssueGridSort[],
  nextSort: LegacyIssueGridSort,
): LegacyIssueGridSort[] {
  const existingIndex = sorts.findIndex(
    (sort) => sort.columnKey === nextSort.columnKey,
  );
  if (existingIndex < 0) return [...sorts, nextSort];
  return sorts.map((sort, index) =>
    index === existingIndex ? nextSort : sort,
  );
}

function removeGridSort(
  sorts: readonly LegacyIssueGridSort[],
  columnKey: string,
): LegacyIssueGridSort[] {
  return sorts.filter((sort) => sort.columnKey !== columnKey);
}

export function normalizeGridSortPreferences(
  value: unknown,
): LegacyIssueGridSort[] {
  if (!Array.isArray(value)) return [];
  const seenColumnKeys = new Set<string>();
  const sorts: LegacyIssueGridSort[] = [];
  for (const item of value) {
    if (!item || typeof item !== 'object') continue;
    const { columnKey, direction, emptyPlacement } = item as {
      columnKey?: unknown;
      direction?: unknown;
      emptyPlacement?: unknown;
    };
    if (
      typeof columnKey !== 'string' ||
      !columnKey ||
      seenColumnKeys.has(columnKey)
    )
      continue;
    if (direction !== 'asc' && direction !== 'desc') continue;
    const sort: LegacyIssueGridSort = { columnKey, direction };
    if (emptyPlacement === 'first' || emptyPlacement === 'last') {
      sort.emptyPlacement = emptyPlacement;
    }
    sorts.push(sort);
    seenColumnKeys.add(columnKey);
  }
  return sorts;
}

export function normalizeGridScrollPreference(
  value: unknown,
): LegacyIssueGridScrollPreference | null {
  if (!value || typeof value !== 'object') return null;
  const { columnIndex, rowIndex, scrollLeft, scrollTop } = value as {
    columnIndex?: unknown;
    rowIndex?: unknown;
    scrollLeft?: unknown;
    scrollTop?: unknown;
  };
  if (
    typeof columnIndex !== 'number' ||
    typeof rowIndex !== 'number' ||
    typeof scrollLeft !== 'number' ||
    typeof scrollTop !== 'number' ||
    !Number.isFinite(columnIndex) ||
    !Number.isFinite(rowIndex) ||
    !Number.isFinite(scrollLeft) ||
    !Number.isFinite(scrollTop) ||
    columnIndex < 0 ||
    rowIndex < 0 ||
    scrollLeft < 0 ||
    scrollTop < 0
  ) {
    return null;
  }
  return {
    columnIndex: Math.floor(columnIndex),
    rowIndex: Math.floor(rowIndex),
    scrollLeft: Math.round(scrollLeft),
    scrollTop: Math.round(scrollTop),
  };
}

export function getGridScrollPreferenceFromVisibleRegion({
  columns,
  range,
  rowStartOffset,
  tx,
  ty,
}: {
  columns: readonly unknown[];
  range: Pick<Rectangle, 'x' | 'y'>;
  rowStartOffset: number;
  tx: number;
  ty: number;
}): LegacyIssueGridScrollPreference {
  const columnIndex = Math.max(0, Math.floor(range.x));
  const rowIndex = Math.max(0, Math.floor(range.y));
  let columnOffset = 0;
  for (const column of columns.slice(0, columnIndex)) {
    columnOffset += gridColumnWidth(column);
  }
  const scrollLeft = Math.max(0, columnOffset - tx);
  const scrollTop = Math.max(0, rowStartOffset - ty);
  return {
    columnIndex,
    rowIndex,
    scrollLeft: Math.round(scrollLeft),
    scrollTop: Math.round(scrollTop),
  };
}

function gridColumnWidth(column: unknown): number {
  if (!column || typeof column !== 'object') return 0;
  const width = (column as { width?: unknown }).width;
  return typeof width === 'number' && Number.isFinite(width) ? width : 0;
}

export function toggleGridFilterSelectedValues({
  allValues,
  filteredValues,
  selectedValues,
}: {
  allValues: readonly string[];
  filteredValues: readonly string[];
  selectedValues: readonly string[] | null;
}): string[] | null {
  if (filteredValues.length === 0)
    return selectedValues ? [...selectedValues] : null;
  const current = selectedValues ?? allValues;
  const currentSet = new Set(current);
  const allFilteredValuesSelected = filteredValues.every((value) =>
    currentSet.has(value),
  );
  const nextValues = allFilteredValuesSelected
    ? current.filter((value) => !filteredValues.includes(value))
    : Array.from(new Set([...current, ...filteredValues]));
  return nextValues.length === allValues.length ? null : nextValues;
}

export function resolveLegacyIssueGridColumnOrderState(
  current: string[],
  next: readonly string[],
): string[] {
  return areStringArraysEqual(current, next) ? current : [...next];
}

export function resolveLegacyIssueGridPersonalizedColumnOrder({
  columns,
  defaultColumnOrder,
  personalizedColumnOrder,
}: {
  columns: readonly LegacyIssueGridColumn[];
  defaultColumnOrder: readonly string[];
  personalizedColumnOrder: readonly string[] | null;
}): string[] {
  const baseOrder = applyGridColumnOrder(columns, defaultColumnOrder).map(
    (column) => column.key,
  );
  if (!personalizedColumnOrder) return baseOrder;
  const availableKeys = new Set(baseOrder);
  const seen = new Set<string>();
  const personalized = personalizedColumnOrder.filter((key) => {
    if (!availableKeys.has(key) || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  return [
    ...personalized,
    ...baseOrder.filter((columnKey) => !seen.has(columnKey)),
  ];
}

export function resolveLegacyIssueGridHiddenColumnKeys(
  columns: readonly LegacyIssueGridColumn[],
  hiddenColumnKeys: readonly string[],
): string[] {
  const availableKeys = new Set(columns.map((column) => column.key));
  const seen = new Set<string>();
  const hidden = hiddenColumnKeys.filter((key) => {
    if (!availableKeys.has(key) || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  if (columns.length > 0 && hidden.length >= columns.length) {
    return hidden.filter((key) => key !== columns[0]?.key);
  }
  return hidden;
}

function appendMissingLegacyIssueGridColumnKeys(
  current: readonly string[],
  columns: readonly LegacyIssueGridColumn[],
): string[] {
  const availableKeys = new Set(columns.map((column) => column.key));
  const seen = new Set<string>();
  const next = current.filter((key) => {
    if (!availableKeys.has(key) || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  for (const column of columns) {
    if (seen.has(column.key)) continue;
    seen.add(column.key);
    next.push(column.key);
  }
  return areStringArraysEqual(current, next) ? [...current] : next;
}

export function isLegacyIssueGridColumnLayoutEqual(
  current: LegacyIssueGridColumnLayout | null,
  next: LegacyIssueGridColumnLayout,
): boolean {
  return (
    current?.layoutId === next.layoutId &&
    areStringArraysEqual(current.columnKeys, next.columnKeys)
  );
}

export function isLegacyIssueGridRowLayoutEqual(
  current: LegacyIssueGridRowLayout | null,
  next: LegacyIssueGridRowLayout,
): boolean {
  return (
    current?.layoutId === next.layoutId &&
    current.viewApplied === next.viewApplied &&
    areStringArraysEqual(current.recordIds, next.recordIds)
  );
}

function areStringArraysEqual(
  left: readonly string[],
  right: readonly string[],
): boolean {
  return (
    left.length === right.length &&
    left.every((value, index) => value === right[index])
  );
}

export function applyGridColumnOrder(
  columns: readonly LegacyIssueGridColumn[],
  columnOrder: readonly string[],
): LegacyIssueGridColumn[] {
  if (columnOrder.length === 0) return [...columns];
  const columnByKey = new Map(columns.map((column) => [column.key, column]));
  const orderedColumns = columnOrder
    .map((key) => columnByKey.get(key))
    .filter((column): column is LegacyIssueGridColumn => Boolean(column));
  const orderedKeySet = new Set(orderedColumns.map((column) => column.key));
  const mergedColumns = [...orderedColumns];
  for (const column of columns) {
    if (orderedKeySet.has(column.key)) continue;
    mergedColumns.splice(
      missingGridColumnInsertIndex(column.key, mergedColumns, columns),
      0,
      column,
    );
    orderedKeySet.add(column.key);
  }
  return mergedColumns;
}

export function resolveLegacyIssueVisibleGridColumns({
  columns,
  hiddenColumnKeys,
}: {
  columns: readonly LegacyIssueGridColumn[];
  hiddenColumnKeys: ReadonlySet<string>;
}): LegacyIssueGridColumn[] {
  const visibleColumns = columns.filter(
    (column) => !hiddenColumnKeys.has(column.key),
  );
  return visibleColumns.length > 0 ? visibleColumns : columns.slice(0, 1);
}

function missingGridColumnInsertIndex(
  key: string,
  orderedColumns: readonly LegacyIssueGridColumn[],
  defaultColumns: readonly LegacyIssueGridColumn[],
): number {
  const defaultIndex = defaultColumns.findIndex((column) => column.key === key);
  if (defaultIndex < 0) return orderedColumns.length;
  for (let index = defaultIndex - 1; index >= 0; index -= 1) {
    const orderedIndex = orderedColumns.findIndex(
      (column) => column.key === defaultColumns[index]?.key,
    );
    if (orderedIndex >= 0) return orderedIndex + 1;
  }
  for (
    let index = defaultIndex + 1;
    index < defaultColumns.length;
    index += 1
  ) {
    const orderedIndex = orderedColumns.findIndex(
      (column) => column.key === defaultColumns[index]?.key,
    );
    if (orderedIndex >= 0) return orderedIndex;
  }
  return orderedColumns.length;
}

export function moveVisibleGridColumn({
  columns,
  currentOrder,
  fromVisibleIndex,
  toVisibleIndex,
  visibleColumns,
}: {
  columns: readonly LegacyIssueGridColumn[];
  currentOrder: readonly string[];
  fromVisibleIndex: number;
  toVisibleIndex: number;
  visibleColumns: readonly LegacyIssueGridColumn[];
}): string[] {
  if (
    fromVisibleIndex === toVisibleIndex ||
    fromVisibleIndex < 0 ||
    toVisibleIndex < 0 ||
    fromVisibleIndex >= visibleColumns.length ||
    toVisibleIndex >= visibleColumns.length
  ) {
    return sanitizeGridColumnOrder(columns, currentOrder);
  }

  const baseOrder = applyGridColumnOrder(columns, currentOrder).map(
    (column) => column.key,
  );
  const nextVisibleOrder = moveArrayItem(
    visibleColumns.map((column) => column.key),
    fromVisibleIndex,
    toVisibleIndex,
  );
  const visibleKeySet = new Set(visibleColumns.map((column) => column.key));
  let visibleIndex = 0;
  return baseOrder.map((key) => {
    if (!visibleKeySet.has(key)) return key;
    const nextKey = nextVisibleOrder[visibleIndex];
    visibleIndex += 1;
    return nextKey ?? key;
  });
}

export function getLegacyIssueContextRowIndexes({
  rowCount,
  rowIndex,
  selection,
}: {
  rowCount: number;
  rowIndex: number | null;
  selection: LegacyIssueGridSelectionLike;
}): number[] {
  if (rowIndex === null) return [];
  const selectedRows = normalizeLegacyIssueRowIndexes(
    selection?.rows?.toArray() ?? [],
    rowCount,
  );
  if (selectedRows.includes(rowIndex)) return selectedRows;

  const range = selection?.current?.range;
  if (range && rowIndex >= range.y && rowIndex < range.y + range.height) {
    const rangeRows: number[] = [];
    const start = Math.max(0, Math.floor(range.y));
    const end = Math.min(rowCount, Math.ceil(range.y + range.height));
    for (let index = start; index < end; index += 1) {
      rangeRows.push(index);
    }
    return normalizeLegacyIssueRowIndexes(rangeRows, rowCount);
  }

  return normalizeLegacyIssueRowIndexes([rowIndex], rowCount);
}

export function normalizeLegacyIssueRowIndexes(
  rowIndexes: readonly number[],
  rowCount: number,
): number[] {
  return [...new Set(rowIndexes)]
    .filter((rowIndex) => Number.isInteger(rowIndex))
    .filter((rowIndex) => rowIndex >= 0 && rowIndex < rowCount)
    .sort((left, right) => left - right);
}

export function getRequiredMissingColumnKeysForBlankRowDraft({
  requiredColumnKeys,
  values,
}: {
  requiredColumnKeys: ReadonlySet<string>;
  values: Record<string, string | null>;
}): string[] {
  if (!blankRowDraftHasData(values)) return [];
  return [...requiredColumnKeys].filter(
    (columnKey) => !normalizeGridValue(values[columnKey]).trim(),
  );
}

function isBlankRowRequiredCellMissing({
  columnKey,
  requiredColumnKeys,
  values,
}: {
  columnKey: string;
  requiredColumnKeys: ReadonlySet<string>;
  values: Record<string, string | null>;
}): boolean {
  return getRequiredMissingColumnKeysForBlankRowDraft({
    requiredColumnKeys,
    values,
  }).includes(columnKey);
}

function mergeBlankRowDraftValues(
  current: Record<string, string | null>,
  incoming: Record<string, string | null>,
): Record<string, string | null> {
  const next = { ...current };
  for (const [key, value] of Object.entries(incoming)) {
    if (value === null || !value.trim()) {
      delete next[key];
    } else {
      next[key] = value;
    }
  }
  return next;
}

function blankRowDraftHasData(values: Record<string, string | null>): boolean {
  return Object.values(values).some((value) =>
    normalizeGridValue(value).trim(),
  );
}

function resizeBlankRowDrafts(
  drafts: Array<Record<string, string | null>>,
  size: number,
): Array<Record<string, string | null>> {
  if (drafts.length === size) return drafts;
  if (drafts.length > size) return drafts.slice(0, size);
  return [
    ...drafts,
    ...Array.from({ length: size - drafts.length }, () => ({})),
  ];
}

function replaceBlankRowDraftAt(
  drafts: Array<Record<string, string | null>>,
  rowIndex: number,
  values: Record<string, string | null>,
  size: number,
): Array<Record<string, string | null>> {
  const next = resizeBlankRowDrafts(drafts, size);
  if (rowIndex < 0 || rowIndex >= next.length) return next;
  return next.map((draft, index) => (index === rowIndex ? values : draft));
}

function removeBlankRowDraftsAt(
  drafts: Array<Record<string, string | null>>,
  rowIndexes: readonly number[],
): Array<Record<string, string | null>> {
  const removeIndexes = new Set(
    normalizeLegacyIssueRowIndexes(rowIndexes, drafts.length),
  );
  if (removeIndexes.size === 0) return drafts;
  return drafts.filter((_draft, index) => !removeIndexes.has(index));
}

function sanitizeGridColumnOrder(
  columns: readonly LegacyIssueGridColumn[],
  columnOrder: readonly string[],
): string[] {
  return applyGridColumnOrder(columns, columnOrder).map((column) => column.key);
}

function moveArrayItem<TItem>(
  items: readonly TItem[],
  fromIndex: number,
  toIndex: number,
): TItem[] {
  const next = [...items];
  const [item] = next.splice(fromIndex, 1);
  if (item === undefined) return next;
  next.splice(toIndex, 0, item);
  return next;
}

function sumGridColumnWidths(columns: readonly { width?: number }[]): number {
  return columns.reduce(
    (total, column) => total + getGridColumnWidth(column),
    0,
  );
}

function getGridColumnWidth(column: { width?: number }): number {
  return 'width' in column && typeof column.width === 'number'
    ? column.width
    : 0;
}

function getUniqueColumnValues<TRecord>(
  records: TRecord[],
  columnKey: string,
  getCellValue: (
    record: TRecord,
    columnKey: string,
  ) => string | null | undefined,
): string[] {
  const values = new Set<string>();
  records.forEach((record) => {
    values.add(normalizeGridValue(getCellValue(record, columnKey)));
  });
  return [...values].sort((left, right) =>
    left.localeCompare(right, undefined, {
      numeric: true,
      sensitivity: 'base',
    }),
  );
}

function isEditableColumn(
  columnKey: string,
  readonlyColumnKeys: ReadonlySet<string>,
): boolean {
  return !readonlyColumnKeys.has(columnKey);
}

function isFilterActive(filter: LegacyIssueGridFilter | undefined): boolean {
  if (!filter) return false;
  return Boolean(filter.text.trim()) || filter.selectedValues !== null;
}

export function createLegacyIssueTextCell(
  value: string | null | undefined,
  readonly: boolean,
  options: {
    bgCell?: string;
    dirty?: boolean;
    dirtyBg?: string;
    inputKind?: 'date';
    inputLabel?: string;
    requiredMissing?: boolean;
    searchActive?: boolean;
    searchBg?: string;
    selectOptions?: string[];
    textOverlay?: boolean;
  } = {},
): GridCell {
  const displayData = normalizeGridValue(value);
  const normalizedDisplayData =
    normalizeLegacyIssueGridDisplayData(displayData);
  const bgCell = options.searchActive
    ? options.searchBg
    : options.dirty
      ? options.dirtyBg
      : options.bgCell;
  const cell: LegacyIssueTextCell = {
    allowOverlay: options.textOverlay ?? true,
    allowWrapping: true,
    copyData: displayData,
    data: displayData,
    displayData: normalizedDisplayData,
    kind: GridCellKind.Text,
    legacyIssueRequiredMissing: Boolean(options.requiredMissing),
    readonly,
    themeOverride: bgCell ? { bgCell } : undefined,
  };
  if (options.selectOptions && options.selectOptions.length > 0) {
    cell.legacyIssueSelectOptions = options.selectOptions;
  }
  if (options.inputKind) {
    cell.legacyIssueInputKind = options.inputKind;
    cell.legacyIssueInputLabel = options.inputLabel;
  }
  return cell;
}

type LegacyIssueTextCell = TextCell & {
  legacyIssueInputKind?: 'date';
  legacyIssueInputLabel?: string;
  legacyIssueRequiredMissing?: boolean;
  legacyIssueSelectOptions?: string[];
};

function isLegacyIssueEditableTextCell(
  cell: GridCell,
): cell is LegacyIssueTextCell {
  return cell.kind === GridCellKind.Text && !cell.readonly && cell.allowOverlay;
}

function isLegacyIssueRequiredMissingCell(
  cell: GridCell,
): cell is LegacyIssueTextCell {
  return (
    cell.kind === GridCellKind.Text &&
    Boolean((cell as LegacyIssueTextCell).legacyIssueRequiredMissing)
  );
}

type LegacyIssueGridKeyEvent = Parameters<
  NonNullable<DataEditorProps['onKeyDown']>
>[0];

function isLegacyIssueEditorOpenKey(event: LegacyIssueGridKeyEvent): boolean {
  if (event.altKey || event.ctrlKey || event.metaKey) return false;
  return (
    event.key.length === 1 ||
    event.key === 'Dead' ||
    event.key === 'Process' ||
    event.keyCode === 229
  );
}

function provideLegacyIssueCellEditor(
  cell: GridCell,
): ReturnType<NonNullable<DataEditorProps['provideEditor']>> {
  if (cell.kind !== GridCellKind.Text || cell.readonly) return undefined;
  const legacyIssueCell = cell as LegacyIssueTextCell;
  if (legacyIssueCell.legacyIssueInputKind === 'date') {
    return {
      disablePadding: true,
      disableStyling: true,
      editor: LegacyIssueDateCellEditor,
    };
  }
  const selectOptions = legacyIssueCell.legacyIssueSelectOptions;
  if (selectOptions && selectOptions.length > 0) {
    return {
      disablePadding: true,
      disableStyling: true,
      editor: LegacyIssueSelectCellEditor,
    };
  }
  return undefined;
}

function LegacyIssueSelectCellEditor({
  onChange,
  onFinishedEditing,
  target,
  value,
}: {
  onChange: (newValue: GridCell) => void;
  onFinishedEditing: (newValue?: GridCell) => void;
  target: Rectangle;
  value: GridCell;
}) {
  const { t } = useTranslation(['common']);
  const cell = value as LegacyIssueTextCell;
  const options = cell.legacyIssueSelectOptions ?? [];
  const currentValue = cell.data ?? '';
  const latestCellRef = useRef<LegacyIssueTextCell>(cell);
  const finishedRef = useRef(false);

  function finish(nextValue: string) {
    const nextCell: LegacyIssueTextCell = {
      ...cell,
      data: nextValue,
      displayData: nextValue,
      copyData: nextValue,
    };
    latestCellRef.current = nextCell;
    finishedRef.current = true;
    onChange(nextCell);
    onFinishedEditing(nextCell);
  }

  function finishWithLatestValue() {
    if (finishedRef.current) return;
    finishedRef.current = true;
    onFinishedEditing(latestCellRef.current);
  }

  return (
    <select
      autoFocus
      className="app-field-input-sm h-full border-app-accent"
      style={{
        minHeight: target.height,
        minWidth: Math.max(target.width, 120),
      }}
      value={currentValue}
      onBlur={finishWithLatestValue}
      onChange={(event) => finish(event.target.value)}
      onKeyDown={(event) => {
        if (event.key === 'Enter') {
          event.preventDefault();
          finish(event.currentTarget.value);
        }
        if (event.key === 'Escape') {
          event.preventDefault();
          finishedRef.current = true;
          onFinishedEditing(cell);
        }
      }}
    >
      <option value="">{t('empty.none')}</option>
      {options.map((option) => (
        <option key={option} value={option}>
          {option}
        </option>
      ))}
    </select>
  );
}

export function LegacyIssueDateCellEditor({
  onChange,
  onFinishedEditing,
  target,
  value,
}: {
  onChange: (newValue: GridCell) => void;
  onFinishedEditing: (newValue?: GridCell) => void;
  target: Rectangle;
  value: GridCell;
}) {
  const cell = value as LegacyIssueTextCell;
  const latestCellRef = useRef<LegacyIssueTextCell>(cell);
  const finishedRef = useRef(false);

  function update(nextValue: string) {
    const normalized = normalizeLegacyIssueDateInput(nextValue);
    if (normalized === undefined) return false;
    const displayValue = normalized ?? '';
    const nextCell: LegacyIssueTextCell = {
      ...cell,
      copyData: displayValue,
      data: displayValue,
      displayData: displayValue,
    };
    latestCellRef.current = nextCell;
    onChange(nextCell);
    return true;
  }

  function finishWithLatestValue() {
    if (finishedRef.current) return;
    finishedRef.current = true;
    onFinishedEditing(latestCellRef.current);
  }

  return (
    <input
      aria-label={cell.legacyIssueInputLabel}
      autoFocus
      className="app-field-input-sm h-full border-app-accent"
      style={{
        minHeight: target.height,
        minWidth: Math.max(target.width, 140),
      }}
      type="date"
      value={String(latestCellRef.current.data ?? '')}
      onBlur={finishWithLatestValue}
      onChange={(event) => update(event.target.value)}
      onPaste={(event) => {
        const pastedValue =
          event.clipboardData.getData('text/plain') ||
          event.clipboardData.getData('text');
        if (!update(pastedValue)) return;
        event.preventDefault();
        event.stopPropagation();
        finishWithLatestValue();
      }}
      onKeyDown={(event) => {
        if (event.key === 'Enter') {
          event.preventDefault();
          update(event.currentTarget.value);
          finishWithLatestValue();
        }
        if (event.key === 'Escape') {
          event.preventDefault();
          finishedRef.current = true;
          onFinishedEditing(cell);
        }
      }}
    />
  );
}

export function coerceLegacyIssuePasteCellValue(
  value: string,
  cell: GridCell,
): GridCell | undefined {
  if (
    cell.kind !== GridCellKind.Text ||
    (cell as LegacyIssueTextCell).legacyIssueInputKind !== 'date'
  ) {
    return undefined;
  }
  const dateCell = cell as LegacyIssueTextCell;
  const normalized = normalizeLegacyIssueDateInput(value);
  if (normalized === undefined) return dateCell;
  const displayValue = normalized ?? '';
  return {
    ...dateCell,
    copyData: displayValue,
    data: displayValue,
    displayData: displayValue,
  };
}

function editableCellToText(cell: EditableGridCell): string {
  if (cell.kind === GridCellKind.Text) {
    return String(cell.data ?? '');
  }
  if ('data' in cell) {
    return String(cell.data ?? '');
  }
  return '';
}

function normalizeGridValue(value: string | null | undefined): string {
  return value ?? '';
}

export function normalizeLegacyIssueGridDisplayData(value: string): string {
  return value
    .replace(/\r\n?/g, '\n')
    .replace(/[^\S\n]+/g, ' ')
    .slice(0, 1_000);
}

export function getLegacyIssueGridRowHeight({
  columns,
  getCellValue,
}: {
  columns: readonly Pick<LegacyIssueGridColumn, 'key' | 'width'>[];
  getCellValue: (columnKey: string) => string | null | undefined;
}): number {
  let rowLineCount = 1;
  for (const column of columns) {
    const value = normalizeLegacyIssueGridDisplayData(
      normalizeGridValue(getCellValue(column.key)),
    );
    if (!value) continue;
    const availableWidth = Math.max(
      1,
      column.width - GRID_TEXT_HORIZONTAL_PADDING,
    );
    let cellLineCount = 0;
    for (const line of value.split('\n')) {
      cellLineCount += getLegacyIssueGridWrappedLineCount(
        line,
        availableWidth,
        GRID_MAX_AUTO_LINE_COUNT - cellLineCount,
      );
      if (cellLineCount >= GRID_MAX_AUTO_LINE_COUNT) break;
    }
    rowLineCount = Math.max(rowLineCount, cellLineCount);
    if (rowLineCount >= GRID_MAX_AUTO_LINE_COUNT) {
      return GRID_MAX_AUTO_ROW_HEIGHT;
    }
  }
  return Math.max(
    GRID_ROW_HEIGHT,
    GRID_TEXT_VERTICAL_PADDING + rowLineCount * GRID_TEXT_LINE_HEIGHT,
  );
}

export function buildLegacyIssueGridRowOffsets(
  rowHeights: readonly number[],
): number[] {
  const offsets = [0];
  for (const rowHeight of rowHeights) {
    offsets.push((offsets.at(-1) ?? 0) + rowHeight);
  }
  return offsets;
}

function getLegacyIssueGridWrappedLineCount(
  value: string,
  availableWidth: number,
  maximumLineCount: number,
): number {
  if (!value) return 1;
  if (value.length <= Math.floor(availableWidth / 13)) return 1;

  const tokens = value.match(/\S+|\s+/g) ?? [value];
  let lineCount = 1;
  let currentLineWidth = 0;
  let pendingSpaceWidth = 0;

  for (const token of tokens) {
    if (token.trim() === '') {
      if (currentLineWidth > 0) {
        pendingSpaceWidth = estimateLegacyIssueGridTextWidth(' ');
      }
      continue;
    }

    const tokenWidth = estimateLegacyIssueGridTextWidth(token);
    if (tokenWidth <= availableWidth) {
      const combinedWidth = currentLineWidth + pendingSpaceWidth + tokenWidth;
      if (currentLineWidth === 0 || combinedWidth <= availableWidth) {
        currentLineWidth = combinedWidth;
      } else {
        lineCount += 1;
        if (lineCount >= maximumLineCount) return maximumLineCount;
        currentLineWidth = tokenWidth;
      }
      pendingSpaceWidth = 0;
      continue;
    }

    if (currentLineWidth > 0) {
      lineCount += 1;
      if (lineCount >= maximumLineCount) return maximumLineCount;
      currentLineWidth = 0;
    }
    pendingSpaceWidth = 0;
    for (const character of token) {
      const characterWidth = estimateLegacyIssueGridTextWidth(character);
      if (
        currentLineWidth > 0 &&
        currentLineWidth + characterWidth > availableWidth
      ) {
        lineCount += 1;
        if (lineCount >= maximumLineCount) return maximumLineCount;
        currentLineWidth = 0;
      }
      currentLineWidth += Math.min(characterWidth, availableWidth);
    }
  }

  return lineCount;
}

function estimateLegacyIssueGridTextWidth(value: string): number {
  let width = 0;
  for (const character of value) {
    const codePoint = character.codePointAt(0) ?? 0;
    if (codePoint === 9) {
      width += 28;
    } else if (codePoint === 32) {
      width += 4;
    } else if (codePoint <= 0x7f) {
      width += "ilI.,'`|!:;".includes(character)
        ? 4
        : 'mwMW@#%&'.includes(character)
          ? 10
          : 7;
    } else if (
      (codePoint >= 0x300 && codePoint <= 0x36f) ||
      (codePoint >= 0xfe00 && codePoint <= 0xfe0f)
    ) {
      continue;
    } else {
      width += 13;
    }
  }
  return width;
}

function isEmptyGridValue(value: string | null | undefined): boolean {
  return normalizeGridValue(value).trim() === '';
}

function compareEmptyGridValues({
  emptyPlacement,
  leftEmpty,
  rightEmpty,
}: {
  emptyPlacement: 'first' | 'last';
  leftEmpty: boolean;
  rightEmpty: boolean;
}): number {
  if (leftEmpty === rightEmpty) return 0;
  if (leftEmpty) return emptyPlacement === 'first' ? -1 : 1;
  return emptyPlacement === 'first' ? 1 : -1;
}

function getRecordGridId(record: unknown): string | null {
  if (!record || typeof record !== 'object') return null;
  const id = (record as { id?: unknown }).id;
  return typeof id === 'string' && id ? id : null;
}

export function legacyIssueGridCellKey(
  recordId: string,
  columnKey: string,
): string {
  return `${recordId}:${columnKey}`;
}

export function isLegacyIssueGridCellChanged({
  changedCellKeys,
  columnKey,
  dirtyCells,
  recordId,
}: {
  changedCellKeys: ReadonlySet<string>;
  columnKey: string;
  dirtyCells: Readonly<Record<string, string>>;
  recordId: string;
}): boolean {
  const key = legacyIssueGridCellKey(recordId, columnKey);
  return dirtyCells[key] !== undefined || changedCellKeys.has(key);
}

function useLegacyIssueGridTheme(): {
  editedCellBg: string;
  editableColumnBg: string;
  frozenBoundaryColor: string;
  newRowBg: string;
  requiredMissingBorder: string;
  searchCellBg: string;
  stripedRowBg: string;
  theme: Partial<GlideTheme>;
} {
  const [theme, setTheme] = useState(() => createLegacyIssueGridTheme());
  useEffect(() => {
    const refreshTheme = () => setTheme(createLegacyIssueGridTheme());
    refreshTheme();
    if (
      typeof document === 'undefined' ||
      typeof MutationObserver === 'undefined'
    ) {
      return undefined;
    }
    const observer = new MutationObserver(refreshTheme);
    observer.observe(document.documentElement, {
      attributeFilter: ['class', 'style'],
      attributes: true,
    });
    return () => observer.disconnect();
  }, []);
  return theme;
}

export function createLegacyIssueGridTheme(): {
  editedCellBg: string;
  editableColumnBg: string;
  frozenBoundaryColor: string;
  newRowBg: string;
  requiredMissingBorder: string;
  searchCellBg: string;
  stripedRowBg: string;
  theme: Partial<GlideTheme>;
} {
  const bg = readCssVariable('--color-app-bg', APP_COLOR_FALLBACKS.bg);
  const surface = readCssVariable(
    '--color-app-surface-sidebar',
    APP_COLOR_FALLBACKS.surfaceSidebar,
  );
  const hover = readCssVariable(
    '--color-app-surface-hover',
    APP_COLOR_FALLBACKS.surfaceHover,
  );
  const border = readCssVariable(
    '--color-app-border',
    APP_COLOR_FALLBACKS.border,
  );
  const ink = readCssVariable('--color-app-ink', APP_COLOR_FALLBACKS.ink);
  const accent = readCssVariable(
    '--color-app-accent',
    APP_COLOR_FALLBACKS.accent,
  );
  return {
    editedCellBg: APP_GRID_HIGHLIGHT_COLORS.editedCellBg,
    editableColumnBg: 'rgba(37, 99, 235, 0.045)',
    frozenBoundaryColor:
      'color-mix(in srgb, var(--color-app-accent) 55%, var(--color-app-border))',
    newRowBg: readCssVariable(
      '--color-app-surface-muted',
      APP_COLOR_FALLBACKS.surfaceMuted,
    ),
    requiredMissingBorder: APP_COLOR_FALLBACKS.danger,
    searchCellBg: APP_GRID_HIGHLIGHT_COLORS.searchCellBg,
    stripedRowBg: surface,
    theme: {
      accentColor: accent,
      accentFg: bg,
      bgCell: bg,
      bgCellMedium: surface,
      bgHeader: surface,
      bgHeaderHasFocus: hover,
      bgHeaderHovered: hover,
      borderColor: border,
      drilldownBorder: border,
      fgIconHeader: ink,
      fontFamily: 'inherit',
      headerFontStyle: '600 12px',
      textDark: ink,
      textGroupHeader: ink,
      textHeader: ink,
      textLight: readCssVariable(
        '--color-app-ink-muted',
        APP_COLOR_FALLBACKS.inkMuted,
      ),
      textMedium: ink,
    },
  };
}

function readCssVariable(name: string, fallback: string): string {
  if (typeof document === 'undefined') return fallback;
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  return value || fallback;
}
