import { useFeedback } from '@open-work-hub/ui';
import { Download, X } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { DocumentArtifact } from '@/src/components/artifacts/DocumentArtifact';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { apiFetchBinary } from '@/src/platform/api/client';
import { downloadBlobAsFile } from '@/src/platform/browser/browser-download';
import { formatByteSize } from '@/src/platform/format/byte-size';
import { formatDateTime } from '@/src/platform/time/time-utils';
import {
  getHermesFileRevision,
  getHermesRun,
  hermesFileRevisionContentPath,
  listHermesFileRevisions,
  previewHermesFileRevision,
  previewHermesAsset,
  type HermesFileRevision,
  type HermesRun,
} from '../../api/hermes-agent-api';
import { ChatResultSurface } from './ChatResultSurface';
import { hermesFilePreviewKind } from './hermes-file-preview';
import { CodeArtifact } from './artifacts/CodeArtifact';
import { HtmlArtifact } from './artifacts/HtmlArtifact';
import { SvgArtifact } from './artifacts/SvgArtifact';
import { bundleHtmlPreview } from './artifacts/html-preview-bundle';

export function HermesFilePanel({
  sessionId,
  fileId,
  revisionId,
  onRevisionChange,
  onClose,
}: {
  sessionId: string;
  fileId: string;
  revisionId: string | null;
  onRevisionChange: (revisionId: string) => void;
  onClose: () => void;
}) {
  const { token } = useAuth();
  const { t } = useTranslation('apps');
  const feedback = useFeedback();
  const [{ data: revisions, has_more: hasMore }, setVersionPage] = useState<{
    data: HermesFileRevision[];
    has_more: boolean;
  }>({ data: [], has_more: false });
  const [revision, setRevision] = useState<HermesFileRevision | null>(null);
  const [error, setError] = useState(false);
  const [listError, setListError] = useState(false);
  const [preview, setPreview] = useState<{ text: string; url: string } | null>(
    null,
  );
  const [previewHtml, setPreviewHtml] = useState<string | null>(null);
  const [bundleError, setBundleError] = useState(false);
  const [sourceRun, setSourceRun] = useState<HermesRun | null>(null);
  const [sourceLoading, setSourceLoading] = useState(false);
  const [showSource, setShowSource] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const ownerKey = useMemo(
    () => ({ token, sessionId, fileId }),
    [token, sessionId, fileId],
  );
  const owner = useRef(ownerKey);
  owner.current = ownerKey;
  const moreRequest = useRef<object | null>(null);

  useEffect(() => {
    setVersionPage({ data: [], has_more: false });
    setListError(false);
    setError(false);
    setLoadingMore(false);
    moreRequest.current = null;
    if (!token) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const refresh = () =>
      void listHermesFileRevisions(token, sessionId, fileId)
        .then((result) => {
          if (cancelled) return;
          setVersionPage((current) => {
            if (!result.has_more || current.data.length <= result.data.length)
              return result;
            return {
              data: [
                ...new Map(
                  [...result.data, ...current.data].map((item) => [
                    item.id,
                    item,
                  ]),
                ).values(),
              ],
              has_more: current.has_more,
            };
          });
          setListError(result.data.length === 0);
        })
        .catch(() => {
          if (!cancelled) setListError(true);
        })
        .finally(() => {
          if (!cancelled) timer = setTimeout(refresh, 4000);
        });
    refresh();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [token, sessionId, fileId]);

  useEffect(() => {
    if (!revisionId && revisions[0]) onRevisionChange(revisions[0].id);
  }, [revisionId, revisions, onRevisionChange]);

  useEffect(() => {
    setRevision(null);
    setPreview(null);
    setPreviewHtml(null);
    setBundleError(false);
    setError(false);
    setSourceRun(null);
    setShowSource(false);
    if (!token || !revisionId) return;
    let cancelled = false;
    let objectUrl: string | null = null;
    const abort = new AbortController();
    void (async () => {
      const selected = await getHermesFileRevision(token, revisionId);
      if (cancelled) return;
      if (selected.session_id !== sessionId || selected.file_id !== fileId)
        throw new Error(t('ai.filePreview.unavailable'));
      setRevision(selected);
      const kind = hermesFilePreviewKind(selected);
      const limit = kind === 'image' ? 10 * 1024 * 1024 : 2 * 1024 * 1024;
      if (!kind || selected.size_bytes > limit) return;
      const blob = await previewHermesFileRevision(
        token,
        selected,
        limit,
        abort.signal,
      );
      if (cancelled) return;
      const text = kind === 'image' ? '' : await blob.text();
      if (cancelled) return;
      if (kind === 'image') objectUrl = URL.createObjectURL(blob);
      setPreview({ text, url: objectUrl ?? '' });
      if (kind === 'html') {
        try {
          const html = await bundleHtmlPreview(
            text,
            selected.relative_path,
            (path) =>
              previewHermesAsset(token, selected.id, path, abort.signal),
            abort.signal,
          );
          if (!cancelled) setPreviewHtml(html);
        } catch {
          if (!cancelled) setBundleError(true);
        }
      }
    })().catch(() => {
      if (!cancelled) setError(true);
    });
    return () => {
      cancelled = true;
      abort.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [token, revisionId, fileId, sessionId, t]);

  useEffect(() => {
    if (!showSource || !token || !revision?.run_id) return;
    let cancelled = false;
    setSourceLoading(true);
    void getHermesRun(token, revision.run_id)
      .then((run) => {
        if (!cancelled && run.session_binding_id === sessionId)
          setSourceRun(run);
      })
      .catch(() => {
        if (!cancelled) feedback.error(t('ai.filePreview.unavailable'));
      })
      .finally(() => {
        if (!cancelled) setSourceLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [showSource, token, revision, sessionId, feedback, t]);

  const kind = revision ? hermesFilePreviewKind(revision) : null;
  const tooLarge =
    revision && revision.size_bytes > (kind === 'image' ? 10 : 2) * 1024 * 1024;
  const download = async () => {
    if (!token || !revision) return;
    try {
      const { blob } = await apiFetchBinary(
        hermesFileRevisionContentPath(revision.id),
        token,
        { signal: AbortSignal.timeout(60_000), redirect: 'error' },
      );
      downloadBlobAsFile(
        blob,
        revision.relative_path.split('/').at(-1) || 'file',
      );
    } catch {
      feedback.error(t('ai.filePreview.unavailable'));
    }
  };
  const loadMore = async () => {
    if (!token || moreRequest.current === ownerKey) return;
    moreRequest.current = ownerKey;
    setLoadingMore(true);
    try {
      const page = await listHermesFileRevisions(
        token,
        sessionId,
        fileId,
        revisions.length,
      );
      if (owner.current !== ownerKey) return;
      setVersionPage((current) => ({
        data: [
          ...new Map(
            [...current.data, ...page.data].map((item) => [item.id, item]),
          ).values(),
        ],
        has_more: page.has_more,
      }));
    } catch {
      if (owner.current === ownerKey)
        feedback.error(t('ai.filePreview.unavailable'));
    } finally {
      if (owner.current === ownerKey) {
        setLoadingMore(false);
        moreRequest.current = null;
      }
    }
  };

  return (
    <ChatResultSurface
      title={revision?.relative_path ?? t('ai.filePreview.title')}
      onClose={onClose}
    >
      <header className="flex items-center gap-2 border-b border-app-border p-3">
        <h2 className="min-w-0 flex-1 truncate app-text-body-sm font-semibold text-app-ink">
          {revision?.relative_path ?? t('ai.filePreview.title')}
        </h2>
        <button
          type="button"
          aria-label={t('ai.artifacts.downloadContent')}
          disabled={!revision}
          onClick={() => void download()}
          className="p-2 text-app-ink/65"
        >
          <Download size={16} />
        </button>
        <button
          type="button"
          aria-label={t('ai.artifacts.closePanel')}
          onClick={onClose}
          className="p-2 text-app-ink/65"
        >
          <X size={16} />
        </button>
      </header>
      <div className="flex flex-wrap items-center gap-2 border-b border-app-border p-3 app-text-caption text-app-ink/65">
        <select
          aria-label={t('ai.filePreview.version')}
          value={revisionId ?? ''}
          onChange={(event) => onRevisionChange(event.target.value)}
          className="min-w-0 max-w-full bg-app-surface text-app-ink"
        >
          {!revisions.some((item) => item.id === revisionId) && revision ? (
            <option value={revision.id}>
              {formatDateTime(revision.created_at, {
                dateStyle: 'short',
                timeStyle: 'medium',
              })}
            </option>
          ) : null}
          {revisions.map((item) => (
            <option key={item.id} value={item.id}>
              {formatDateTime(item.created_at, {
                dateStyle: 'short',
                timeStyle: 'medium',
              })}
            </option>
          ))}
        </select>
        {revisions[0] && revisionId && revisions[0].id !== revisionId ? (
          <button
            type="button"
            onClick={() => onRevisionChange(revisions[0].id)}
          >
            {t('ai.filePreview.latestVersion')}
          </button>
        ) : null}
        {hasMore ? (
          <button
            type="button"
            disabled={loadingMore}
            onClick={() => void loadMore()}
          >
            {t('ai.filePreview.olderVersions')}
          </button>
        ) : null}
        {revision ? <span>{formatByteSize(revision.size_bytes)}</span> : null}
        {revision?.run_id ? (
          <button
            type="button"
            aria-pressed={showSource}
            onClick={() => setShowSource((value) => !value)}
          >
            {t('ai.filePreview.sourceRun')}
          </button>
        ) : (
          <span>{t('ai.filePreview.conversationFile')}</span>
        )}
      </div>
      <div className="custom-scrollbar min-h-0 flex-1 overflow-auto p-4 text-app-ink app-text-body-sm">
        {showSource ? (
          <div className="mb-4 border-b border-app-border pb-3">
            {sourceLoading ? (
              <p role="status">{t('hermesWorkspace.loading')}</p>
            ) : sourceRun ? (
              <>
                <p>{t(`hermesWorkspace.status.${sourceRun.status}`)}</p>
                <DocumentArtifact content={sourceRun.output_text ?? ''} />
              </>
            ) : null}
          </div>
        ) : null}
        {error || listError ? (
          <p role="alert">{t('ai.filePreview.unavailable')}</p>
        ) : !revision ? (
          <p role="status">{t('hermesWorkspace.loading')}</p>
        ) : !kind ? (
          <p>{t('ai.filePreview.unsupported')}</p>
        ) : tooLarge ? (
          <p>{t('ai.filePreview.tooLarge')}</p>
        ) : !preview ? (
          <p role="status">{t('hermesWorkspace.loading')}</p>
        ) : kind === 'image' ? (
          <img
            src={preview.url}
            alt={revision.relative_path}
            onError={() => setError(true)}
            className="max-h-full max-w-full object-contain"
          />
        ) : kind === 'html' ? (
          <div className="h-full min-h-96">
            <HtmlArtifact
              previewContent={previewHtml}
              previewError={bundleError}
              content={preview.text}
              title={revision.relative_path}
            />
          </div>
        ) : kind === 'svg' ? (
          <SvgArtifact
            content={preview.text}
            ariaLabel={revision.relative_path}
          />
        ) : kind === 'document' ? (
          <DocumentArtifact content={preview.text} />
        ) : (
          <CodeArtifact
            content={preview.text}
            language={revision.relative_path.split('.').at(-1) ?? null}
          />
        )}
      </div>
    </ChatResultSurface>
  );
}
