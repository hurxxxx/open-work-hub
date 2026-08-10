import { apiFetchJson } from '@/src/platform/api/client';

export interface PlmRawColumn {
  name: string;
  type: string;
}

export interface PlmRawTable {
  owner: string;
  name: string;
  object_type: string;
}

export interface PlmRawTableListResponse {
  items: PlmRawTable[];
}

export interface PlmRawRowsResponse {
  columns: PlmRawColumn[];
  rows: Array<Array<string | null>>;
  has_more: boolean;
  limit: number;
  offset: number;
  sql_preview: string;
}

const PAGE_SIZE = 100;

function workspacePlmPath(workspaceSlug: string, path: string): string {
  return `/api/v1/workspaces/${encodeURIComponent(workspaceSlug)}/plm/raw${path}`;
}

export function getPlmRawPageSize(): number {
  return PAGE_SIZE;
}

export async function fetchPlmRawTables(
  token: string,
  workspaceSlug: string,
): Promise<PlmRawTableListResponse> {
  return apiFetchJson<PlmRawTableListResponse>(
    workspacePlmPath(workspaceSlug, '/tables'),
    token,
  );
}

export async function fetchPlmRawTableRows({
  limit = PAGE_SIZE,
  name,
  offset,
  owner,
  token,
  workspaceSlug,
}: {
  limit?: number;
  name: string;
  offset: number;
  owner: string;
  token: string;
  workspaceSlug: string;
}): Promise<PlmRawRowsResponse> {
  return apiFetchJson<PlmRawRowsResponse>(
    workspacePlmPath(workspaceSlug, '/table/rows'),
    token,
    {
      method: 'POST',
      body: JSON.stringify({ owner, name, limit, offset }),
    },
  );
}

export async function runPlmRawSqlQuery({
  limit = PAGE_SIZE,
  offset,
  sql,
  token,
  workspaceSlug,
}: {
  limit?: number;
  offset: number;
  sql: string;
  token: string;
  workspaceSlug: string;
}): Promise<PlmRawRowsResponse> {
  return apiFetchJson<PlmRawRowsResponse>(
    workspacePlmPath(workspaceSlug, '/query'),
    token,
    {
      method: 'POST',
      body: JSON.stringify({ sql, limit, offset }),
    },
  );
}
