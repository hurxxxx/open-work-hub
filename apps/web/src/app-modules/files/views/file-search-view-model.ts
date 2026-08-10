import type {
  FileSearchHit,
  FileSearchSnippet,
  FileSearchStrategy,
} from '../api/files-api';

export const FILE_SEARCH_PAGE_SIZE = 20;
export const FILE_SEARCH_MAX_RANKED_RESULTS = 100;
export const FILE_SEARCH_STRATEGIES = [
  'keyword',
  'semantic',
  'hybrid',
] as const satisfies readonly FileSearchStrategy[];

export interface FileSearchUrlState {
  page: number;
  query: string;
  strategy: FileSearchStrategy;
}

export function parseFileSearchParams(
  searchParams: URLSearchParams,
): FileSearchUrlState {
  const strategy = searchParams.get('strategy');
  return {
    page: parsePage(searchParams.get('page')),
    query: searchParams.get('q')?.trim() || '',
    strategy: isFileSearchStrategy(strategy) ? strategy : 'hybrid',
  };
}

export function buildFileSearchParams(
  input: FileSearchUrlState,
): URLSearchParams {
  const params = new URLSearchParams({ view: 'search' });
  const query = input.query.trim();
  if (query) {
    params.set('q', query);
  }
  if (input.strategy !== 'hybrid') {
    params.set('strategy', input.strategy);
  }
  if (input.page > 1) {
    params.set('page', String(input.page));
  }
  return params;
}

function parsePage(value: string | null): number {
  const page = Number(value);
  const maxPage = FILE_SEARCH_MAX_RANKED_RESULTS / FILE_SEARCH_PAGE_SIZE;
  return Number.isInteger(page) && page >= 1 && page <= maxPage ? page : 1;
}

function isFileSearchStrategy(
  value: string | null,
): value is FileSearchStrategy {
  return FILE_SEARCH_STRATEGIES.some((strategy) => strategy === value);
}

export interface FileSearchSnippetSegment {
  highlighted: boolean;
  text: string;
}

export function fileSearchSnippetSegments(
  snippet: FileSearchSnippet,
): FileSearchSnippetSegment[] {
  const ranges = snippet.highlights
    .map(({ start, end }) => ({
      start: Math.max(0, Math.min(snippet.text.length, start)),
      end: Math.max(0, Math.min(snippet.text.length, end)),
    }))
    .filter(({ start, end }) => end > start)
    .sort((left, right) => left.start - right.start || left.end - right.end);
  const segments: FileSearchSnippetSegment[] = [];
  let cursor = 0;
  for (const range of ranges) {
    const start = Math.max(cursor, range.start);
    if (start > cursor) {
      segments.push({
        highlighted: false,
        text: snippet.text.slice(cursor, start),
      });
    }
    if (range.end > start) {
      segments.push({
        highlighted: true,
        text: snippet.text.slice(start, range.end),
      });
      cursor = range.end;
    }
  }
  if (cursor < snippet.text.length) {
    segments.push({ highlighted: false, text: snippet.text.slice(cursor) });
  }
  return segments;
}

export function orderFileSearchHits(
  hits: readonly FileSearchHit[],
): FileSearchHit[] {
  return [...hits].sort(
    (left, right) =>
      left.rank - right.rank ||
      right.score - left.score ||
      left.file_id.localeCompare(right.file_id),
  );
}
