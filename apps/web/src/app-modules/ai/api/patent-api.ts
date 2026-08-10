import {
  ApiRequestError,
  apiFetchJson,
} from '@/src/platform/api/client';
import { i18n } from '@/src/platform/i18n';
import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

// ── Shared types ────────────────────────────────────────────────────────────
export interface PatentChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface PatentItem {
  app_no: string;
  reg_no: string;
  title: string;
  applicant: string;
  date: string;
  status: string;
  ipc: string;
  abstract: string;
  ai_tags: string[];
  relevance: number;
}

export interface TopApplicant {
  name: string;
  count: number;
}

export interface AiSearchResult {
  results: PatentItem[];
  total: number;
  page: number;
  search_query: string;
  main_keywords: string[];
  tech_summary: string;
  top_applicants: TopApplicant[];
  applicant_sample_size: number;
  applicant_filter: string;
  ai_summary: string;
  core_techs: string[];
  suggested_queries: string[];
}

export interface PatentDetail {
  app_no: string;
  reg_no: string;
  open_no: string;
  pub_no: string;
  title: string;
  title_eng: string;
  applicant: string;
  date: string;
  status: string;
  ipc: string;
  abstract: string;
  claims: string[];
  description: string;
  reg_date: string;
  open_date: string;
  pub_date: string;
  final_disposal: string;
  warning: string;
  foreign?: boolean;
  google_patents_url?: string;
  claims_source?: string;
}

export interface TranslateResult {
  translations: string[];
}

export interface KeywordGroup {
  element: string;
  description: string;
  keywords_kr: string[];
  keywords_en: string[];
  synonyms_kr: string[];
  synonyms_en: string[];
}

export interface SearchQueryResult {
  tech_summary: string;
  ipc_codes: string[];
  keyword_groups: KeywordGroup[];
  search_formula: string;
}

export interface ReportResult {
  result: string;
  report_type: string;
  label: string;
}

export type ReportType = 'invention-disclosure' | 'prior-art';
export type FilingMode = 'review' | 'improve' | 'prior';

export interface ClaimsExplainResult {
  summary: string;
  key_features: string[];
  technical_significance: string;
  per_claim: Array<Record<string, unknown>>;
}

export interface RightsScopeResult {
  overall_analysis: string;
  scope_breadth: string;
  key_elements: string[];
  per_claim: Array<Record<string, unknown>>;
  caution: string;
}

export interface InfringeCheckResult {
  overall_verdict: string;
  overall_summary: string;
  per_claim: Array<Record<string, unknown>>;
  caution: string;
}

export interface DescriptionMappingResult {
  mappings: Array<Record<string, unknown>>;
}

export interface PdfUrlResult {
  pdf_url: string;
  kipris_url: string;
  type: string;
}

export interface ExtractResult {
  filename: string;
  text: string;
  char_count: number;
  truncated: boolean;
}

export class PatentApiError extends Error {
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
  }
  return fallback;
}

async function patentPost<T>(
  path: string,
  token: string,
  workspaceSlug: string | null,
  body: unknown,
): Promise<T> {
  try {
    return await apiFetchJson<T>(
      rewriteWorkspaceApiPath(path, workspaceSlug),
      token,
      { method: 'POST', body: JSON.stringify(body ?? {}) },
    );
  } catch (error) {
    if (error instanceof ApiRequestError) {
      throw new PatentApiError(
        error.status,
        resolveErrorMessage(
          error.payload,
          i18n.t('apps:ai.patentCompose.errors.requestFailed', { status: error.status }),
        ),
      );
    }
    throw new PatentApiError(0, i18n.t('apps:ai.patentCompose.errors.connect'));
  }
}

interface Auth {
  token: string;
  workspaceSlug: string | null;
}

export function patentAiSearch(
  args: Auth & { query: string; page?: number; applicantFilter?: string },
): Promise<AiSearchResult> {
  return patentPost<AiSearchResult>('/api/v1/patent/ai-search', args.token, args.workspaceSlug, {
    query: args.query,
    page: args.page ?? 1,
    applicant_filter: args.applicantFilter ?? '',
  });
}

export function patentFetch(args: Auth & { patentNumber: string }): Promise<PatentDetail> {
  return patentPost<PatentDetail>('/api/v1/patent/fetch', args.token, args.workspaceSlug, {
    patent_number: args.patentNumber,
  });
}

export function patentTranslate(
  args: Auth & { texts: string[] },
): Promise<TranslateResult> {
  return patentPost<TranslateResult>('/api/v1/patent/translate', args.token, args.workspaceSlug, {
    texts: args.texts,
  });
}

