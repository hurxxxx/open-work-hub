import type {
  RetrievalAnswerMode,
  RetrievalHit,
  RetrievalSource,
  RetrievalStrategy,
} from '@/src/platform/retrieval/retrieval-api';

export const RETRIEVAL_STRATEGIES = [
  'hybrid',
  'semantic',
  'keyword',
  'graph_hybrid',
] as const satisfies readonly RetrievalStrategy[];

export const RETRIEVAL_ANSWER_MODES = [
  'search-only',
  'grounded-answer',
] as const satisfies readonly RetrievalAnswerMode[];

export type RetrievalTopK = 5 | 8 | 12 | 20;

export const RETRIEVAL_TOP_K_OPTIONS = [5, 8, 12, 20] as const;

export type RetrievalSearchUrlState = {
  answerMode: RetrievalAnswerMode;
  query: string;
  selectedSources: string[];
  strategy: RetrievalStrategy;
  topK: RetrievalTopK;
};

export type RetrievalSearchDraft<TValue> = {
  sourceKey: string;
  value: TValue;
};

export function parseRetrievalSearchParams(
  searchParams: URLSearchParams,
): RetrievalSearchUrlState {
  const rawAnswerMode = searchParams.get('answer_mode');
  const rawStrategy = searchParams.get('strategy');
  return {
    answerMode: isRetrievalAnswerMode(rawAnswerMode)
      ? rawAnswerMode
      : 'search-only',
    query: searchParams.get('q')?.trim() || '',
    selectedSources: uniqueSourceIds(searchParams.getAll('source')),
    strategy: isRetrievalStrategy(rawStrategy) ? rawStrategy : 'hybrid',
    topK: parseTopK(searchParams.get('top_k')),
  };
}

export function buildRetrievalSearchParams(input: {
  answerMode: RetrievalAnswerMode;
  query: string;
  selectedSources: readonly string[];
  strategy: RetrievalStrategy;
  topK: RetrievalTopK;
  workspaceSlug: string;
}): URLSearchParams {
  const params = new URLSearchParams();
  const query = input.query.trim();
  params.set('workspace', input.workspaceSlug);
  if (query) {
    params.set('q', query);
  }
  if (input.strategy !== 'hybrid') {
    params.set('strategy', input.strategy);
  }
  if (input.answerMode !== 'search-only') {
    params.set('answer_mode', input.answerMode);
  }
  if (input.topK !== 8) {
    params.set('top_k', String(input.topK));
  }
  for (const source of input.selectedSources) {
    params.append('source', source);
  }
  return params;
}

export function draftValue<TValue>(
  draft: RetrievalSearchDraft<TValue>,
  sourceKey: string,
  fallback: TValue,
): TValue {
  return draft.sourceKey === sourceKey ? draft.value : fallback;
}

export function sourceIdsKey(sourceIds: readonly string[]): string {
  return sourceIds.join('\u0000');
}

export function toggleRetrievalSourceSelection(
  selectedSources: readonly string[],
  source: string,
): string[] {
  return selectedSources.includes(source)
    ? selectedSources.filter((item) => item !== source)
    : [...selectedSources, source].sort();
}

export function isSelectableRetrievalSource(source: RetrievalSource): boolean {
  return source.active && source.available;
}

export function retrievalHitKey(hit: RetrievalHit): string {
  return `${hit.source}:${hit.resource_type}:${hit.resource_id}`;
}

function parseTopK(value: string | null): RetrievalTopK {
  const parsed = Number(value);
  return isRetrievalTopK(parsed) ? parsed : 8;
}

function isRetrievalTopK(value: number): value is RetrievalTopK {
  return RETRIEVAL_TOP_K_OPTIONS.some((option) => option === value);
}

function isRetrievalStrategy(
  value: string | null,
): value is RetrievalStrategy {
  return RETRIEVAL_STRATEGIES.some((strategy) => strategy === value);
}

function isRetrievalAnswerMode(
  value: string | null,
): value is RetrievalAnswerMode {
  return RETRIEVAL_ANSWER_MODES.some((mode) => mode === value);
}

function uniqueSourceIds(values: readonly string[]): string[] {
  const seen = new Set<string>();
  for (const value of values) {
    const normalized = value.trim();
    if (/^[A-Za-z0-9_.:-]{1,64}$/.test(normalized)) {
      seen.add(normalized);
    }
  }
  return [...seen].sort();
}
