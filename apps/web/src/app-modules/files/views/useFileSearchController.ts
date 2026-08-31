import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { downloadAuthenticatedContent } from '@/src/platform/browser/browser-download';
import {
  FilesApiError,
  getFileDownloadUrl,
  searchFiles,
  type FileDownloadResponse,
  type FileSearchPayload,
  type FileSearchResponse,
  type FileSearchStrategy,
} from '../api/files-api';
import {
  buildFileSearchParams,
  FILE_SEARCH_PAGE_SIZE,
  orderFileSearchHits,
  parseFileSearchParams,
} from './file-search-view-model';

export interface FileSearchControllerClient {
  download(
    token: string,
    workspaceSlug: string,
    fileId: string,
  ): Promise<FileDownloadResponse>;
  search(
    token: string,
    workspaceSlug: string,
    payload: FileSearchPayload,
    options?: { signal?: AbortSignal },
  ): Promise<FileSearchResponse>;
}

export interface FileSearchControllerMessages {
  authMissing: string;
  downloadFailed: string;
  loadFailed: string;
  queryRequired: string;
  sessionExpired: string;
  workspaceMissing: string;
}

export type FileSearchParamsSetter = (
  next: URLSearchParams,
  options?: { replace?: boolean },
) => void;

export interface FileSearchControllerOptions {
  client?: FileSearchControllerClient;
  logout: () => Promise<void> | void;
  messages: FileSearchControllerMessages;
  openDownload?: (url: string, token: string) => Promise<void> | void;
  searchParams: URLSearchParams;
  setSearchParams: FileSearchParamsSetter;
  token: string | null | undefined;
  workspaceSlug: string | null | undefined;
}

export interface FileSearchControllerState {
  busyDownloadId: string | null;
  error: string | null;
  queryInput: string;
  response: FileSearchResponse | null;
  searching: boolean;
  strategy: FileSearchStrategy;
}

export interface FileSearchControllerActions {
  download(fileId: string): void;
  nextPage(): void;
  previousPage(): void;
  setQueryInput(value: string): void;
  setStrategy(strategy: FileSearchStrategy): void;
  submitSearch(): void;
}

export interface FileSearchController {
  actions: FileSearchControllerActions;
  state: FileSearchControllerState;
}

interface ScopedFileSearchResponse {
  scopeKey: string;
  value: FileSearchResponse;
}

const defaultClient: FileSearchControllerClient = {
  download: getFileDownloadUrl,
  search: searchFiles,
};

