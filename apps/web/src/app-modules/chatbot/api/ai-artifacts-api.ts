import { apiFetchJson } from '@/src/platform/api/client';
import { i18n } from '@/src/platform/i18n';

export type AiArtifactKind = 'report' | 'analysis' | string;
export type AiArtifactStatus =
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | string;
export type AiGraphRunStatus =
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | string;

export interface AiArtifact {
  id: string;
  artifactNumber: string | number | null;
  graphRunId: string | null;
  conversationId: string | null;
  conversationTurnId: string | null;
  kind: AiArtifactKind;
  status: AiArtifactStatus;
  title: string;
  contentMarkdown: string;
  createdAt: string | null;
  completedAt: string | null;
}

export interface AiArtifactListResponse {
  items: AiArtifact[];
  total: number;
  limit: number;
  offset: number;
}

export interface AiArtifactSourceColumn {
  key: string;
  label: string;
}

export interface AiArtifactSource {
  id: string;
  sourceKind: string;
  title: string;
  columns: AiArtifactSourceColumn[];
  rows: Array<Record<string, unknown>>;
  rowCount: number;
  truncated: boolean;
  queryId: string | null;
}

export interface AiGraphRun {
  id: string;
  conversationId: string | null;
  status: AiGraphRunStatus;
  currentStage: string | null;
  progressPercent: number | null;
  artifactId: string | null;
  errorCode: string | null;
  createdAt: string | null;
  updatedAt: string | null;
}

export interface AiGraphRunListResponse {
  items: AiGraphRun[];
  total: number;
}

type JsonRecord = Record<string, unknown>;

function aiPath(suffix: string): string {
  return `/api/v1/ai/${suffix}`;
}

export async function listAiArtifacts({
  appId,
  conversationId,
  kind,
  limit = 30,
  offset = 0,
  signal,
  status,
  token,
}: {
  appId?: string | null;
  conversationId?: string | null;
  kind?: string;
  limit?: number;
  offset?: number;
  signal?: AbortSignal;
  status?: string;
  token: string;
}): Promise<AiArtifactListResponse> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  if (kind) {
    // `artifact_type` is the current API field. Keep `kind` in the client
    // vocabulary so callers are not coupled to transport naming.
    params.set('artifact_type', kind);
  }
  if (status) params.set('status', status);
  if (appId) params.set('app_id', appId);
  if (conversationId) params.set('conversation_id', conversationId);

  const raw = await apiFetchJson<unknown>(
    `${aiPath('artifacts')}?${params.toString()}`,
    token,
    { signal },
  );
  const page = asRecord(raw);
  const items = arrayValue(page?.items ?? raw)
    .map(normalizeAiArtifact)
    .filter((artifact): artifact is AiArtifact => artifact !== null)
    .filter(
      (artifact) =>
        (!kind || artifact.kind === kind) &&
        (!status || artifact.status === normalizeArtifactStatus(status)),
    );
  return {
    items,
    total: numberValue(page?.total) ?? items.length,
    limit: numberValue(page?.limit) ?? limit,
    offset: numberValue(page?.offset) ?? offset,
  };
}

export async function getAiArtifact({
  artifactId,
  signal,
  token,
}: {
  artifactId: string;
  signal?: AbortSignal;
  token: string;
}): Promise<AiArtifact> {
  const raw = await apiFetchJson<unknown>(
    aiPath(`artifacts/${encodeURIComponent(artifactId)}`),
    token,
    { signal },
  );
  const artifact = normalizeAiArtifact(raw);
  if (!artifact) {
    throw new Error(i18n.t('apps:ai.errors.invalidArtifactResponse'));
  }
  return artifact;
}

