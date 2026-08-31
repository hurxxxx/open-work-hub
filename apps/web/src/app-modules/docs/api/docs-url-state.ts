export const DOC_PAGE_QUERY_PARAM = 'page';
export const DOCS_CREATE_QUERY_PARAM = 'create';
export const DOCS_SPACE_QUERY_PARAM = 'space_id';

type DocsPageTreeItem = {
  id: string;
  parent_id: string | null;
};

export function getDocPageIdFromSearchParams(
  searchParams: URLSearchParams,
): string | null {
  const pageId = searchParams.get(DOC_PAGE_QUERY_PARAM)?.trim();
  return pageId || null;
}

export function getDocsFilterQueryString(
  searchParams: URLSearchParams,
): string {
  const next = new URLSearchParams(searchParams);
  next.delete(DOC_PAGE_QUERY_PARAM);
  return next.toString();
}

export function appendDocPageQuery(
  path: string,
  pageId: string | null | undefined,
): string {
  if (!pageId) {
    return path;
  }
  const hashIndex = path.indexOf('#');
  const beforeHash = hashIndex >= 0 ? path.slice(0, hashIndex) : path;
  const hash = hashIndex >= 0 ? path.slice(hashIndex) : '';
  const separator = beforeHash.includes('?') ? '&' : '?';
  return `${beforeHash}${separator}${DOC_PAGE_QUERY_PARAM}=${encodeURIComponent(pageId)}${hash}`;
}

export function withDocPageSearchParam(
  searchParams: URLSearchParams,
  pageId: string | null,
): URLSearchParams {
  const next = new URLSearchParams(searchParams);
  if (pageId) {
    next.set(DOC_PAGE_QUERY_PARAM, pageId);
  } else {
    next.delete(DOC_PAGE_QUERY_PARAM);
  }
  return next;
}

export function consumeDocsCreateSearchParam(searchParams: URLSearchParams): {
  shouldOpen: boolean;
  searchParams: URLSearchParams | null;
} {
  if (searchParams.get(DOCS_CREATE_QUERY_PARAM) !== '1') {
    return { shouldOpen: false, searchParams: null };
  }
  const next = new URLSearchParams(searchParams);
  next.delete(DOCS_CREATE_QUERY_PARAM);
  return { shouldOpen: true, searchParams: next };
}

export function withDocsSpaceFilterSearchParam(
  searchParams: URLSearchParams,
  spaceId: string,
): URLSearchParams {
  const next = new URLSearchParams(searchParams);
  next.delete(DOC_PAGE_QUERY_PARAM);
  if (spaceId) {
    next.set(DOCS_SPACE_QUERY_PARAM, spaceId);
  } else {
    next.delete(DOCS_SPACE_QUERY_PARAM);
  }
  return next;
}

export function resetDocsFilterSearchParams(
  searchParams: URLSearchParams,
): URLSearchParams {
  const next = new URLSearchParams(searchParams);
  next.delete(DOC_PAGE_QUERY_PARAM);
  next.delete('source_app');
  next.delete('source_kind');
  next.delete(DOCS_SPACE_QUERY_PARAM);
  return next;
}

export function resolveInitialDocPageId(
  pages: readonly DocsPageTreeItem[],
  requestedPageId: string | null | undefined,
): string | null {
  if (requestedPageId && pages.some((page) => page.id === requestedPageId)) {
    return requestedPageId;
  }
  return pages[0]?.id ?? null;
}

export function getExpandedDocPageNodeIds(
  pages: readonly DocsPageTreeItem[],
  selectedPageId: string | null | undefined,
): Set<string> {
  const expanded = new Set<string>();
  const pagesById = new Map(pages.map((page) => [page.id, page]));

  for (const page of pages) {
    if (page.parent_id === null) {
      expanded.add(page.id);
    }
  }

  let current = selectedPageId ? pagesById.get(selectedPageId) : null;
  const visited = new Set<string>();
  while (current?.parent_id && !visited.has(current.id)) {
    visited.add(current.id);
    expanded.add(current.parent_id);
    current = pagesById.get(current.parent_id) ?? null;
  }

  return expanded;
}