export function useFileSearchController({
  client = defaultClient,
  logout,
  messages,
  openDownload = (url, currentToken) =>
    downloadAuthenticatedContent(currentToken, url, 'download'),
  searchParams,
  setSearchParams,
  token,
  workspaceSlug,
}: FileSearchControllerOptions): FileSearchController {
  const searchParamsKey = searchParams.toString();
  const urlSearch = useMemo(
    () => parseFileSearchParams(new URLSearchParams(searchParamsKey)),
    [searchParamsKey],
  );
  const [queryInput, setQueryInputState] = useState(urlSearch.query);
  const [strategy, setStrategyState] = useState<FileSearchStrategy>(
    urlSearch.strategy,
  );
  const [scopedResponse, setScopedResponse] =
    useState<ScopedFileSearchResponse | null>(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyDownloadId, setBusyDownloadId] = useState<string | null>(null);
  const queryInputRef = useRef(queryInput);
  const strategyRef = useRef(strategy);
  const searchAbortRef = useRef<AbortController | null>(null);
  const searchSequenceRef = useRef(0);
  const downloadSequenceRef = useRef(0);
  const lastSearchSignatureRef = useRef('');
  const scopeKey = fileSearchScopeKey(token, workspaceSlug);
  const response =
    scopedResponse?.scopeKey === scopeKey ? scopedResponse.value : null;

  queryInputRef.current = queryInput;
  strategyRef.current = strategy;

  useEffect(() => {
    queryInputRef.current = urlSearch.query;
    strategyRef.current = urlSearch.strategy;
    setQueryInputState(urlSearch.query);
    setStrategyState(urlSearch.strategy);
  }, [searchParamsKey, urlSearch.query, urlSearch.strategy]);

  const runSearch = useCallback(
    async (options?: {
      page?: number;
      query?: string;
      strategy?: FileSearchStrategy;
      syncUrl?: boolean;
    }) => {
      if (!token) {
        setError(messages.authMissing);
        return;
      }
      if (!workspaceSlug) {
        setError(messages.workspaceMissing);
        return;
      }
      const query = (options?.query ?? queryInputRef.current).trim();
      if (!query) {
        setError(messages.queryRequired);
        return;
      }
      const nextStrategy = options?.strategy ?? strategyRef.current;
      const page = options?.page ?? 1;
      const sequence = searchSequenceRef.current + 1;
      searchSequenceRef.current = sequence;
      searchAbortRef.current?.abort();
      const controller = new AbortController();
      const requestScopeKey = fileSearchScopeKey(token, workspaceSlug);
      searchAbortRef.current = controller;
      setSearching(true);
      setError(null);
      setScopedResponse(null);
      try {
        const result = await client.search(
          token,
          workspaceSlug,
          {
            page,
            page_size: FILE_SEARCH_PAGE_SIZE,
            query,
            strategy: nextStrategy,
          },
          { signal: controller.signal },
        );
        if (
          controller.signal.aborted ||
          searchSequenceRef.current !== sequence
        ) {
          return;
        }
        const orderedResult = {
          ...result,
          hits: orderFileSearchHits(result.hits),
        };
        setScopedResponse({ scopeKey: requestScopeKey, value: orderedResult });
        lastSearchSignatureRef.current = searchSignature({
          page,
          query,
          strategy: nextStrategy,
          token,
          workspaceSlug,
        });
        if (options?.syncUrl !== false) {
          setSearchParams(
            buildFileSearchParams({ page, query, strategy: nextStrategy }),
            { replace: true },
          );
        }
      } catch (caughtError: unknown) {
        if (controller.signal.aborted || isAbortError(caughtError)) {
          return;
        }
        if (
          caughtError instanceof FilesApiError &&
          caughtError.status === 401
        ) {
          setError(messages.sessionExpired);
          void logout();
          return;
        }
        setError(
          caughtError instanceof Error
            ? caughtError.message
            : messages.loadFailed,
        );
      } finally {
        if (searchSequenceRef.current === sequence) {
          setSearching(false);
        }
        if (searchAbortRef.current === controller) {
          searchAbortRef.current = null;
        }
      }
    },
    [
      client,
      logout,
      messages.authMissing,
      messages.loadFailed,
      messages.queryRequired,
      messages.sessionExpired,
      messages.workspaceMissing,
      setSearchParams,
      token,
      workspaceSlug,
    ],
  );

  const urlSearchSignature = searchSignature({
    ...urlSearch,
    token,
    workspaceSlug,
  });

  useEffect(() => {
    searchAbortRef.current?.abort();
    searchSequenceRef.current += 1;
    downloadSequenceRef.current += 1;
    setScopedResponse(null);
    setSearching(false);
    setBusyDownloadId(null);
    setError(null);
  }, [scopeKey]);

  useEffect(() => {
    if (urlSearch.query) {
      return;
    }
    searchAbortRef.current?.abort();
    searchSequenceRef.current += 1;
    setScopedResponse(null);
    setSearching(false);
  }, [urlSearch.query]);

  useEffect(() => {
    if (!token || !workspaceSlug || !urlSearch.query) {
      return;
    }
    if (lastSearchSignatureRef.current === urlSearchSignature) {
      return;
    }
    void runSearch({
      page: urlSearch.page,
      query: urlSearch.query,
      strategy: urlSearch.strategy,
      syncUrl: false,
    });
  }, [
    runSearch,
    token,
    urlSearch.page,
    urlSearch.query,
    urlSearch.strategy,
    urlSearchSignature,
    workspaceSlug,
  ]);

  useEffect(
    () => () => {
      searchAbortRef.current?.abort();
      searchSequenceRef.current += 1;
      downloadSequenceRef.current += 1;
    },
    [],
  );

  const download = useCallback(
    async (fileId: string) => {
      if (!token) {
        setError(messages.authMissing);
        return;
      }
      if (!workspaceSlug) {
        setError(messages.workspaceMissing);
        return;
      }
      const sequence = downloadSequenceRef.current + 1;
      downloadSequenceRef.current = sequence;
      setBusyDownloadId(fileId);
      setError(null);
      try {
        const result = await client.download(token, workspaceSlug, fileId);
        if (downloadSequenceRef.current === sequence) {
          await openDownload(result.url, token);
        }
      } catch (caughtError: unknown) {
        if (downloadSequenceRef.current !== sequence) {
          return;
        }
        if (
          caughtError instanceof FilesApiError &&
          caughtError.status === 401
        ) {
          setError(messages.sessionExpired);
          void logout();
          return;
        }
        setError(
          caughtError instanceof Error
            ? caughtError.message
            : messages.downloadFailed,
        );
      } finally {
        if (downloadSequenceRef.current === sequence) {
          setBusyDownloadId(null);
        }
      }
    },
    [
      client,
      logout,
      messages.authMissing,
      messages.downloadFailed,
      messages.sessionExpired,
      messages.workspaceMissing,
      openDownload,
      token,
      workspaceSlug,
    ],
  );

  const setQueryInput = useCallback((value: string) => {
    queryInputRef.current = value;
    setQueryInputState(value);
  }, []);
  const setStrategy = useCallback((nextStrategy: FileSearchStrategy) => {
    strategyRef.current = nextStrategy;
    setStrategyState(nextStrategy);
  }, []);

  const actions = useMemo<FileSearchControllerActions>(
    () => ({
      download: (fileId) => void download(fileId),
      nextPage: () => {
        if (response?.has_more) {
          void runSearch({
            page: response.page + 1,
            query: response.query,
            strategy: response.strategy,
          });
        }
      },
      previousPage: () => {
        if (response && response.page > 1) {
          void runSearch({
            page: response.page - 1,
            query: response.query,
            strategy: response.strategy,
          });
        }
      },
      setQueryInput,
      setStrategy,
      submitSearch: () => void runSearch({ page: 1 }),
    }),
    [download, response, runSearch, setQueryInput, setStrategy],
  );

  return {
    actions,
    state: {
      busyDownloadId,
      error,
      queryInput,
      response,
      searching,
      strategy,
    },
  };
}

function searchSignature(input: {
  page: number;
  query: string;
  strategy: FileSearchStrategy;
  token: string | null | undefined;
  workspaceSlug: string | null | undefined;
}): string {
  return [
    input.token ?? '',
    input.workspaceSlug ?? '',
    input.query,
    input.strategy,
    input.page,
  ].join('\u0000');
}

function fileSearchScopeKey(
  token: string | null | undefined,
  workspaceSlug: string | null | undefined,
): string {
  return `${token ?? ''}\u0000${workspaceSlug ?? ''}`;
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}
