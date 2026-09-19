import type { components } from './api.generated';

type Schemas = components['schemas'];
export type Task = Schemas['TaskOut'];
export type Detail = Schemas['TaskDetail'];
export type Revision = Schemas['RevisionOut'];
export type Account = Schemas['AccountOut'];
export type Model = Schemas['ModelOut'];
export type Thread = Schemas['ThreadSummary'];
export type ThreadPage = Schemas['ThreadPage'];
export type Change = Schemas['ChangeOut'];
export type Diff = Schemas['DiffOut'];
export type Pending = Schemas['RequestOut'];
export type DeviceLogin = Schemas['DeviceLoginOut'];
export type Attachment = Schemas['AttachmentOut'];

export const apiBasePath = new URL(
  'api/',
  window.location.href,
).pathname.replace(/\/$/, '');

export class ApiError extends Error {
  constructor(public code: string) {
    super(code);
  }
}

function csrfToken() {
  return decodeURIComponent(
    document.cookie
      .split('; ')
      .find((row) => row.startsWith('codex_console_csrf='))
      ?.split('=')[1] ?? '',
  );
}

export const attachmentDownload = (taskId: string, id: string) =>
  `${apiBasePath}/tasks/${taskId}/attachments/${id}/download`;

export function uploadAttachment(
  taskId: string,
  id: string,
  file: File,
  signal: AbortSignal,
  onProgress: (percent: number) => void,
): Promise<Attachment> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open('PUT', `${apiBasePath}/tasks/${taskId}/attachments/${id}`);
    request.timeout = 125000;
    request.setRequestHeader('Content-Type', 'application/octet-stream');
    request.setRequestHeader('X-CSRF-Token', csrfToken());
    request.setRequestHeader('X-File-Name', encodeURIComponent(file.name));
    const abort = () => request.abort();
    signal.addEventListener('abort', abort, { once: true });
    request.onloadend = () => signal.removeEventListener('abort', abort);
    request.upload.onprogress = (event) => {
      if (event.lengthComputable)
        onProgress(Math.round((event.loaded / event.total) * 100));
    };
    request.onload = () => {
      let body;
      try {
        body = JSON.parse(request.responseText);
      } catch {
        reject(new ApiError('request_failed'));
        return;
      }
      if (request.status >= 200 && request.status < 300)
        resolve(body as Attachment);
      else reject(new ApiError(body.code ?? 'request_failed'));
    };
    request.onerror = () => reject(new ApiError('request_failed'));
    request.ontimeout = () => reject(new ApiError('attachment_upload_timeout'));
    request.onabort = () =>
      reject(new DOMException('Upload cancelled', 'AbortError'));
    if (signal.aborted) {
      reject(new DOMException('Upload cancelled', 'AbortError'));
      return;
    }
    request.send(file);
  });
}

export async function api<T>(
  path: string,
  body?: unknown,
  method?: string,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(`${apiBasePath}${path}`, {
    method: method ?? (body === undefined ? 'GET' : 'POST'),
    credentials: 'same-origin',
    signal,
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-Token': csrfToken(),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const result = (await response.json().catch(() => ({}))) as {
      code?: string;
    };
    throw new ApiError(result.code ?? 'request_failed');
  }
  return response.json() as Promise<T>;
}

export const active = (task: Task | null) =>
  !!task && ['starting', 'running', 'waiting'].includes(task.status);
export const locked = (task: Task | null) =>
  active(task) || task?.status === 'uncertain';
export const record = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
export const string = (value: unknown): string =>
  typeof value === 'string' ? value : '';