export async function listAiArtifactSources({
  artifactId,
  signal,
  token,
}: {
  artifactId: string;
  signal?: AbortSignal;
  token: string;
}): Promise<AiArtifactSource[]> {
  const raw = await apiFetchJson<unknown>(
    aiPath(`artifacts/${encodeURIComponent(artifactId)}/sources`),
    token,
    { signal },
  );
  const record = asRecord(raw);
  return arrayValue(record?.items ?? record?.sources ?? raw)
    .map(normalizeAiArtifactSource)
    .filter((source): source is AiArtifactSource => source !== null);
}

export async function listAiGraphRuns({
  appId,
  conversationId,
  signal,
  token,
}: {
  appId?: string | null;
  conversationId: string;
  signal?: AbortSignal;
  token: string;
}): Promise<AiGraphRunListResponse> {
  const params = new URLSearchParams({ conversation_id: conversationId });
  if (appId) params.set('app_id', appId);
  const raw = await apiFetchJson<unknown>(
    `${aiPath('graph-runs')}?${params.toString()}`,
    token,
    { signal },
  );
  const page = asRecord(raw);
  const items = arrayValue(page?.items ?? raw)
    .map(normalizeAiGraphRun)
    .filter((run): run is AiGraphRun => run !== null);
  return {
    items,
    total: numberValue(page?.total) ?? items.length,
  };
}

export async function getAiGraphRun({
  runId,
  signal,
  token,
}: {
  runId: string;
  signal?: AbortSignal;
  token: string;
}): Promise<AiGraphRun> {
  const raw = await apiFetchJson<unknown>(
    aiPath(`graph-runs/${encodeURIComponent(runId)}`),
    token,
    { signal },
  );
  const run = normalizeAiGraphRun(raw);
  if (!run) {
    throw new Error(i18n.t('apps:ai.errors.invalidGraphRunResponse'));
  }
  return run;
}

export function normalizeAiArtifact(raw: unknown): AiArtifact | null {
  const value = asRecord(raw);
  const id = stringValue(value?.id ?? value?.artifact_id);
  if (!value || !id) return null;
  return {
    id,
    artifactNumber: identifierValue(
      value.artifact_number ?? value.artifactNumber,
    ),
    graphRunId:
      stringValue(
        value.graph_run_id ?? value.graphRunId ?? value.run_id ?? value.runId,
      ) ?? null,
    conversationId:
      stringValue(value.conversation_id ?? value.conversationId) ?? null,
    conversationTurnId:
      stringValue(
        value.conversation_turn_id ??
          value.conversationTurnId ??
          value.turn_id ??
          value.turnId,
      ) ?? null,
    kind:
      stringValue(
        value.kind ??
          value.artifact_type ??
          value.artifactType ??
          value.artifact_kind ??
          value.artifactKind,
      ) ?? 'analysis',
    status: normalizeArtifactStatus(
      stringValue(value.status ?? value.state) ?? 'completed',
    ),
    title: stringValue(value.title) ?? '',
    contentMarkdown:
      stringValue(
        value.content_markdown ??
          value.contentMarkdown ??
          value.content_text ??
          value.contentText ??
          value.content,
      ) ?? '',
    createdAt: stringValue(value.created_at ?? value.createdAt) ?? null,
    completedAt: stringValue(value.completed_at ?? value.completedAt) ?? null,
  };
}

export function normalizeAiArtifactSource(
  raw: unknown,
): AiArtifactSource | null {
  const value = asRecord(raw);
  const id = stringValue(value?.id ?? value?.source_id);
  if (!value || !id) return null;
  const columns = normalizeSourceColumns(
    value.columns ?? value.grid_columns ?? value.gridColumns,
  );
  const rows = normalizeSourceRows(
    value.rows ?? value.grid_rows ?? value.gridRows,
    columns,
  );
  return {
    id,
    sourceKind:
      stringValue(value.source_kind ?? value.sourceKind ?? value.kind) ??
      'source',
    title: stringValue(value.title) ?? '',
    columns: columns.length ? columns : deriveSourceColumns(rows),
    rows,
    rowCount: numberValue(value.row_count ?? value.rowCount) ?? rows.length,
    truncated: Boolean(value.truncated),
    queryId: stringValue(value.query_id ?? value.queryId) ?? null,
  };
}

