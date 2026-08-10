import {
  apiFetchJsonWithMappedError,
  jsonHeaders,
} from '@/src/platform/api/client';
import { i18n } from '@/src/platform/i18n';
import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

export interface PptTemplatePreviewImage {
  id: string;
  url: string;
  sort_order: number;
  created_at: string;
}

export interface PptFamily {
  id: string;
  name: string;
  aspect: string;
  /** 본문 슬라이드 수를 사용자가 정할 수 있는 양식(자유/Open ALM/corporate-v2)인지. */
  multi_body?: boolean;
  preview_images?: PptTemplatePreviewImage[];
}

export interface PptFailedFile {
  name: string;
  reason: string;
}

export interface PptGenerateResponse {
  job_id: string;
  status: string;
  family: string;
  family_name: string;
  aspect: string;
  n_slides: number;
  attached_files: string[];
  failed_files: PptFailedFile[];
}

/** slides_spec.slides[i] — 레이아웃 + data dict (HTML 렌더 입력). */
export interface PptSlide {
  layout: string;
  data: Record<string, unknown>;
}

export interface PptSlidesSpec {
  family: string;
  slides?: PptSlide[];
  /** 'html' 이면 Claude 가 생성한 자체 완결형 HTML 덱을 그대로 렌더(자유 양식). */
  format?: string;
  html?: string;
  slide_w?: number;
  slide_h?: number;
  /**
   * 교육 보고서의 '똑딱이'(OLE 임베드) 안에 들어갈 결과보고서 덱의 미리보기 HTML.
   * 데스크톱 PowerPoint 에서는 더블클릭 시 열리지만, 미리보기에선 이 HTML 로 펼쳐 보여준다.
   */
  embed_preview?: { html: string; slide_w?: number; title?: string };
}

export interface PptChatResult {
  status: 'idle' | 'processing' | 'done' | 'error';
  answer?: string;
  intent?: 'edit' | 'chat' | null;
  refreshed_slide_index?: number | null;
  rev?: number;
  conversation_id?: string | null;
}

export interface PptJobStatus {
  job_id: string;
  status: 'pending' | 'running' | 'completed' | 'error' | 'cancelled';
  title?: string | null;
  message: string;
  family: string;
  aspect: string;
  n_slides: number;
  error?: string | null;
  rev: number;
  chat_result?: PptChatResult | null;
  /** 프론트 HTML 렌더용 구조화 데이터 (status==='completed' 부터 채워짐). */
  slides_spec?: PptSlidesSpec | null;
  /** 'PPT로 전환'(finalize)으로 .pptx 가 빌드돼 다운로드 가능한지. */
  pptx_ready?: boolean;
  /** 외부 웹 검색(Claude)으로 기초 정보 수집 시 참고한 출처. */
  research_sources?: PptResearchSource[];
  /**
   * 진행 중 작업의 마지막 활동으로부터 경과 초(서버 계산). 워커 하트비트가 ~12초마다
   * 갱신하므로, 이 값이 크게 벌어지면 워커가 멈춘 것으로 의심할 수 있다.
   */
  heartbeat_age_seconds?: number | null;
}

export interface PptResearchSource {
  url: string;
  title?: string;
  /** 이 출처를 찾은 검색어. */
  query?: string;
  /** 이 출처에서 인용·발췌한 핵심 문구(어떤 정보를 가져왔는지). */
  snippet?: string;
  /** 이 출처가 반영된 것으로 추정되는 슬라이드 페이지(1-based, 표지 포함). */
  page?: number;
  /** 해당 페이지에서 추정되는 섹션/제목. */
  section?: string;
  /** 반영된 블록 종류(표/차트/본문/타임라인/결론/개요). */
  block_kind?: string;
  /** 반영된 것으로 추정되는 블록의 대표 발췌. */
  used_in?: string;
}

export interface PptJobListItem {
  job_id: string;
  status: 'pending' | 'running' | 'completed' | 'error' | 'cancelled';
  title?: string | null;
  family: string;
  aspect: string;
  n_slides: number;
  error?: string | null;
  rev: number;
  pptx_ready?: boolean;
  created_at: string;
  updated_at: string;
}

export interface PptJobListResponse {
  items: PptJobListItem[];
}

export class PptGeneratorApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function resolveErrorMessage(payload: unknown, fallback: string): string {
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === 'string' && detail.trim()) {
      return detail;
    }
    if (
      detail &&
      typeof detail === 'object' &&
      'message' in detail &&
      typeof (detail as { message?: unknown }).message === 'string'
    ) {
      return (detail as { message: string }).message;
    }
  }
  return fallback;
}

async function pptRequest<T>(
  path: string,
  token: string,
  workspaceSlug: string | null,
  init: RequestInit = {},
): Promise<T> {
  try {
    return await apiFetchJsonWithMappedError<T>(
      rewriteWorkspaceApiPath(path, workspaceSlug),
      token,
      init,
      (error) =>
        new PptGeneratorApiError(
          error.status,
          resolveErrorMessage(
            error.payload,
            i18n.t('apps:ai.pptGenerator.errors.requestFailed', {
              status: error.status,
            }),
          ),
        ),
    );
  } catch (error) {
    if (error instanceof PptGeneratorApiError) {
      throw error;
    }
    throw new PptGeneratorApiError(
      0,
      i18n.t('apps:ai.pptGenerator.errors.connect'),
    );
  }
}

export function listPptFamilies(args: {
  token: string;
  workspaceSlug: string | null;
}): Promise<PptFamily[]> {
  return pptRequest<PptFamily[]>(
    '/api/v1/ppt-generator/families',
    args.token,
    args.workspaceSlug,
  );
}

