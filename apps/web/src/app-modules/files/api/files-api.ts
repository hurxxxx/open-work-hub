import {
  apiFetchJsonWithMappedError,
  jsonBodyHeaders,
  jsonHeaders,
} from '@/src/platform/api/client';
import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

export type FileVisibility = 'private' | 'workspace';
export type FileRagStatus =
  | 'disabled'
  | 'pending'
  | 'processing'
  | 'ready'
  | 'unsupported'
  | 'failed';

export interface FileFolderItem {
  id: string;
  corpus_id?: string | null;
  parent_id: string | null;
  name: string;
  visibility: FileVisibility;
  owner_id: string;
  owner_name: string;
  can_manage: boolean;
  created_at: string;
  updated_at: string;
}

export interface FileItem {
  id: string;
  corpus_id?: string | null;
  folder_id: string | null;
  filename: string;
  content_type: string;
  size_bytes: number;
  visibility: FileVisibility;
  owner_id: string;
  owner_name: string;
  can_delete: boolean;
  rag_status: FileRagStatus;
  rag_updated_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface FileBrowseResponse {
  current_folder: FileFolderItem | null;
  breadcrumbs: FileFolderItem[];
  folders: FileFolderItem[];
  files: FileItem[];
  all_folders: FileFolderItem[];
}

export interface FileDownloadResponse {
  url: string;
}

export type FileSearchStrategy = 'keyword' | 'semantic' | 'hybrid';

export interface FileSearchHighlight {
  start: number;
  end: number;
}

export interface FileSearchSnippet {
  text: string;
  highlights: FileSearchHighlight[];
}

export interface FileSearchHit {
  rank: number;
  file_id: string;
  filename: string;
  folder_id: string | null;
  content_type: string;
  size_bytes: number;
  score: number;
  methods: string[];
  snippet: FileSearchSnippet;
  updated_at: string;
}

export interface FileSearchPayload {
  query: string;
  strategy: FileSearchStrategy;
  page: number;
  page_size: number;
}

export interface FileSearchResponse {
  query: string;
  strategy: FileSearchStrategy;
  page: number;
  page_size: number;
  hits: FileSearchHit[];
  has_more: boolean;
  max_ranked_results: number;
  latency_ms: number;
  trace_id: string | null;
}

export interface FileUploadProgress {
  loaded: number;
  total: number;
  percent: number;
}

export interface FileBulkPayload {
  fileIds: string[];
  folderIds: string[];
}

export type FileCorpusAccessScope = 'workspace' | 'company';

export interface FileCorpusItem {
  id: string;
  name: string;
  managed_workspace_id: string;
  access_scope_kind: FileCorpusAccessScope;
  retrieval_partition_id: string;
  metadata_version: number;
  created_by_id: string;
  created_at: string;
  updated_at: string;
}

export interface FileArchiveDownload {
  blob: Blob;
  filename: string;
}

export class FilesApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  path: string,
  token: string,
  workspaceSlug: string,
  init: RequestInit = {},
): Promise<T> {
  return apiFetchJsonWithMappedError<T>(
    rewriteWorkspaceApiPath(path, workspaceSlug),
    token,
    init,
    (error) => new FilesApiError(error.status, error.message),
  );
}

export function browseFiles(
  token: string,
  workspaceSlug: string,
  folderId?: string | null,
  options: { signal?: AbortSignal } = {},
): Promise<FileBrowseResponse> {
  const params = new URLSearchParams();
  if (folderId) {
    params.set('folder_id', folderId);
  }
  const query = params.toString();
  return request<FileBrowseResponse>(
    `/api/v1/files${query ? `?${query}` : ''}`,
    token,
    workspaceSlug,
    { signal: options.signal },
  );
}

export function searchFiles(
  token: string,
  workspaceSlug: string,
  payload: FileSearchPayload,
  options: { signal?: AbortSignal } = {},
): Promise<FileSearchResponse> {
  return request<FileSearchResponse>(
    '/api/v1/files/search',
    token,
    workspaceSlug,
    {
      method: 'POST',
      body: JSON.stringify(payload),
      signal: options.signal,
    },
  );
}