export function normalizeAiGraphRun(raw: unknown): AiGraphRun | null {
  const value = asRecord(raw);
  const id = stringValue(value?.id ?? value?.run_id ?? value?.runId);
  if (!value || !id) return null;
  return {
    id,
    conversationId:
      stringValue(value.conversation_id ?? value.conversationId) ?? null,
    status: normalizeGraphRunStatus(
      stringValue(value.status ?? value.state) ?? 'queued',
    ),
    currentStage:
      stringValue(value.current_stage ?? value.currentStage ?? value.stage) ??
      null,
    progressPercent: clampPercent(
      numberValue(value.progress_percent ?? value.progressPercent),
    ),
    artifactId: stringValue(value.artifact_id ?? value.artifactId) ?? null,
    errorCode: stringValue(value.error_code ?? value.errorCode) ?? null,
    createdAt: stringValue(value.created_at ?? value.createdAt) ?? null,
    updatedAt: stringValue(value.updated_at ?? value.updatedAt) ?? null,
  };
}

function normalizeArtifactStatus(status: string): AiArtifactStatus {
  switch (status.toLowerCase()) {
    case 'pending':
      return 'queued';
    case 'building':
    case 'open':
    case 'in_progress':
    case 'streaming':
      return 'running';
    case 'closed':
    case 'done':
    case 'succeeded':
    case 'success':
      return 'completed';
    case 'error':
      return 'failed';
    case 'canceled':
      return 'cancelled';
    default:
      return status.toLowerCase();
  }
}

function normalizeGraphRunStatus(status: string): AiGraphRunStatus {
  switch (status.toLowerCase()) {
    case 'pending':
      return 'queued';
    case 'in_progress':
    case 'streaming':
      return 'running';
    case 'done':
    case 'succeeded':
    case 'success':
      return 'completed';
    case 'error':
      return 'failed';
    case 'canceled':
      return 'cancelled';
    default:
      return status.toLowerCase();
  }
}

function normalizeSourceColumns(raw: unknown): AiArtifactSourceColumn[] {
  return arrayValue(raw).flatMap((column) => {
    if (typeof column === 'string' && column.trim()) {
      return [{ key: column, label: column }];
    }
    const value = asRecord(column);
    const key = stringValue(value?.key ?? value?.name ?? value?.id);
    if (!key) return [];
    return [
      {
        key,
        label: stringValue(value?.label ?? value?.title) ?? key,
      },
    ];
  });
}

function normalizeSourceRows(
  raw: unknown,
  columns: AiArtifactSourceColumn[],
): Array<Record<string, unknown>> {
  return arrayValue(raw).flatMap((row) => {
    const record = asRecord(row);
    if (record) return [record];
    if (!Array.isArray(row)) return [];
    return [
      Object.fromEntries(
        row.map((cell, index) => [
          columns[index]?.key ?? `column_${index + 1}`,
          cell,
        ]),
      ),
    ];
  });
}

function deriveSourceColumns(
  rows: Array<Record<string, unknown>>,
): AiArtifactSourceColumn[] {
  const keys = new Set<string>();
  for (const row of rows.slice(0, 20)) {
    for (const key of Object.keys(row)) keys.add(key);
  }
  return Array.from(keys, (key) => ({ key, label: key }));
}

function asRecord(value: unknown): JsonRecord | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as JsonRecord)
    : null;
}

function arrayValue(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function stringValue(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null;
}

function numberValue(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function identifierValue(value: unknown): string | number | null {
  if (typeof value === 'string' && value.trim()) return value;
  return numberValue(value);
}

function clampPercent(value: number | null): number | null {
  if (value === null) return null;
  return Math.min(100, Math.max(0, value));
}
