import { BarChartCard, LineChartCard, type ChartSeries } from '@ai-do/ui';
import { AlertTriangle } from 'lucide-react';
import { useId, useMemo } from 'react';
import { useTranslation } from 'react-i18next';

type AnalysisMode =
  | 'metadata'
  | 'analytics'
  | 'semantic'
  | 'hybrid'
  | 'generated';

type AnalysisExactness = 'exact' | 'literal_match' | 'generated';
type AnalysisDataSource = 'legacy_issues' | 'vehicle_checklists';

type AnalysisShape =
  | 'scalar'
  | 'table'
  | 'bar'
  | 'time_series'
  | 'crosstab'
  | 'detail';

type AnalysisCell = string | number | null;

interface AnalysisScope {
  dataset_key: string;
  data_sources?: AnalysisDataSource[];
  module_keys: string[];
  revision_ids: string[];
  checklist_ids?: string[];
  source_count?: number;
  source_counts?: Partial<Record<AnalysisDataSource, number>>;
  filters?: unknown[];
  date_field?: string | null;
}

interface AnalysisColumn {
  key: string;
  label: string;
  type: 'text' | 'number' | 'date' | 'percent';
  role: 'dimension' | 'metric';
}

interface AnalysisCoverage {
  field_key: string;
  label: string;
  present_count: number;
  missing_count: number;
  invalid_count: number;
}

interface AnalysisQuery {
  id: string;
  title: string;
  family_id: string;
  family_version: number;
  data_source?: AnalysisDataSource;
  source_count?: number;
  shape: AnalysisShape;
  exactness: string;
  columns: AnalysisColumn[];
  rows: Array<Record<string, AnalysisCell>>;
  totals?: Record<string, AnalysisCell>;
  coverage?: AnalysisCoverage[];
  warnings?: string[];
  truncated: boolean;
}

export interface LegacyIssueAnalysisPayloadV1 {
  version: 1;
  mode: AnalysisMode;
  title: string;
  exactness: AnalysisExactness;
  scope: AnalysisScope;
  queries: AnalysisQuery[];
  warnings?: string[];
}

const ANALYSIS_MODES = new Set<AnalysisMode>([
  'metadata',
  'analytics',
  'semantic',
  'hybrid',
  'generated',
]);
const ANALYSIS_EXACTNESS = new Set<AnalysisExactness>([
  'exact',
  'literal_match',
  'generated',
]);
const ANALYSIS_DATA_SOURCES = new Set<AnalysisDataSource>([
  'legacy_issues',
  'vehicle_checklists',
]);
const ANALYSIS_SHAPES = new Set<AnalysisShape>([
  'scalar',
  'table',
  'bar',
  'time_series',
  'crosstab',
  'detail',
]);
const COLUMN_TYPES = new Set<AnalysisColumn['type']>([
  'text',
  'number',
  'date',
  'percent',
]);
const COLUMN_ROLES = new Set<AnalysisColumn['role']>(['dimension', 'metric']);
const CHART_COLORS = Array.from(
  { length: 8 },
  (_, index) => `var(--ui-color-chart-${index + 1})`,
);

const MAX_QUERY_COUNT = 12;
const MAX_COLUMN_COUNT = 64;
const MAX_ROW_COUNT = 1_000;
const MAX_COVERAGE_COUNT = 128;
const MAX_WARNING_COUNT = 100;

