import { apiFetchJsonWithMappedError } from '@/src/platform/api/client';

const BASE_PATH = '/api/v1/news';

export type NewsChannel = 'keyword' | 'front' | 'car';

export interface NewsArticle {
  keyword: string;
  source: string;
  date: string;
  title: string;
  summary: string;
  original_url: string;
}

export interface NewsListResponse {
  status: string;
  channel: string;
  collected_at: string | null;
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  has_next: boolean;
  articles: NewsArticle[];
}

export interface NewsSearchResponse {
  status: string;
  query: string;
  articles: NewsArticle[];
}

export interface NewsArticleImage {
  url: string;
  caption: string;
}

export interface NewsArticleDetail {
  status: string;
  url: string;
  full_text: string;
  summary: string;
  images: NewsArticleImage[];
  tables: string[];
}

export interface NewsFilterSettings {
  keyword_filter: string[];
  car_filter: string[];
  keyword_ui_filters: string[];
}

export interface NewsStatus {
  collecting: boolean;
  collected_at: string | null;
  is_today: boolean;
}

export interface NewsFetchResult {
  status: string;
  message: string;
}

export class NewsApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = 'NewsApiError';
  }
}

function request<T>(path: string, token: string | null, init: RequestInit = {}): Promise<T> {
  return apiFetchJsonWithMappedError<T>(
    path,
    token,
    init,
    (error) => new NewsApiError(error.status, error.message || `News request failed with ${error.status}.`),
  );
}

export function fetchNewsChannel(
  token: string | null,
  channel: NewsChannel,
): Promise<NewsListResponse> {
  return request<NewsListResponse>(`${BASE_PATH}/${channel}`, token);
}

export function searchNews(token: string | null, query: string): Promise<NewsSearchResponse> {
  return request<NewsSearchResponse>(`${BASE_PATH}/search?q=${encodeURIComponent(query)}`, token);
}

export function fetchNewsArticle(token: string | null, url: string): Promise<NewsArticleDetail> {
  return request<NewsArticleDetail>(`${BASE_PATH}/article?url=${encodeURIComponent(url)}`, token);
}

export function fetchNewsFilterSettings(token: string | null): Promise<NewsFilterSettings> {
  return request<NewsFilterSettings>(`${BASE_PATH}/filter-settings`, token);
}

export function saveNewsFilterSettings(
  token: string | null,
  payload: Partial<NewsFilterSettings>,
): Promise<NewsFilterSettings> {
  return request<NewsFilterSettings>(`${BASE_PATH}/filter-settings`, token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function triggerNewsFetch(token: string | null): Promise<NewsFetchResult> {
  return request<NewsFetchResult>(`${BASE_PATH}/fetch`, token, { method: 'POST' });
}

export function fetchNewsStatus(token: string | null): Promise<NewsStatus> {
  return request<NewsStatus>(`${BASE_PATH}/status`, token);
}

// ── 추천 뉴스 ──
export interface NewsRecommendedArticle extends NewsArticle {
  id: string;
  channel: string;
  origin: string;
  reason: string;
  reason_detail: string;
}

export interface NewsRecommendedListResponse {
  status: string;
  articles: NewsRecommendedArticle[];
}

export function fetchRecommendedNews(token: string | null): Promise<NewsRecommendedListResponse> {
  return request<NewsRecommendedListResponse>(`${BASE_PATH}/recommended`, token);
}

export interface NewsScrapArticle extends NewsArticle {
  id: string;
  channel: string;
}

export interface NewsScrapListResponse {
  status: string;
  articles: NewsScrapArticle[];
}

export function fetchNewsScraps(token: string | null): Promise<NewsScrapListResponse> {
  return request<NewsScrapListResponse>(`${BASE_PATH}/scraps`, token);
}

// ── AI 추천 뉴스 (큐레이션) ──
export interface NewsAiProfile {
  ai_profile: string;
  ai_profile_is_default: boolean;
  ai_curate_enabled: boolean;
  ai_curated_at: string | null;
}

export interface NewsCurateResult {
  status: string;
  evaluated: number;
  saved: number;
  by_reason: Record<string, number>;
  error: string | null;
}

export function fetchAiRecommended(token: string | null): Promise<NewsRecommendedListResponse> {
  return request<NewsRecommendedListResponse>(`${BASE_PATH}/ai-recommended`, token);
}

export function triggerCurate(token: string | null): Promise<NewsCurateResult> {
  return request<NewsCurateResult>(`${BASE_PATH}/curate`, token, { method: 'POST' });
}

export function fetchAiProfile(token: string | null): Promise<NewsAiProfile> {
  return request<NewsAiProfile>(`${BASE_PATH}/ai-profile`, token);
}

export function saveAiProfile(
  token: string | null,
  payload: { ai_profile?: string; ai_curate_enabled?: boolean },
): Promise<NewsAiProfile> {
  return request<NewsAiProfile>(`${BASE_PATH}/ai-profile`, token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function recommendNews(
  token: string | null,
  article: NewsArticle,
  channel: string,
): Promise<NewsRecommendedArticle> {
  return request<NewsRecommendedArticle>(`${BASE_PATH}/recommended`, token, {
    method: 'POST',
    body: JSON.stringify({
      channel,
      keyword: article.keyword,
      source: article.source,
      date: article.date,
      title: article.title,
      summary: article.summary,
      original_url: article.original_url,
    }),
  });
}

export function deleteRecommendedNews(token: string | null, id: string): Promise<{ status: string }> {
  return request<{ status: string }>(`${BASE_PATH}/recommended/${encodeURIComponent(id)}`, token, {
    method: 'DELETE',
  });
}

export function scrapNews(
  token: string | null,
  article: NewsArticle,
  channel: string,
): Promise<NewsScrapArticle> {
  return request<NewsScrapArticle>(`${BASE_PATH}/scraps`, token, {
    method: 'POST',
    body: JSON.stringify({
      channel,
      keyword: article.keyword,
      source: article.source,
      date: article.date,
      title: article.title,
      summary: article.summary,
      original_url: article.original_url,
    }),
  });
}

export function deleteNewsScrap(token: string | null, id: string): Promise<{ status: string }> {
  return request<{ status: string }>(`${BASE_PATH}/scraps/${encodeURIComponent(id)}`, token, {
    method: 'DELETE',
  });
}