export function patentSearchQuery(
  args: Auth & { technologyDescription: string },
): Promise<SearchQueryResult> {
  return patentPost<SearchQueryResult>(
    '/api/v1/patent/search-query',
    args.token,
    args.workspaceSlug,
    { technology_description: args.technologyDescription },
  );
}

export function patentReport(
  args: Auth & { content: string; reportType: ReportType; patentContext?: string },
): Promise<ReportResult> {
  return patentPost<ReportResult>('/api/v1/patent/report', args.token, args.workspaceSlug, {
    content: args.content,
    report_type: args.reportType,
    patent_context: args.patentContext ?? '',
  });
}

export function patentFilingAssist(
  args: Auth & { invention: string; mode: FilingMode },
): Promise<{ result: string }> {
  return patentPost<{ result: string }>(
    '/api/v1/patent/filing-assist',
    args.token,
    args.workspaceSlug,
    { invention: args.invention, mode: args.mode },
  );
}

export function patentAgentChat(
  args: Auth & {
    message: string;
    context?: string;
    history?: PatentChatMessage[];
    conversationId?: string | null;
  },
): Promise<{ reply: string; conversation_id?: string | null }> {
  return patentPost<{ reply: string; conversation_id?: string | null }>(
    '/api/v1/patent/agent-chat',
    args.token,
    args.workspaceSlug,
    {
      message: args.message,
      context: args.context ?? '',
      history: args.history ?? [],
      conversation_id: args.conversationId || undefined,
    },
  );
}

export function patentAskBrainy(
  args: Auth & {
    patentContext?: string;
    messages?: PatentChatMessage[];
    question: string;
    conversationId?: string | null;
  },
): Promise<{ answer: string; conversation_id?: string | null }> {
  return patentPost<{ answer: string; conversation_id?: string | null }>(
    '/api/v1/patent/ask-brainy',
    args.token,
    args.workspaceSlug,
    {
      patent_context: args.patentContext ?? '',
      messages: args.messages ?? [],
      question: args.question,
      conversation_id: args.conversationId || undefined,
    },
  );
}

export function patentClaimsExplain(
  args: Auth & { claims: string[]; abstract?: string; title?: string },
): Promise<ClaimsExplainResult> {
  return patentPost<ClaimsExplainResult>(
    '/api/v1/patent/claims-explain',
    args.token,
    args.workspaceSlug,
    { claims: args.claims, abstract: args.abstract ?? '', title: args.title ?? '' },
  );
}

export function patentRightsScope(
  args: Auth & { claims: string[]; title?: string },
): Promise<RightsScopeResult> {
  return patentPost<RightsScopeResult>(
    '/api/v1/patent/rights-scope',
    args.token,
    args.workspaceSlug,
    { claims: args.claims, title: args.title ?? '' },
  );
}

export function patentDescriptionMapping(
  args: Auth & { claims: string[]; description?: string; abstract?: string },
): Promise<DescriptionMappingResult> {
  return patentPost<DescriptionMappingResult>(
    '/api/v1/patent/description-mapping',
    args.token,
    args.workspaceSlug,
    { claims: args.claims, description: args.description ?? '', abstract: args.abstract ?? '' },
  );
}

export function patentInfringeCheck(
  args: Auth & { claims: string[]; title?: string; techDescription: string },
): Promise<InfringeCheckResult> {
  return patentPost<InfringeCheckResult>(
    '/api/v1/patent/infringe-check',
    args.token,
    args.workspaceSlug,
    { claims: args.claims, title: args.title ?? '', tech_description: args.techDescription },
  );
}

export function patentPdfUrl(
  args: Auth & { appNo: string; regNo?: string },
): Promise<PdfUrlResult> {
  return patentPost<PdfUrlResult>('/api/v1/patent/pdf-url', args.token, args.workspaceSlug, {
    app_no: args.appNo,
    reg_no: args.regNo ?? '',
  });
}

export async function patentExtract(args: Auth & { file: File }): Promise<ExtractResult> {
  const form = new FormData();
  form.append('file', args.file);
  try {
    return await apiFetchJson<ExtractResult>(
      rewriteWorkspaceApiPath('/api/v1/patent/extract', args.workspaceSlug),
      args.token,
      { method: 'POST', body: form },
    );
  } catch (error) {
    if (error instanceof ApiRequestError) {
      throw new PatentApiError(
        error.status,
        resolveErrorMessage(
          error.payload,
          i18n.t('apps:ai.patentCompose.errors.requestFailed', { status: error.status }),
        ),
      );
    }
    throw new PatentApiError(0, i18n.t('apps:ai.patentCompose.errors.connect'));
  }
}
