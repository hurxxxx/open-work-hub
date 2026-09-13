import { useFeedback } from '@open-work-hub/ui';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';

import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  downloadAuthenticatedContent,
  downloadBlobAsFile,
} from '@/src/platform/browser/browser-download';
import { formatByteSize } from '@/src/platform/format/byte-size';
import {
  downloadHermesTerminalFile,
  listHermesTerminalFiles,
  listHermesTerminalSessions,
  type HermesTerminalSession,
  type HermesTerminalFileEntry,
} from '@/src/app-modules/hermes-terminal/public-api';
import {
  createHermesSession,
  listHermesFiles,
  listHermesRuns,
  listHermesSessions,
  stopHermesRun,
  uploadHermesFile,
  type HermesFile,
  type HermesRun,
} from '../api/hermes-agent-api';

export function HermesWorkspacePanel({
  conversationId,
  scopeRef,
  scopeResourceId,
}: {
  conversationId: string | null;
  scopeRef?: string;
  scopeResourceId?: string;
}) {
  const { token } = useAuth();
  const { t } = useTranslation('apps');
  const feedback = useFeedback();
  const [, setSearchParams] = useSearchParams();
  const [files, setFiles] = useState<HermesFile[]>([]);
  const [runs, setRuns] = useState<HermesRun[]>([]);
  const [sessionTitles, setSessionTitles] = useState<Record<string, string>>(
    {},
  );
  const [legacyFailed, setLegacyFailed] = useState(false);
  const [legacySessions, setLegacySessions] = useState<HermesTerminalSession[]>(
    [],
  );
  const [legacyId, setLegacyId] = useState('');
  const [legacyPath, setLegacyPath] = useState('');
  const [legacyFiles, setLegacyFiles] = useState<HermesTerminalFileEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [revision, setRevision] = useState(0);
  const owner = useRef({ conversationId, token });
  owner.current = { conversationId, token };

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    setFiles([]);
    setRuns([]);
    setLoading(true);
    setFailed(false);
    const load = async () => {
      try {
        const [fileResult, runResult] = await Promise.all([
          conversationId
            ? listHermesFiles(token, conversationId)
            : Promise.resolve({ data: [] }),
          listHermesRuns(token, { status: 'active', limit: 100 }),
        ]);
        if (cancelled) return;
        setFiles(fileResult.data);
        setRuns(runResult.data);
        setFailed(false);
      } catch {
        if (!cancelled) setFailed(true);
      } finally {
        if (!cancelled) {
          setLoading(false);
          timer = setTimeout(load, 4000);
        }
      }
    };
    void load();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [token, conversationId, revision, t]);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    void listHermesSessions(token, { limit: 100 })
      .then(({ data }) => {
        if (!cancelled)
          setSessionTitles(
            Object.fromEntries(
              data.map((session) => [
                session.id,
                session.title ||
                  session.preview ||
                  t('hermesWorkspace.untitled'),
              ]),
            ),
          );
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [token, conversationId, revision, t]);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    setLegacySessions([]);
    setLegacyId('');
    setLegacyFailed(false);
    void listHermesTerminalSessions(token)
      .then(({ items }) => {
        if (!cancelled) setLegacySessions(items);
      })
      .catch(() => {
        if (!cancelled) setLegacyFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  useEffect(() => {
    setLegacyFiles([]);
    if (!token || !legacyId) return;
    let cancelled = false;
    void listHermesTerminalFiles(token, legacyId, legacyPath)
      .then(({ items }) => {
        if (!cancelled) setLegacyFiles(items);
      })
      .catch(() => {
        if (!cancelled) feedback.error(t('hermesWorkspace.operationFailed'));
      });
    return () => {
      cancelled = true;
    };
  }, [token, legacyId, legacyPath, feedback, t]);

  const openSession = (id: string) =>
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.set('c', id);
      next.delete('a');
      return next;
    });
  const runAction = async (action: () => Promise<unknown>) => {
    try {
      await action();
      setRevision((value) => value + 1);
    } catch {
      feedback.error(t('hermesWorkspace.operationFailed'));
    }
  };
  const upload = async (file: File) => {
    if (!token) return;
    if (file.size > 64 * 1024 * 1024) {
      feedback.error(t('hermesWorkspace.fileTooLarge'));
      return;
    }
    setUploading(true);
    const startedIn = conversationId;
    try {
      const sessionId =
        conversationId ??
        (
          await createHermesSession(token, {
            scope_ref: scopeRef,
            scope_resource_id: scopeResourceId,
          })
        ).id;
      await uploadHermesFile(token, sessionId, file);
      if (
        owner.current.conversationId === startedIn &&
        owner.current.token === token
      ) {
        openSession(sessionId);
        setRevision((value) => value + 1);
      }
      feedback.success(t('hermesWorkspace.uploaded'));
    } catch {
      feedback.error(t('hermesWorkspace.operationFailed'));
    } finally {
      setUploading(false);
    }
  };

  return (
    <details className="border-b border-app-border px-4 py-2 text-app-ink app-text-body-sm">
      <summary className="cursor-pointer">
        {t('hermesWorkspace.title', { count: runs.length })}
      </summary>
      <div className="max-h-64 space-y-3 overflow-auto py-3">
        <p className="text-app-ink/60">{t('hermesWorkspace.continues')}</p>
        {loading ? (
          <p role="status">{t('hermesWorkspace.loading')}</p>
        ) : failed ? (
          <p role="alert">{t('hermesWorkspace.loadFailed')}</p>
        ) : null}
        <ul className="divide-y divide-app-border">
          {runs.map((run) => (
            <li key={run.id} className="flex items-center gap-2 py-1">
              <button
                type="button"
                disabled={!run.session_binding_id}
                className="min-w-0 flex-1 truncate text-start"
                onClick={() =>
                  run.session_binding_id && openSession(run.session_binding_id)
                }
              >
                <span className="block truncate">
                  {run.session_binding_id
                    ? sessionTitles[run.session_binding_id] ||
                      t('hermesWorkspace.untitled')
                    : t('hermesWorkspace.background')}
                </span>
                {t('hermesWorkspace.run', {
                  status: t(`hermesWorkspace.status.${run.status}`),
                  progress: run.progress_percent,
                })}
              </button>
              <button
                type="button"
                onClick={() =>
                  token && void runAction(() => stopHermesRun(token, run.id))
                }
              >
                {t('hermesWorkspace.stop')}
              </button>
            </li>
          ))}
        </ul>
        <label className="flex items-center gap-2">
          <span className="shrink-0">{t('hermesWorkspace.attach')}</span>
          <input
            type="file"
            aria-label={t('hermesWorkspace.attach')}
            disabled={
              !token ||
              loading ||
              failed ||
              uploading ||
              (Boolean(conversationId) &&
                runs.some((run) => run.session_binding_id === conversationId))
            }
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = '';
              if (file) void upload(file);
            }}
            className="min-w-0 max-w-full"
          />
        </label>
        <ul className="divide-y divide-app-border">
          {files.map((file) => (
            <li
              key={file.id}
              className="flex items-center justify-between gap-2 py-1"
            >
              <button
                type="button"
                className="min-w-0 truncate text-start"
                onClick={() =>
                  token &&
                  void runAction(() =>
                    downloadAuthenticatedContent(
                      token,
                      `/api/v1/agent/files/${encodeURIComponent(file.id)}/content`,
                      file.relative_path,
                    ),
                  )
                }
              >
                {file.relative_path}
              </button>
              <span className="shrink-0 text-app-ink/60">
                {formatByteSize(file.size_bytes)}
              </span>
            </li>
          ))}
        </ul>
        {!loading && !failed && !files.length ? (
          <p className="text-app-ink/60">{t('hermesWorkspace.noFiles')}</p>
        ) : null}
        {legacyFailed ? (
          <p role="alert">{t('hermesWorkspace.legacyLoadFailed')}</p>
        ) : null}
        {legacySessions.length > 0 ? (
          <details>
            <summary>{t('hermesWorkspace.legacy')}</summary>
            <select
              aria-label={t('hermesWorkspace.legacy')}
              value={legacyId}
              onChange={(event) => {
                setLegacyId(event.target.value);
                setLegacyPath('');
              }}
              className="my-2 max-w-full bg-app-surface"
            >
              <option value="">{t('hermesWorkspace.selectSession')}</option>
              {legacySessions.map((session) => (
                <option key={session.id} value={session.id}>
                  {session.title}
                </option>
              ))}
            </select>
            {legacyPath ? (
              <button
                type="button"
                onClick={() =>
                  setLegacyPath(legacyPath.split('/').slice(0, -1).join('/'))
                }
              >
                {t('hermesWorkspace.parentFolder')}
              </button>
            ) : null}
            <ul>
              {legacyFiles.map((file) => (
                <li key={file.relative_path}>
                  <button
                    type="button"
                    className="max-w-full truncate py-1 text-start"
                    onClick={() => {
                      if (file.kind === 'directory') {
                        setLegacyPath(file.relative_path);
                        return;
                      }
                      if (token)
                        void runAction(async () => {
                          const response = await downloadHermesTerminalFile(
                            token,
                            legacyId,
                            file.relative_path,
                          );
                          downloadBlobAsFile(response.blob, file.name);
                        });
                    }}
                  >
                    {file.name}
                  </button>
                </li>
              ))}
            </ul>
          </details>
        ) : null}
      </div>
    </details>
  );
}