export function generatePpt(args: {
  token: string;
  workspaceSlug: string | null;
  content: string;
  family: string;
  purpose?: string;
  audience?: string;
  referenceUrl?: string;
  extraNotes?: string;
  slideRange?: string;
  language?: string;
  tone?: string;
  instructions?: string;
  includeTitleSlide?: boolean;
  includeToc?: boolean;
  files?: File[];
}): Promise<PptGenerateResponse> {
  const form = new FormData();
  form.append('content', args.content ?? '');
  form.append('family', args.family);
  if (args.purpose) form.append('purpose', args.purpose);
  if (args.audience) form.append('audience', args.audience);
  if (args.referenceUrl) form.append('reference_url', args.referenceUrl);
  if (args.extraNotes) form.append('extra_notes', args.extraNotes);
  if (args.slideRange) form.append('slide_range', args.slideRange);
  form.append('language', args.language ?? 'Korean');
  form.append('tone', args.tone ?? 'default');
  if (args.instructions) form.append('instructions', args.instructions);
  form.append('include_title_slide', String(args.includeTitleSlide ?? true));
  form.append('include_table_of_contents', String(args.includeToc ?? false));
  for (const file of args.files ?? []) {
    form.append('files', file);
  }
  return pptRequest<PptGenerateResponse>(
    '/api/v1/ppt-generator/generate',
    args.token,
    args.workspaceSlug,
    { method: 'POST', body: form },
  );
}

export function getPptJobStatus(args: {
  token: string;
  workspaceSlug: string | null;
  jobId: string;
}): Promise<PptJobStatus> {
  return pptRequest<PptJobStatus>(
    `/api/v1/ppt-generator/jobs/${encodeURIComponent(args.jobId)}`,
    args.token,
    args.workspaceSlug,
  );
}

export function listPptJobs(args: {
  token: string;
  workspaceSlug: string | null;
  limit?: number;
}): Promise<PptJobListResponse> {
  const search = new URLSearchParams();
  if (args.limit) search.set('limit', String(args.limit));
  const query = search.toString();
  const suffix = query ? `?${query}` : '';
  return pptRequest<PptJobListResponse>(
    `/api/v1/ppt-generator/jobs${suffix}`,
    args.token,
    args.workspaceSlug,
  );
}

export async function deletePptJob(args: {
  token: string;
  workspaceSlug: string | null;
  jobId: string;
}): Promise<void> {
  let response: Response;
  try {
    response = await fetch(
      rewriteWorkspaceApiPath(
        `/api/v1/ppt-generator/jobs/${encodeURIComponent(args.jobId)}`,
        args.workspaceSlug,
      ),
      { method: 'DELETE', headers: jsonHeaders(args.token), cache: 'no-store' },
    );
  } catch {
    throw new PptGeneratorApiError(
      0,
      i18n.t('apps:ai.pptGenerator.errors.connect'),
    );
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new PptGeneratorApiError(
      response.status,
      resolveErrorMessage(
        payload,
        i18n.t('apps:ai.pptGenerator.errors.requestFailed', {
          status: response.status,
        }),
      ),
    );
  }
}

export function sendPptChatEdit(args: {
  token: string;
  workspaceSlug: string | null;
  jobId: string;
  message: string;
  history: { role: string; content: string }[];
  conversationId?: string | null;
}): Promise<{
  ok: boolean;
  status: string;
  message: string;
  conversation_id?: string | null;
}> {
  return pptRequest(
    `/api/v1/ppt-generator/jobs/${encodeURIComponent(args.jobId)}/chat-edit`,
    args.token,
    args.workspaceSlug,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: args.message,
        history: args.history,
        conversation_id: args.conversationId || undefined,
      }),
    },
  );
}

/** HTML 미리보기에서 다듬은 slides_spec 을 .pptx 로 빌드(전환)하도록 요청. */
export function finalizePpt(args: {
  token: string;
  workspaceSlug: string | null;
  jobId: string;
}): Promise<{ ok: boolean; status: string }> {
  return pptRequest(
    `/api/v1/ppt-generator/jobs/${encodeURIComponent(args.jobId)}/finalize`,
    args.token,
    args.workspaceSlug,
    { method: 'POST' },
  );
}

/** 진행 중인 생성 작업을 취소. 아직 시작 안 한 작업은 실행을 막고, 실행 중이면 결과를 폐기한다. */
export function cancelPpt(args: {
  token: string;
  workspaceSlug: string | null;
  jobId: string;
}): Promise<{ ok: boolean; status: string }> {
  return pptRequest(
    `/api/v1/ppt-generator/jobs/${encodeURIComponent(args.jobId)}/cancel`,
    args.token,
    args.workspaceSlug,
    { method: 'POST' },
  );
}

/** .pptx 다운로드 (인증 헤더 → blob → 앵커 클릭). */
export async function downloadPptx(args: {
  token: string;
  workspaceSlug: string | null;
  jobId: string;
  filename: string;
}): Promise<void> {
  let response: Response;
  try {
    response = await fetch(
      rewriteWorkspaceApiPath(
        `/api/v1/ppt-generator/jobs/${encodeURIComponent(args.jobId)}/download`,
        args.workspaceSlug,
      ),
      { headers: jsonHeaders(args.token), cache: 'no-store' },
    );
  } catch {
    throw new PptGeneratorApiError(
      0,
      i18n.t('apps:ai.pptGenerator.errors.connect'),
    );
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new PptGeneratorApiError(
      response.status,
      resolveErrorMessage(
        payload,
        i18n.t('apps:ai.pptGenerator.errors.downloadFailed'),
      ),
    );
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `${args.filename}.pptx`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