export function createFileFolder(
  token: string,
  workspaceSlug: string,
  payload: {
    name: string;
    parent_id?: string | null;
    visibility: FileVisibility;
    corpus_id?: string | null;
  },
): Promise<FileFolderItem> {
  return request<FileFolderItem>(
    '/api/v1/files/folders',
    token,
    workspaceSlug,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}

export function listFileCorpora(
  token: string,
  workspaceSlug: string,
): Promise<FileCorpusItem[]> {
  return request<FileCorpusItem[]>(
    '/api/v1/files/corpora',
    token,
    workspaceSlug,
  );
}

export function createFileCorpus(
  token: string,
  workspaceSlug: string,
  name: string,
): Promise<FileCorpusItem> {
  return request<FileCorpusItem>(
    '/api/v1/files/corpora',
    token,
    workspaceSlug,
    {
      method: 'POST',
      body: JSON.stringify({ name }),
    },
  );
}

export function transitionFileCorpus(
  token: string,
  workspaceSlug: string,
  corpusId: string,
  payload: {
    expected_metadata_version: number;
    access_scope_kind: FileCorpusAccessScope;
    reason: string;
    target_workspace_id?: string | null;
    request_id?: string | null;
  },
): Promise<FileCorpusItem> {
  return request<FileCorpusItem>(
    `/api/v1/files/corpora/${encodeURIComponent(corpusId)}/transition`,
    token,
    workspaceSlug,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}

export function updateFileFolder(
  token: string,
  workspaceSlug: string,
  folderId: string,
  payload: {
    name?: string;
    visibility?: FileVisibility;
  },
): Promise<FileFolderItem> {
  return request<FileFolderItem>(
    `/api/v1/files/folders/${encodeURIComponent(folderId)}`,
    token,
    workspaceSlug,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  );
}

export function deleteFileFolder(
  token: string,
  workspaceSlug: string,
  folderId: string,
): Promise<void> {
  return request<void>(
    `/api/v1/files/folders/${encodeURIComponent(folderId)}`,
    token,
    workspaceSlug,
    { method: 'DELETE' },
  );
}

export function bulkDeleteFileItems(
  token: string,
  workspaceSlug: string,
  payload: FileBulkPayload,
): Promise<void> {
  return request<void>('/api/v1/files/bulk-delete', token, workspaceSlug, {
    method: 'POST',
    body: JSON.stringify(toBulkRequest(payload)),
  });
}

export async function downloadFileArchive(
  token: string,
  workspaceSlug: string,
  payload: FileBulkPayload,
): Promise<FileArchiveDownload> {
  const response = await fetch(
    rewriteWorkspaceApiPath('/api/v1/files/archive', workspaceSlug),
    {
      method: 'POST',
      headers: jsonBodyHeaders(token),
      body: JSON.stringify(toBulkRequest(payload)),
      cache: 'no-store',
    },
  );
  if (!response.ok) {
    const errorPayload = await response.json().catch(() => null);
    throw new FilesApiError(
      response.status,
      getUploadErrorMessage(errorPayload, response.status),
    );
  }
  return {
    blob: await response.blob(),
    filename: parseContentDispositionFilename(
      response.headers.get('Content-Disposition'),
    ),
  };
}

export function uploadDriveFile(
  token: string,
  workspaceSlug: string,
  file: File,
  options: {
    corpusId?: string | null;
    folderId?: string | null;
    onProgress?: (progress: FileUploadProgress) => void;
    signal?: AbortSignal;
    visibility: FileVisibility;
  },
): Promise<FileItem> {
  const formData = new FormData();
  formData.append('file', file, file.name);
  if (options.folderId) {
    formData.append('folder_id', options.folderId);
  }
  if (options.corpusId) {
    formData.append('corpus_id', options.corpusId);
  }
  formData.append('visibility', options.visibility);

  return uploadWithProgress<FileItem>(
    rewriteWorkspaceApiPath('/api/v1/files/upload', workspaceSlug),
    token,
    formData,
    options.onProgress,
    options.signal,
  );
}

function toBulkRequest(payload: FileBulkPayload) {
  return {
    file_ids: payload.fileIds,
    folder_ids: payload.folderIds,
  };
}

function uploadWithProgress<T>(
  path: string,
  token: string,
  formData: FormData,
  onProgress?: (progress: FileUploadProgress) => void,
  signal?: AbortSignal,
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const request = new XMLHttpRequest();
    if (signal?.aborted) {
      reject(new FilesApiError(0, 'Upload request was cancelled.'));
      return;
    }

    const abortHandler = () => {
      request.abort();
    };
    const cleanup = () => {
      signal?.removeEventListener('abort', abortHandler);
    };

    signal?.addEventListener('abort', abortHandler, { once: true });
    request.open('POST', path);

    for (const [key, value] of new Headers(jsonHeaders(token)).entries()) {
      request.setRequestHeader(key, value);
    }

    request.upload.onprogress = (event) => {
      const total = event.lengthComputable ? event.total : 0;
      const percent = total > 0 ? Math.round((event.loaded / total) * 100) : 0;
      onProgress?.({
        loaded: event.loaded,
        total,
        percent,
      });
    };

    request.onload = () => {
      cleanup();
      const payload = parseUploadResponse(request.responseText);
      if (request.status < 200 || request.status >= 300) {
        reject(
          new FilesApiError(
            request.status,
            getUploadErrorMessage(payload, request.status),
          ),
        );
        return;
      }
      resolve(payload as T);
    };

    request.onerror = () => {
      cleanup();
      reject(new FilesApiError(0, 'Upload request failed.'));
    };

    request.onabort = () => {
      cleanup();
      reject(new FilesApiError(0, 'Upload request was cancelled.'));
    };

    request.send(formData);
  });
}

function parseContentDispositionFilename(value: string | null): string {
  const fallback = 'files.zip';
  if (!value) {
    return fallback;
  }
  const match = value.match(/filename="?([^";]+)"?/i);
  return match?.[1] || fallback;
}

function parseUploadResponse(responseText: string): unknown {
  if (!responseText) {
    return undefined;
  }
  try {
    return JSON.parse(responseText) as unknown;
  } catch {
    return null;
  }
}

function getUploadErrorMessage(payload: unknown, status: number): string {
  if (
    payload &&
    typeof payload === 'object' &&
    'detail' in payload &&
    typeof payload.detail === 'string'
  ) {
    return payload.detail;
  }
  return `Request failed with ${status}.`;
}

export function getFileDownloadUrl(
  token: string,
  workspaceSlug: string,
  fileId: string,
): Promise<FileDownloadResponse> {
  return request<FileDownloadResponse>(
    `/api/v1/files/${encodeURIComponent(fileId)}/download`,
    token,
    workspaceSlug,
  );
}

export function getFilePreviewUrl(
  token: string,
  workspaceSlug: string,
  fileId: string,
): Promise<FileDownloadResponse> {
  return request<FileDownloadResponse>(
    `/api/v1/files/${encodeURIComponent(fileId)}/preview`,
    token,
    workspaceSlug,
  );
}

export function deleteDriveFile(
  token: string,
  workspaceSlug: string,
  fileId: string,
): Promise<void> {
  return request<void>(
    `/api/v1/files/${encodeURIComponent(fileId)}`,
    token,
    workspaceSlug,
    { method: 'DELETE' },
  );
}
