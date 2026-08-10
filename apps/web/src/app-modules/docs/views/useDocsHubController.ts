import { useCallback, useEffect, useRef, useState } from 'react';

import {
  listDocsHub,
  type DocsHubItem,
  type DocsHubResponse,
} from '../api/docs-api';
import type { DocsViewCategory } from './docs-view-model';

export interface DocsHubControllerClient {
  listDocsHub(
    token: string,
    params: {
      view?: string;
      q?: string;
      sort_by?: string;
      sort_dir?: string;
      source_app?: string;
      source_kind?: string;
      space_id?: string;
    },
    workspaceSlug?: string | null,
  ): Promise<DocsHubResponse>;
}

export interface DocsHubControllerOptions {
  token?: string | null;
  workspaceSlug?: string | null;
  listEnabled: boolean;
  activeCategory: DocsViewCategory;
  activeSourceApp?: string;
  activeSourceKind?: string;
  activeSpaceId?: string;
  client?: DocsHubControllerClient;
  searchDebounceMs?: number;
}

export interface DocsHubController {
  state: {
    docs: DocsHubItem[];
    loadingList: boolean;
    searchQuery: string;
    sortBy: string;
    sortDir: 'asc' | 'desc';
    total: number;
  };
  actions: {
    fetchDocs(): Promise<void>;
    handleSearchChange(value: string): void;
    setDocs(
      value: DocsHubItem[] | ((current: DocsHubItem[]) => DocsHubItem[]),
    ): void;
    setSortBy(value: string): void;
    setSortDir(
      value: 'asc' | 'desc' | ((current: 'asc' | 'desc') => 'asc' | 'desc'),
    ): void;
  };
}

export const docsHubControllerClient: DocsHubControllerClient = {
  listDocsHub,
};

export function useDocsHubController({
  token,
  workspaceSlug,
  listEnabled,
  activeCategory,
  activeSourceApp,
  activeSourceKind,
  activeSpaceId,
  client = docsHubControllerClient,
  searchDebounceMs = 250,
}: DocsHubControllerOptions): DocsHubController {
  const [docs, setDocs] = useState<DocsHubItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loadingList, setLoadingList] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState('updated_at');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchDocs = useCallback(async () => {
    if (!token) return;
    setLoadingList(true);
    try {
      const response = await client.listDocsHub(
        token,
        {
          view: activeCategory,
          q: searchQuery || undefined,
          sort_by: sortBy,
          sort_dir: sortDir,
          source_app: activeSourceApp,
          source_kind: activeSourceKind,
          space_id: activeSpaceId,
        },
        workspaceSlug,
      );
      setDocs(response.items);
      setTotal(response.total);
    } catch {
      setDocs([]);
      setTotal(0);
    } finally {
      setLoadingList(false);
    }
  }, [
    activeCategory,
    activeSpaceId,
    activeSourceApp,
    activeSourceKind,
    client,
    searchQuery,
    sortBy,
    sortDir,
    token,
    workspaceSlug,
  ]);

  useEffect(() => {
    if (!token) return;
    if (listEnabled) {
      void fetchDocs();
    }
  }, [fetchDocs, listEnabled, token]);

  useEffect(
    () => () => {
      if (searchTimerRef.current) {
        clearTimeout(searchTimerRef.current);
      }
    },
    [],
  );

  const handleSearchChange = useCallback(
    (value: string) => {
      if (searchTimerRef.current) {
        clearTimeout(searchTimerRef.current);
      }
      searchTimerRef.current = setTimeout(
        () => setSearchQuery(value),
        searchDebounceMs,
      );
    },
    [searchDebounceMs],
  );

  return {
    state: {
      docs,
      loadingList,
      searchQuery,
      sortBy,
      sortDir,
      total,
    },
    actions: {
      fetchDocs,
      handleSearchChange,
      setDocs,
      setSortBy,
      setSortDir,
    },
  };
}
