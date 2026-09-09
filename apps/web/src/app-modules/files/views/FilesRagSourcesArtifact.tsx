import { Download, FileText, Loader2, MapPin, Search } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/src/platform/auth/auth-provider';
import { downloadAuthenticatedContent } from '@/src/platform/browser/browser-download';
import { FilesApiError, getFileDownloadUrl } from '../api/files-api';

interface FilesRagSource {
  ref: string;
  fileId: string;
  filename: string;
  locator: string | null;
  methods: string[];
}

interface FilesRagSourcesPayload {
  version: number;
  sources: FilesRagSource[];
}

export function buildFilesRagSourcesPreview(content: string): string | null {
  const parsed = parseFilesRagSources(content);
  if (!parsed) {
    return null;
  }
  return parsed.sources.map((source) => source.filename).join(' · ');
}

export function FilesRagSourcesArtifact({ content }: { content: string }) {
  const { t } = useTranslation('apps');
  const { logout, token } = useAuth();

  const parsed = useMemo(() => parseFilesRagSources(content), [content]);
  const [busyFileId, setBusyFileId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const download = async (source: FilesRagSource) => {
    if (!token) {
      setError(t('files.chat.sources.authMissing'));
      return;
    }

    setBusyFileId(source.fileId);
    setError(null);
    try {
      // The endpoint issues a new signed URL only after rechecking the
      // caller's current Files ACL.
      const response = await getFileDownloadUrl(token, source.fileId);
      await downloadAuthenticatedContent(token, response.url, source.filename);
    } catch (caughtError: unknown) {
      if (caughtError instanceof FilesApiError && caughtError.status === 401) {
        setError(t('files.chat.sources.sessionExpired'));
        void logout();
      } else {
        setError(t('files.chat.sources.downloadFailed'));
      }
    } finally {
      setBusyFileId(null);
    }
  };

  if (!parsed) {
    return (
      <div className="rounded-md border border-dashed border-app-border bg-app-bg p-6 text-center app-text-body-sm text-app-ink/55">
        {t('files.chat.sources.invalid')}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-app-ink/70">
        <Search aria-hidden="true" size={16} />
        <h3 className="app-text-title-md">
          {t('files.chat.sources.title', {
            count: parsed.sources.length,
          })}
        </h3>
      </div>

      {error ? (
        <div
          role="alert"
          className="rounded-md border border-app-danger/30 bg-app-danger/5 px-3 py-2 app-text-body-sm text-app-danger"
        >
          {error}
        </div>
      ) : null}

      {parsed.sources.length === 0 ? (
        <div className="rounded-md border border-dashed border-app-border bg-app-bg p-6 text-center app-text-body-sm text-app-ink/55">
          {t('files.chat.sources.empty')}
        </div>
      ) : (
        <ol className="space-y-2">
          {parsed.sources.map((source) => {
            const busy = busyFileId === source.fileId;
            return (
              <li
                key={`${source.ref}-${source.fileId}`}
                className="rounded-md border border-app-border bg-app-bg p-3"
              >
                <div className="flex items-start gap-3">
                  <div className="flex size-9 shrink-0 items-center justify-center rounded-md border border-app-border bg-app-surface text-app-accent">
                    <FileText aria-hidden="true" size={16} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="rounded bg-app-accent/10 px-1.5 py-0.5 app-text-caption font-semibold text-app-accent">
                        {source.ref}
                      </span>
                      <span className="min-w-0 truncate app-text-control-sm text-app-ink">
                        {source.filename}
                      </span>
                    </div>
                    {source.locator ? (
                      <div className="mt-1 flex items-center gap-1 app-text-caption text-app-ink/55">
                        <MapPin aria-hidden="true" size={12} />
                        <span className="truncate">{source.locator}</span>
                      </div>
                    ) : null}
                    {source.methods.length > 0 ? (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {source.methods.map((method) => (
                          <span
                            key={method}
                            className="rounded border border-app-border bg-app-surface px-1.5 py-0.5 app-text-micro text-app-ink/55"
                          >
                            {method}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void download(source)}
                    aria-label={t('files.chat.sources.download', {
                      name: source.filename,
                    })}
                    className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-md border border-app-border bg-app-surface px-3 app-text-control-sm text-app-ink transition-colors hover:border-app-accent hover:text-app-accent disabled:cursor-wait disabled:opacity-50"
                  >
                    {busy ? (
                      <Loader2
                        aria-hidden="true"
                        className="animate-spin"
                        size={14}
                      />
                    ) : (
                      <Download aria-hidden="true" size={14} />
                    )}
                    {busy
                      ? t('files.chat.sources.downloading')
                      : t('files.chat.sources.downloadAction')}
                  </button>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}

function parseFilesRagSources(content: string): FilesRagSourcesPayload | null {
  let value: unknown;
  try {
    value = JSON.parse(content);
  } catch {
    return null;
  }
  if (!isRecord(value) || !Array.isArray(value.sources)) {
    return null;
  }
  const version =
    typeof value.version === 'number' && Number.isFinite(value.version)
      ? value.version
      : 1;
  const sources = value.sources
    .map((source, index) => parseFilesRagSource(source, index))
    .filter((source): source is FilesRagSource => source !== null);
  return { version, sources };
}

function parseFilesRagSource(
  value: unknown,
  index: number,
): FilesRagSource | null {
  if (!isRecord(value)) {
    return null;
  }
  const fileId = stringValue(value.file_id, value.fileId);
  if (!fileId) {
    return null;
  }
  return {
    ref: stringValue(value.ref, value.citation, value.label) ?? `F${index + 1}`,
    fileId,
    filename:
      stringValue(value.filename, value.file_name, value.name) ?? fileId,
    locator: stringValue(value.locator),
    methods: stringArray(
      value.methods,
      value.retrieval_methods,
      value.retrieval_method,
    ),
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function stringValue(...values: unknown[]): string | null {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) {
      return value.trim();
    }
  }
  return null;
}

function stringArray(...values: unknown[]): string[] {
  for (const value of values) {
    if (Array.isArray(value)) {
      return value
        .filter((item): item is string => typeof item === 'string')
        .map((item) => item.trim())
        .filter(Boolean);
    }
    if (typeof value === 'string' && value.trim()) {
      return [value.trim()];
    }
  }
  return [];
}
