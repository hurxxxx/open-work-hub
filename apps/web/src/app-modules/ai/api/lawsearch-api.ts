import {
  apiFetchJson,
  jsonHeaders,
  parseJsonResponse,
} from '@/src/platform/api/client';
import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

const BASE = '/api/v1/lawsearch';

export interface PartSummary {
  id: string;
  name_ko: string;
  name_en?: string;
  icon?: string;
  count: number;
}

export interface PartGroupOut {
  id: string;
  name_ko: string;
  icon?: string;
  parts: PartSummary[];
}

export interface PartsResponse {
  groups: PartGroupOut[];
}

export interface RegionOut {
  id: string;
  name_ko: string;
  name_en?: string;
  flag?: string;
  count: number;
}

export interface RegionsResponse {
  regions: RegionOut[];
}

export interface TypeOut {
  id: string;
  name_ko: string;
  name_en?: string;
  icon?: string;
  desc?: string;
  count: number;
  is_virtual?: boolean;
}

export interface TypesResponse {
  types: TypeOut[];
}

export interface HistoryEntry {
  version: string;
  date: string;
  status: 'current' | 'previous' | 'draft' | 'upcoming' | string;
  summary: string;
}

export interface PartRef {
  id: string;
  name_ko: string;
  icon?: string;
}

export interface RegionRef {
  id: string;
  name_ko: string;
  flag?: string;
}

export interface TypeRef {
  id: string;
  name_ko: string;
  icon?: string;
}

export interface LawItemOut {
  id: string;
  name: string;
  name_en?: string;
  type: string;
  part_ids: string[];
  region_ids: string[];
  description?: string;
  caution?: string;
  effective_date?: string;
  revision_date?: string;
  source_url?: string;
  note?: string;
  history?: HistoryEntry[];
  parts?: PartRef[];
  regions?: RegionRef[];
  type_info?: TypeRef | null;
  created_at?: string;
  updated_at?: string;
}

export interface LawItemRaw {
  id: string;
  name: string;
  name_en?: string;
  type: string;
  part_ids: string[];
  region_ids: string[];
  description?: string;
  caution?: string;
  effective_date?: string;
  revision_date?: string;
  source_url?: string;
  note?: string;
  history?: HistoryEntry[];
  created_at?: string;
  updated_at?: string;
}

export interface LawItemWriteIn {
  name: string;
  name_en?: string;
  type: string;
  part_ids: string[];
  region_ids: string[];
  description?: string;
  caution?: string;
  effective_date?: string;
  revision_date?: string;
  source_url?: string;
  note?: string;
  history?: HistoryEntry[];
}

export interface ByPartResponse {
  part: PartRef;
  items: LawItemOut[];
}

export interface ByRegionResponse {
  region: RegionRef;
  items: LawItemOut[];
}

export interface ByTypeResponse {
  type: TypeRef;
  items: LawItemOut[];
}

export interface SearchResponse {
  items: LawItemOut[];
  q: string;
}

export interface CompetitorOut {
  id: string;
  name_ko: string;
  name_en?: string;
  country?: string;
  flag?: string;
  note?: string;
  count: number;
}

export interface CompetitorsResponse {
  competitors: CompetitorOut[];
}

export interface CompetitorSpecOut {
  id: string;
  competitor_id: string;
  name: string;
  name_en?: string;
  category?: string;
  part_ids: string[];
  description?: string;
  caution?: string;
  effective_date?: string;
  revision_date?: string;
  source_url?: string;
  note?: string;
  parts?: PartRef[];
  created_at?: string;
  updated_at?: string;
}

export interface CompetitorSpecsResponse {
  company: CompetitorOut;
  items: CompetitorSpecOut[];
}

function url(path: string, workspaceSlug: string | null): string {
  return rewriteWorkspaceApiPath(`${BASE}${path}`, workspaceSlug);
}

export function fetchParts(
  token: string | null,
  workspaceSlug: string | null,
): Promise<PartsResponse> {
  return apiFetchJson<PartsResponse>(url('/parts', workspaceSlug), token);
}

export function fetchRegions(
  token: string | null,
  workspaceSlug: string | null,
): Promise<RegionsResponse> {
  return apiFetchJson<RegionsResponse>(url('/regions', workspaceSlug), token);
}

export function fetchTypes(
  token: string | null,
  workspaceSlug: string | null,
): Promise<TypesResponse> {
  return apiFetchJson<TypesResponse>(url('/types', workspaceSlug), token);
}

export function fetchByPart(
  token: string | null,
  workspaceSlug: string | null,
  partId: string,
): Promise<ByPartResponse> {
  return apiFetchJson<ByPartResponse>(
    url(`/by-part/${encodeURIComponent(partId)}`, workspaceSlug),
    token,
  );
}

export function fetchByRegion(
  token: string | null,
  workspaceSlug: string | null,
  regionId: string,
): Promise<ByRegionResponse> {
  return apiFetchJson<ByRegionResponse>(
    url(`/by-region/${encodeURIComponent(regionId)}`, workspaceSlug),
    token,
  );
}

export function fetchByType(
  token: string | null,
  workspaceSlug: string | null,
  typeId: string,
): Promise<ByTypeResponse> {
  return apiFetchJson<ByTypeResponse>(
    url(`/by-type/${encodeURIComponent(typeId)}`, workspaceSlug),
    token,
  );
}

export function fetchSearch(
  token: string | null,
  workspaceSlug: string | null,
  q: string,
): Promise<SearchResponse> {
  return apiFetchJson<SearchResponse>(
    url(`/search?q=${encodeURIComponent(q)}`, workspaceSlug),
    token,
  );
}

export function fetchItemRaw(
  token: string | null,
  workspaceSlug: string | null,
  itemId: string,
): Promise<LawItemRaw> {
  return apiFetchJson<LawItemRaw>(
    url(`/item/${encodeURIComponent(itemId)}`, workspaceSlug),
    token,
  );
}

export function createItem(
  token: string | null,
  workspaceSlug: string | null,
  payload: LawItemWriteIn,
): Promise<LawItemRaw> {
  return apiFetchJson<LawItemRaw>(url('/item', workspaceSlug), token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateItem(
  token: string | null,
  workspaceSlug: string | null,
  itemId: string,
  payload: LawItemWriteIn,
): Promise<LawItemRaw> {
  return apiFetchJson<LawItemRaw>(
    url(`/item/${encodeURIComponent(itemId)}`, workspaceSlug),
    token,
    { method: 'PUT', body: JSON.stringify(payload) },
  );
}

export async function deleteItem(
  token: string | null,
  workspaceSlug: string | null,
  itemId: string,
): Promise<void> {
  const response = await fetch(url(`/item/${encodeURIComponent(itemId)}`, workspaceSlug), {
    method: 'DELETE',
    headers: jsonHeaders(token),
    cache: 'no-store',
  });
  await parseJsonResponse<{ status: string; deleted: string }>(response);
}

export function fetchCompetitors(
  token: string | null,
  workspaceSlug: string | null,
): Promise<CompetitorsResponse> {
  return apiFetchJson<CompetitorsResponse>(
    url('/competitors', workspaceSlug),
    token,
  );
}

export function fetchCompetitorSpecs(
  token: string | null,
  workspaceSlug: string | null,
  companyId: string,
): Promise<CompetitorSpecsResponse> {
  return apiFetchJson<CompetitorSpecsResponse>(
    url(`/competitors/${encodeURIComponent(companyId)}`, workspaceSlug),
    token,
  );
}
