import type { components } from '@ai-do/contracts/openapi';

import { apiFetchJson, jsonBodyHeaders, jsonHeaders } from '@/src/platform/api/client';
import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

type MealInvoiceSchemas = components['schemas'];

// API 스키마의 한국어 필드명을 그대로 사용해 서버 왕복(추출→편집→내보내기)에서 매핑 없이 보존한다.
export type InvoiceRow = MealInvoiceSchemas['MealInvoiceRow'];
export type InvoiceDocument = MealInvoiceSchemas['MealInvoiceDocument'];
export type InvoiceExportDocument = MealInvoiceSchemas['MealInvoiceExportDocument'];
export type ExtractResponse = MealInvoiceSchemas['MealInvoiceExtractResponse'];
export type CorrectionItem = MealInvoiceSchemas['MealInvoiceCorrectionItem'];
export type CorrectionRecord = MealInvoiceSchemas['MealInvoiceCorrectionRecord'];
export type CorrectionListResponse = MealInvoiceSchemas['MealInvoiceCorrectionListResponse'];
export type CorrectionSaveResponse = MealInvoiceSchemas['MealInvoiceCorrectionSaveResponse'];
export type CatalogInfo = MealInvoiceSchemas['MealInvoiceCatalogInfoResponse'];

const API_PREFIX = '/api/v1/meal-invoice-ocr';

function basePath(workspaceSlug: string, path: string): string {
  return rewriteWorkspaceApiPath(`${API_PREFIX}${path}`, workspaceSlug);
}

export async function extractInvoices(args: {
  token: string;
  workspaceSlug: string;
  files: File[];
}): Promise<ExtractResponse> {
  const body = new FormData();
  for (const file of args.files) body.append('files', file);
  return apiFetchJson<ExtractResponse>(basePath(args.workspaceSlug, '/extract'), args.token, {
    method: 'POST',
    body,
  });
}

export async function saveCorrections(args: {
  token: string;
  workspaceSlug: string;
  items: CorrectionItem[];
  // 문서키 → 페이지 이미지(data URL). 확인 행마다 반복 전송하지 않고 문서당 한 번만 보낸다.
  문서이미지?: Record<string, string>;
}): Promise<CorrectionSaveResponse> {
  return apiFetchJson<CorrectionSaveResponse>(basePath(args.workspaceSlug, '/corrections'), args.token, {
    method: 'POST',
    body: JSON.stringify({ items: args.items, 문서이미지: args.문서이미지 ?? {} }),
  });
}

export async function fetchCorrectionImage(args: {
  token: string;
  workspaceSlug: string;
  id: string;
}): Promise<Blob> {
  const response = await fetch(
    basePath(args.workspaceSlug, `/corrections/${encodeURIComponent(args.id)}/image`),
    { cache: 'no-store', headers: { ...jsonHeaders(args.token), Accept: '*/*' } },
  );
  if (!response.ok) {
    throw new Error(String(response.status));
  }
  return response.blob();
}

export async function fetchCorrections(args: {
  token: string;
  workspaceSlug: string;
}): Promise<CorrectionListResponse> {
  return apiFetchJson<CorrectionListResponse>(basePath(args.workspaceSlug, '/corrections'), args.token);
}

export async function deleteCorrection(args: {
  token: string;
  workspaceSlug: string;
  id: string;
}): Promise<CorrectionSaveResponse> {
  return apiFetchJson<CorrectionSaveResponse>(
    basePath(args.workspaceSlug, `/corrections/${encodeURIComponent(args.id)}`),
    args.token,
    { method: 'DELETE' },
  );
}

export async function clearCorrections(args: {
  token: string;
  workspaceSlug: string;
}): Promise<CorrectionSaveResponse> {
  return apiFetchJson<CorrectionSaveResponse>(basePath(args.workspaceSlug, '/corrections'), args.token, {
    method: 'DELETE',
  });
}

export async function uploadCatalog(args: {
  token: string;
  workspaceSlug: string;
  file: File;
}): Promise<CatalogInfo> {
  const body = new FormData();
  body.append('file', args.file);
  return apiFetchJson<CatalogInfo>(basePath(args.workspaceSlug, '/catalog'), args.token, {
    method: 'POST',
    body,
  });
}

export async function fetchCatalogInfo(args: {
  token: string;
  workspaceSlug: string;
}): Promise<CatalogInfo> {
  return apiFetchJson<CatalogInfo>(basePath(args.workspaceSlug, '/catalog'), args.token);
}

export async function clearCatalog(args: {
  token: string;
  workspaceSlug: string;
}): Promise<CatalogInfo> {
  return apiFetchJson<CatalogInfo>(basePath(args.workspaceSlug, '/catalog'), args.token, {
    method: 'DELETE',
  });
}

export async function exportInvoicesXlsx(args: {
  token: string;
  workspaceSlug: string;
  documents: InvoiceExportDocument[];
}): Promise<Blob> {
  const response = await fetch(basePath(args.workspaceSlug, '/export.xlsx'), {
    method: 'POST',
    cache: 'no-store',
    // Content-Type: application/json 이 있어야 FastAPI 가 본문을 파싱한다. Accept 만 */* 로 덮어쓴다.
    headers: { ...jsonBodyHeaders(args.token), Accept: '*/*' },
    body: JSON.stringify({ documents: args.documents }),
  });
  if (!response.ok) {
    throw new Error(String(response.status));
  }
  return response.blob();
}
