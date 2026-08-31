import { useCallback, useEffect, useRef, useState } from 'react';

import {
  getEligibleWorkspaces,
  type EligibleWorkspace,
} from '@/src/platform/workspaces/workspaces-api';

const PAGE_SIZE = 25;
const SEARCH_DEBOUNCE_MS = 250;

function mergeWorkspaces(
  current: readonly EligibleWorkspace[],
  incoming: readonly EligibleWorkspace[],
): EligibleWorkspace[] {
  return Array.from(
    new Map(
      [...current, ...incoming].map((workspace) => [workspace.id, workspace]),
    ).values(),
  );
}

export function useEligibleWorkspaceSearch({
  appId,
  enabled = true,
  resetKey = '',
  token,
}: {
  appId: string;
  enabled?: boolean;
  resetKey?: string;
  token: string | null;
}) {
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [items, setItems] = useState<EligibleWorkspace[]>([]);
  const [total, setTotal] = useState(0);
  const [unfilteredTotal, setUnfilteredTotal] = useState<number | null>(null);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadSeq, setReloadSeq] = useState(0);
  const requestVersionRef = useRef(0);

  useEffect(() => {
    requestVersionRef.current += 1;
    setQuery('');
    setDebouncedQuery('');
    setItems([]);
    setTotal(0);
    setUnfilteredTotal(null);
    setPage(0);
    setLoading(false);
    setError(null);
  }, [appId, enabled, resetKey, token]);

  useEffect(() => {
    const timer = window.setTimeout(
      () => setDebouncedQuery(query.trim()),
      SEARCH_DEBOUNCE_MS,
    );
    return () => window.clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    const requestVersion = requestVersionRef.current + 1;
    requestVersionRef.current = requestVersion;
    if (!enabled || !token || !appId) {
      setItems([]);
      setTotal(0);
      setPage(0);
      setLoading(false);
      setError(null);
      return;
    }

    setLoading(true);
    setError(null);
    getEligibleWorkspaces(token, appId, {
      page: 1,
      pageSize: PAGE_SIZE,
      query: debouncedQuery,
    })
      .then((response) => {
        if (requestVersionRef.current !== requestVersion) return;
        setItems(response.items);
        setTotal(response.total);
        setPage(1);
        if (!debouncedQuery) setUnfilteredTotal(response.total);
      })
      .catch((caught: unknown) => {
        if (requestVersionRef.current !== requestVersion) return;
        setItems([]);
        setTotal(0);
        setPage(0);
        setError(caught instanceof Error ? caught.message : String(caught));
      })
      .finally(() => {
        if (requestVersionRef.current === requestVersion) setLoading(false);
      });
  }, [appId, debouncedQuery, enabled, reloadSeq, resetKey, token]);

  const retry = useCallback(() => {
    setReloadSeq((current) => current + 1);
  }, []);

  const loadMore = useCallback(async () => {
    if (!enabled || !token || loading || items.length >= total || page < 1) {
      return;
    }
    const requestVersion = requestVersionRef.current;
    setLoading(true);
    setError(null);
    try {
      const response = await getEligibleWorkspaces(token, appId, {
        page: page + 1,
        pageSize: PAGE_SIZE,
        query: debouncedQuery,
      });
      if (requestVersionRef.current !== requestVersion) return;
      setItems((current) => mergeWorkspaces(current, response.items));
      setTotal(response.total);
      setPage(response.page);
    } catch (caught) {
      if (requestVersionRef.current !== requestVersion) return;
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      if (requestVersionRef.current === requestVersion) setLoading(false);
    }
  }, [
    appId,
    debouncedQuery,
    enabled,
    items.length,
    loading,
    page,
    token,
    total,
  ]);

  return {
    error,
    hasMore: items.length < total,
    items,
    loading,
    loadMore,
    query,
    retry,
    setQuery,
    total,
    unfilteredTotal,
  };
}