export function LegacyIssueAnalysisArtifact({ content }: { content: string }) {
  const { t } = useTranslation('apps');
  const titleId = useId();
  const parsed = useMemo(
    () => parseLegacyIssueAnalysisPayload(content),
    [content],
  );

  if (!parsed.ok) {
    return <RawAnalysisContent content={content} />;
  }

  const payload = parsed.payload;
  const sourceEntries = Object.entries(
    payload.scope.source_counts ?? {},
  ).filter(
    (entry): entry is [AnalysisDataSource, number] =>
      isSetMember(entry[0], ANALYSIS_DATA_SOURCES) &&
      isNonNegativeInteger(entry[1]),
  );

  return (
    <article className="space-y-5" aria-labelledby={titleId}>
      <header className="space-y-2">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <h2 id={titleId} className="app-text-title-md text-app-ink">
            {payload.title}
          </h2>
          <div className="flex flex-wrap gap-1.5">
            <MetadataBadge value={payload.mode} />
            <MetadataBadge value={payload.exactness} />
          </div>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {sourceEntries.length > 0 ? (
            sourceEntries.map(([source, count]) => (
              <MetadataBadge
                key={source}
                value={`${
                  source === 'vehicle_checklists'
                    ? t('coreBusiness.vehicleChecklist.columns.rowCount')
                    : payload.scope.dataset_key
                } · ${formatNumber(count)}`}
              />
            ))
          ) : (
            <MetadataBadge
              value={`${payload.scope.dataset_key} · ${formatNumber(payload.scope.source_count ?? 0)}`}
            />
          )}
          {payload.scope.module_keys.map((moduleKey) => (
            <MetadataBadge key={moduleKey} value={moduleKey} />
          ))}
          {payload.scope.date_field ? (
            <MetadataBadge value={payload.scope.date_field} />
          ) : null}
        </div>
      </header>

      <WarningList warnings={payload.warnings} />

      <div className="space-y-5">
        {payload.queries.map((query) => (
          <AnalysisQueryView key={query.id} query={query} />
        ))}
      </div>
    </article>
  );
}

function AnalysisQueryView({ query }: { query: AnalysisQuery }) {
  const { t } = useTranslation('apps');
  const titleId = useId();

  return (
    <section
      aria-labelledby={titleId}
      className="space-y-3 rounded-lg border border-app-border bg-app-bg p-4"
    >
      <header className="flex flex-wrap items-start justify-between gap-2">
        <h3 id={titleId} className="app-text-title-sm text-app-ink">
          {query.title}
        </h3>
        <div className="flex flex-wrap gap-1.5">
          <MetadataBadge value={`${query.family_id}@${query.family_version}`} />
          {query.data_source ? (
            <MetadataBadge
              value={`${
                query.data_source === 'vehicle_checklists'
                  ? t('coreBusiness.vehicleChecklist.columns.rowCount')
                  : query.data_source
              }${
                query.source_count === undefined
                  ? ''
                  : ` · ${formatNumber(query.source_count)}`
              }`}
            />
          ) : null}
          <MetadataBadge value={query.exactness} />
        </div>
      </header>

      <WarningList warnings={query.warnings} />

      {query.shape === 'scalar' ? (
        <ScalarResult query={query} />
      ) : query.shape === 'bar' || query.shape === 'time_series' ? (
        <ChartResult query={query} />
      ) : query.shape === 'detail' ? (
        <DetailResult query={query} />
      ) : (
        <AnalysisTable query={query} />
      )}

      <CoverageList coverage={query.coverage} />
    </section>
  );
}

function ScalarResult({ query }: { query: AnalysisQuery }) {
  const row = query.rows[0];
  const metrics = query.columns.filter(
    (column) => column.role === 'metric' && row?.[column.key] !== undefined,
  );

  if (!row || metrics.length === 0) {
    return <AnalysisTable query={query} />;
  }

  return (
    <dl className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {metrics.map((column) => (
        <div
          key={column.key}
          className="rounded-md border border-app-border bg-app-surface px-4 py-3"
        >
          <dt className="app-text-caption text-app-ink/55">{column.label}</dt>
          <dd className="mt-1 app-text-title-lg tabular-nums text-app-ink">
            {formatCell(row[column.key], column)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function ChartResult({ query }: { query: AnalysisQuery }) {
  const chartId = useId();
  const dimension = query.columns.find((column) => column.role === 'dimension');
  const metrics = query.columns.filter(
    (column) =>
      column.role === 'metric' &&
      (column.type === 'number' || column.type === 'percent'),
  );

  if (!dimension || metrics.length === 0 || query.rows.length === 0) {
    return <AnalysisTable query={query} />;
  }

  const chartRows = query.rows.filter((row) =>
    metrics.every((metric) => typeof row[metric.key] === 'number'),
  );
  if (chartRows.length === 0) {
    return <AnalysisTable query={query} />;
  }

  const categories = chartRows.map((row) =>
    formatCell(row[dimension.key], dimension),
  );
  const series: ChartSeries[] = metrics.map((metric, index) => ({
    key: metric.key,
    label: metric.label,
    color: CHART_COLORS[index % CHART_COLORS.length],
    data: chartRows.map((row) => row[metric.key] as number),
  }));
  const chartQuery = { ...query, rows: chartRows };

  return (
    <>
      <figure aria-labelledby={chartId}>
        <figcaption id={chartId} className="sr-only">
          {query.title}
        </figcaption>
        {query.shape === 'time_series' ? (
          <LineChartCard
            categories={categories}
            series={series}
            title={query.title}
          />
        ) : (
          <BarChartCard
            categories={categories}
            series={series}
            title={query.title}
          />
        )}
      </figure>
      <div className="sr-only">
        <AnalysisTable query={chartQuery} />
      </div>
    </>
  );
}

function AnalysisTable({ query }: { query: AnalysisQuery }) {
  return (
    <div className="custom-scrollbar overflow-auto rounded-md border border-app-border">
      <table className="min-w-full border-collapse bg-app-surface app-text-caption">
        <caption className="sr-only">{query.title}</caption>
        <thead className="bg-app-surface-sidebar text-left text-app-ink/55">
          <tr>
            {query.columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className="whitespace-nowrap border-b border-app-border px-3 py-2 font-semibold"
              >
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-app-border">
          {query.rows.map((row, index) => (
            <tr key={`${query.id}-${index}`}>
              {query.columns.map((column) => (
                <td
                  key={column.key}
                  className={`px-3 py-2 text-app-ink/75 ${
                    column.role === 'metric' ? 'text-right tabular-nums' : ''
                  }`}
                >
                  {formatCell(row[column.key], column)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
        {query.totals ? (
          <tfoot className="border-t-2 border-app-border bg-app-bg font-semibold text-app-ink">
            <tr>
              {query.columns.map((column) => (
                <td
                  key={column.key}
                  className={`px-3 py-2 ${
                    column.role === 'metric' ? 'text-right tabular-nums' : ''
                  }`}
                >
                  {formatCell(query.totals?.[column.key], column)}
                </td>
              ))}
            </tr>
          </tfoot>
        ) : null}
      </table>
    </div>
  );
}

function DetailResult({ query }: { query: AnalysisQuery }) {
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      {query.rows.map((row, index) => (
        <article
          key={`${query.id}-${index}`}
          className="rounded-md border border-app-border bg-app-surface p-4"
        >
          <dl className="grid grid-cols-[minmax(7rem,auto)_minmax(0,1fr)] gap-x-4 gap-y-2 app-text-caption">
            {query.columns.map((column) => (
              <div key={column.key} className="contents">
                <dt className="text-app-ink/55">{column.label}</dt>
                <dd
                  className={`min-w-0 whitespace-pre-wrap break-words text-app-ink ${
                    column.role === 'metric' ? 'tabular-nums' : ''
                  }`}
                >
                  {formatCell(row[column.key], column)}
                </dd>
              </div>
            ))}
          </dl>
        </article>
      ))}
    </div>
  );
}

function CoverageList({
  coverage,
}: {
  coverage: AnalysisCoverage[] | undefined;
}) {
  if (!coverage?.length) {
    return null;
  }

  return (
    <ul className="grid gap-2 md:grid-cols-2">
      {coverage.map((item) => {
        const total =
          item.present_count + item.missing_count + item.invalid_count;
        const presentWidth = ratio(item.present_count, total);
        const missingWidth = ratio(item.missing_count, total);
        const invalidWidth = ratio(item.invalid_count, total);
        const values = [
          item.present_count,
          item.missing_count,
          item.invalid_count,
        ];

        return (
          <li
            key={item.field_key}
            className="rounded-md border border-app-border bg-app-surface px-3 py-2"
            title={item.field_key}
          >
            <div className="flex items-center justify-between gap-3 app-text-caption">
              <span className="truncate font-medium text-app-ink">
                {item.label}
              </span>
              <span className="shrink-0 tabular-nums text-app-ink/60">
                {values.map(formatNumber).join(' / ')}
              </span>
            </div>
            <div
              aria-label={`${item.label} ${values.join(' / ')}`}
              className="mt-2 flex h-1.5 overflow-hidden rounded-full bg-app-surface-hover"
              role="img"
            >
              <span
                aria-hidden="true"
                className="bg-[var(--ui-color-chart-2)]"
                style={{ width: `${presentWidth}%` }}
              />
              <span
                aria-hidden="true"
                className="bg-[var(--ui-color-chart-6)]"
                style={{ width: `${missingWidth}%` }}
              />
              <span
                aria-hidden="true"
                className="bg-[var(--ui-color-chart-4)]"
                style={{ width: `${invalidWidth}%` }}
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function WarningList({ warnings }: { warnings: string[] | undefined }) {
  if (!warnings?.length) {
    return null;
  }

  return (
    <ul className="space-y-1.5" role="status">
      {warnings.map((warning, index) => (
        <li
          key={`${warning}-${index}`}
          className="flex items-start gap-2 rounded-md border border-[var(--ui-color-warning-border)] bg-[var(--ui-color-warning-bg)] px-3 py-2 app-text-caption text-app-ink"
        >
          <AlertTriangle
            aria-hidden="true"
            className="mt-0.5 shrink-0 text-[var(--ui-color-warning)]"
            size={14}
          />
          <span>{warning}</span>
        </li>
      ))}
    </ul>
  );
}

function MetadataBadge({ value }: { value: string }) {
  return (
    <span className="inline-flex min-h-6 items-center rounded-md border border-app-border bg-app-surface px-2 app-text-micro text-app-ink/60">
      {value}
    </span>
  );
}

function RawAnalysisContent({ content }: { content: string }) {
  return (
    <pre className="custom-scrollbar max-h-[40rem] overflow-auto whitespace-pre-wrap break-words rounded-md border border-app-border bg-app-bg p-4 app-text-caption text-app-ink/75">
      {content}
    </pre>
  );
}

export function parseLegacyIssueAnalysisPayload(
  content: string,
): { ok: true; payload: LegacyIssueAnalysisPayloadV1 } | { ok: false } {
  let value: unknown;
  try {
    value = JSON.parse(content) as unknown;
  } catch {
    return { ok: false };
  }

  if (!isRecord(value) || value.version !== 1) {
    return { ok: false };
  }
  if (
    !isSetMember(value.mode, ANALYSIS_MODES) ||
    !isNonEmptyString(value.title) ||
    !isSetMember(value.exactness, ANALYSIS_EXACTNESS) ||
    !isAnalysisScope(value.scope) ||
    !Array.isArray(value.queries) ||
    value.queries.length > MAX_QUERY_COUNT ||
    !value.queries.every(isAnalysisQuery) ||
    !isOptionalStringArray(value.warnings, MAX_WARNING_COUNT)
  ) {
    return { ok: false };
  }
  if (
    !hasConsistentSourceProvenance(
      value.scope as AnalysisScope,
      value.queries as AnalysisQuery[],
    )
  ) {
    return { ok: false };
  }

  return {
    ok: true,
    payload: value as unknown as LegacyIssueAnalysisPayloadV1,
  };
}

function isAnalysisScope(value: unknown): value is AnalysisScope {
  if (!isRecord(value)) {
    return false;
  }
  return (
    isNonEmptyString(value.dataset_key) &&
    (value.data_sources === undefined ||
      (Array.isArray(value.data_sources) &&
        new Set(value.data_sources).size === value.data_sources.length &&
        value.data_sources.every((source) =>
          isSetMember(source, ANALYSIS_DATA_SOURCES),
        ))) &&
    isStringArray(value.module_keys) &&
    isStringArray(value.revision_ids) &&
    (value.checklist_ids === undefined || isStringArray(value.checklist_ids)) &&
    (value.source_count === undefined ||
      isNonNegativeInteger(value.source_count)) &&
    (value.source_counts === undefined ||
      (isRecord(value.source_counts) &&
        Object.entries(value.source_counts).every(
          ([source, count]) =>
            isSetMember(source, ANALYSIS_DATA_SOURCES) &&
            isNonNegativeInteger(count),
        ))) &&
    (value.filters === undefined || Array.isArray(value.filters)) &&
    (value.date_field === undefined ||
      value.date_field === null ||
      typeof value.date_field === 'string')
  );
}

function hasConsistentSourceProvenance(
  scope: AnalysisScope,
  queries: AnalysisQuery[],
): boolean {
  const sources = scope.data_sources;
  if (sources === undefined) {
    return queries.every(
      (query) =>
        query.data_source === undefined && query.source_count === undefined,
    );
  }
  if (sources.length === 0 || scope.source_counts === undefined) {
    return false;
  }
  const countKeys = Object.keys(scope.source_counts);
  if (
    countKeys.length !== sources.length ||
    sources.some(
      (source) => !isNonNegativeInteger(scope.source_counts?.[source]),
    )
  ) {
    return false;
  }
  if (sources.length > 1 && scope.source_count !== undefined) {
    return false;
  }
  if (
    sources.length === 1 &&
    scope.source_count !== undefined &&
    scope.source_count !== scope.source_counts[sources[0]]
  ) {
    return false;
  }
  return queries.every(
    (query) =>
      query.data_source !== undefined &&
      sources.includes(query.data_source) &&
      query.source_count === scope.source_counts?.[query.data_source],
  );
}

function isAnalysisQuery(value: unknown): value is AnalysisQuery {
  if (!isRecord(value)) {
    return false;
  }
  if (
    !isNonEmptyString(value.id) ||
    !isNonEmptyString(value.title) ||
    !isNonEmptyString(value.family_id) ||
    !isNonNegativeInteger(value.family_version) ||
    (value.data_source !== undefined &&
      !isSetMember(value.data_source, ANALYSIS_DATA_SOURCES)) ||
    (value.source_count !== undefined &&
      !isNonNegativeInteger(value.source_count)) ||
    !isSetMember(value.shape, ANALYSIS_SHAPES) ||
    !isNonEmptyString(value.exactness) ||
    !Array.isArray(value.columns) ||
    value.columns.length > MAX_COLUMN_COUNT ||
    !value.columns.every(isAnalysisColumn) ||
    !hasUniqueColumnKeys(value.columns as AnalysisColumn[]) ||
    !Array.isArray(value.rows) ||
    value.rows.length > MAX_ROW_COUNT ||
    !value.rows.every(isAnalysisRow) ||
    (value.totals !== undefined && !isAnalysisRow(value.totals)) ||
    !isOptionalCoverageArray(value.coverage) ||
    !isOptionalStringArray(value.warnings, MAX_WARNING_COUNT) ||
    typeof value.truncated !== 'boolean'
  ) {
    return false;
  }
  return true;
}

function isAnalysisColumn(value: unknown): value is AnalysisColumn {
  return (
    isRecord(value) &&
    isNonEmptyString(value.key) &&
    isNonEmptyString(value.label) &&
    isSetMember(value.type, COLUMN_TYPES) &&
    isSetMember(value.role, COLUMN_ROLES)
  );
}

function hasUniqueColumnKeys(columns: AnalysisColumn[]): boolean {
  return new Set(columns.map((column) => column.key)).size === columns.length;
}

function isAnalysisRow(value: unknown): value is Record<string, AnalysisCell> {
  return (
    isRecord(value) &&
    Object.values(value).every(
      (cell) =>
        cell === null ||
        typeof cell === 'string' ||
        (typeof cell === 'number' && Number.isFinite(cell)),
    )
  );
}

function isOptionalCoverageArray(value: unknown): boolean {
  return (
    value === undefined ||
    (Array.isArray(value) &&
      value.length <= MAX_COVERAGE_COUNT &&
      value.every(isAnalysisCoverage))
  );
}

function isAnalysisCoverage(value: unknown): value is AnalysisCoverage {
  return (
    isRecord(value) &&
    isNonEmptyString(value.field_key) &&
    isNonEmptyString(value.label) &&
    isNonNegativeInteger(value.present_count) &&
    isNonNegativeInteger(value.missing_count) &&
    isNonNegativeInteger(value.invalid_count)
  );
}

function isOptionalStringArray(value: unknown, maxLength: number): boolean {
  return (
    value === undefined ||
    (Array.isArray(value) &&
      value.length <= maxLength &&
      value.every((entry) => typeof entry === 'string'))
  );
}

function isStringArray(value: unknown): value is string[] {
  return (
    Array.isArray(value) && value.every((entry) => typeof entry === 'string')
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}

function isNonNegativeInteger(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;
}

function isSetMember<T extends string>(
  value: unknown,
  values: ReadonlySet<T>,
): value is T {
  return typeof value === 'string' && values.has(value as T);
}

function formatCell(
  value: AnalysisCell | undefined,
  column: AnalysisColumn,
): string {
  if (value === null || value === undefined) {
    return '—';
  }
  if (typeof value === 'number') {
    return formatNumber(value);
  }
  if (column.type === 'number' || column.type === 'percent') {
    const numeric = Number(value);
    if (Number.isFinite(numeric)) {
      return formatNumber(numeric);
    }
  }
  return value;
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat(undefined, {
    maximumFractionDigits: 6,
  }).format(value);
}

function ratio(value: number, total: number): number {
  if (total <= 0) {
    return 0;
  }
  return (value / total) * 100;
}
