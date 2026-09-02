import { Badge, Button, EmptyState, useFeedback } from '@open-work-hub/ui';
import {
  Check,
  ChevronLeft,
  Download,
  File,
  Folder,
  RefreshCw,
  ShieldCheck,
  X,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  contentDispositionFilename,
  downloadBlobAsFile,
} from '@/src/platform/browser/browser-download';
import { formatByteSize } from '@/src/platform/format/byte-size';
import {
  decideHermesTerminalApproval,
  downloadHermesTerminalFile,
  listHermesTerminalApprovals,
  listHermesTerminalFiles,
  type HermesTerminalApproval,
  type HermesTerminalFileEntry,
  type HermesTerminalSession,
} from '../api/hermes-terminal-api';

type PanelTab = 'files' | 'approvals';

function approvalTone(
  status: HermesTerminalApproval['status'],
): 'neutral' | 'success' | 'warning' | 'danger' {
  if (status === 'approved') return 'success';
  if (status === 'pending') return 'warning';
  if (status === 'denied') return 'danger';
  return 'neutral';
}

export function HermesTerminalActivityPanel({
  session,
  token,
  workspaceSlug,
}: {
  session: HermesTerminalSession;
  token: string;
  workspaceSlug: string;
}) {
  const { t } = useTranslation('apps');
  const feedback = useFeedback();
  const [tab, setTab] = useState<PanelTab>('files');
  const [path, setPath] = useState('');
  const [files, setFiles] = useState<HermesTerminalFileEntry[]>([]);
  const [approvals, setApprovals] = useState<HermesTerminalApproval[]>([]);
  const [filesLoading, setFilesLoading] = useState(true);
  const [approvalsLoading, setApprovalsLoading] = useState(true);
  const [downloadingPath, setDownloadingPath] = useState<string | null>(null);
  const [decidingId, setDecidingId] = useState<string | null>(null);
  const requestIdRef = useRef(0);
  const loadRequestRef = useRef<{
    key: string;
    promise: Promise<void>;
  } | null>(null);
  const seenPendingIdsRef = useRef<Set<string>>(new Set());

  const load = useCallback(
    async (showLoading = false) => {
      const requestKey = `${session.id}:${path}`;
      if (loadRequestRef.current?.key === requestKey) {
        return loadRequestRef.current.promise;
      }
      const requestId = ++requestIdRef.current;
      if (showLoading) {
        setFilesLoading(true);
        setApprovalsLoading(true);
      }
      const request = Promise.allSettled([
        listHermesTerminalFiles(token, workspaceSlug, session.id, path),
        listHermesTerminalApprovals(token, workspaceSlug, session.id),
      ])
        .then(([filesResult, approvalsResult]) => {
          if (requestId !== requestIdRef.current) return;
          if (filesResult.status === 'fulfilled') {
            setFiles(filesResult.value.items ?? []);
          } else if (showLoading) {
            feedback.error(t('hermesTerminal.feedback.filesLoadFailed'));
          }
          if (approvalsResult.status === 'fulfilled') {
            const items = approvalsResult.value.items ?? [];
            setApprovals(items);
            const pendingIds = items
              .filter((item) => item.status === 'pending')
              .map((item) => item.id);
            if (pendingIds.some((id) => !seenPendingIdsRef.current.has(id))) {
              setTab('approvals');
            }
            seenPendingIdsRef.current = new Set(pendingIds);
          } else if (showLoading) {
            feedback.error(t('hermesTerminal.feedback.approvalsLoadFailed'));
          }
          setFilesLoading(false);
          setApprovalsLoading(false);
        })
        .finally(() => {
          if (loadRequestRef.current?.promise === request) {
            loadRequestRef.current = null;
          }
        });
      loadRequestRef.current = { key: requestKey, promise: request };
      return request;
    },
    [feedback, path, session.id, t, token, workspaceSlug],
  );

  useEffect(() => {
    setPath('');
    setFiles([]);
    setApprovals([]);
    seenPendingIdsRef.current = new Set();
  }, [session.id]);

  const hasPendingApproval = approvals.some(
    (approval) => approval.status === 'pending',
  );
  useEffect(() => {
    const active = [
      'starting',
      'running',
      'awaiting_approval',
      'stopping',
      'archiving',
    ].includes(session.status);
    if (!active && !hasPendingApproval) return;
    let cancelled = false;
    let timer: number | null = null;
    const poll = async () => {
      if (cancelled) return;
      if (document.visibilityState === 'visible') await load();
      if (!cancelled) {
        timer = window.setTimeout(
          () => void poll(),
          document.visibilityState === 'visible' ? 1500 : 10_000,
        );
      }
    };
    timer = window.setTimeout(() => void poll(), 1500);
    return () => {
      cancelled = true;
      if (timer !== null) window.clearTimeout(timer);
    };
  }, [hasPendingApproval, load, session.status]);

  useEffect(() => {
    void load(true);
  }, [load, session.status]);

  const parentPath = useMemo(() => {
    const parts = path.split('/').filter(Boolean);
    parts.pop();
    return parts.join('/');
  }, [path]);
  const pendingCount = approvals.filter(
    (approval) => approval.status === 'pending',
  ).length;

  const download = useCallback(
    async (entry: HermesTerminalFileEntry) => {
      if (entry.kind !== 'file') return;
      setDownloadingPath(entry.relative_path);
      try {
        const response = await downloadHermesTerminalFile(
          token,
          workspaceSlug,
          session.id,
          entry.relative_path,
        );
        downloadBlobAsFile(
          response.blob,
          contentDispositionFilename(response.contentDisposition, entry.name),
        );
        feedback.success(t('hermesTerminal.feedback.downloaded'));
      } catch {
        feedback.error(t('hermesTerminal.feedback.downloadFailed'));
      } finally {
        setDownloadingPath(null);
      }
    },
    [feedback, session.id, t, token, workspaceSlug],
  );

  const decide = useCallback(
    async (approval: HermesTerminalApproval, decision: 'approve' | 'deny') => {
      if (approval.status !== 'pending') return;
      setDecidingId(approval.id);
      try {
        await decideHermesTerminalApproval(
          token,
          workspaceSlug,
          session.id,
          approval.id,
          { decision },
        );
        feedback.success(
          t(
            decision === 'approve'
              ? 'hermesTerminal.feedback.approved'
              : 'hermesTerminal.feedback.denied',
          ),
        );
        await load();
      } catch {
        feedback.error(t('hermesTerminal.feedback.approvalFailed'));
      } finally {
        setDecidingId(null);
      }
    },
    [feedback, load, session.id, t, token, workspaceSlug],
  );

  return (
    <section
      aria-label={t('hermesTerminal.activity.label')}
      className="flex h-full min-h-0 flex-col bg-app-surface text-app-ink"
    >
      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-app-border px-2 py-2">
        <div className="flex min-w-0 items-center gap-1">
          <button
            aria-pressed={tab === 'files'}
            className={`rounded px-2 py-1.5 app-text-caption font-semibold ${
              tab === 'files'
                ? 'bg-app-accent/10 text-app-accent'
                : 'text-app-ink/55 hover:bg-app-surface-hover hover:text-app-ink'
            }`}
            onClick={() => setTab('files')}
            type="button"
          >
            {t('hermesTerminal.activity.files')} · {files.length}
          </button>
          <button
            aria-pressed={tab === 'approvals'}
            className={`rounded px-2 py-1.5 app-text-caption font-semibold ${
              tab === 'approvals'
                ? 'bg-app-accent/10 text-app-accent'
                : 'text-app-ink/55 hover:bg-app-surface-hover hover:text-app-ink'
            }`}
            onClick={() => setTab('approvals')}
            type="button"
          >
            {t('hermesTerminal.activity.approvals')}
            {pendingCount > 0 ? ` · ${pendingCount}` : ''}
          </button>
        </div>
        <Button
          aria-label={t('hermesTerminal.actions.refreshResults')}
          onClick={() => void load(true)}
          title={t('hermesTerminal.actions.refreshResults')}
          variant="subtle"
        >
          <RefreshCw aria-hidden="true" className="size-4" />
        </Button>
      </div>

      {tab === 'files' ? (
        <div className="flex min-h-0 flex-1 flex-col">
          <div className="flex shrink-0 items-center gap-2 border-b border-app-border px-2 py-1.5">
            <Button
              aria-label={t('hermesTerminal.actions.parentFolder')}
              disabled={!path}
              onClick={() => setPath(parentPath)}
              title={t('hermesTerminal.actions.parentFolder')}
              variant="subtle"
            >
              <ChevronLeft aria-hidden="true" className="size-4" />
            </Button>
            <span className="min-w-0 truncate font-mono app-text-caption text-app-ink/60">
              /workspace{path ? `/${path}` : ''}
            </span>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {filesLoading ? (
              <div className="flex items-center gap-2 px-3 py-8 app-text-caption text-app-ink/55">
                <RefreshCw aria-hidden="true" className="size-4 animate-spin" />
                {t('hermesTerminal.activity.loadingFiles')}
              </div>
            ) : files.length === 0 ? (
              <EmptyState
                title={t('hermesTerminal.activity.noFilesTitle')}
                description={t('hermesTerminal.activity.noFilesDescription')}
              />
            ) : (
              <ul className="divide-y divide-app-border">
                {files.map((entry) => (
                  <li
                    className="flex min-w-0 items-center gap-2 px-3 py-2"
                    key={entry.relative_path}
                  >
                    {entry.kind === 'directory' ? (
                      <Folder
                        aria-hidden="true"
                        className="size-4 shrink-0 text-app-accent"
                      />
                    ) : (
                      <File
                        aria-hidden="true"
                        className="size-4 shrink-0 text-app-ink/45"
                      />
                    )}
                    <button
                      className="min-w-0 flex-1 truncate text-left app-text-body hover:text-app-accent"
                      onClick={() =>
                        entry.kind === 'directory'
                          ? setPath(entry.relative_path)
                          : void download(entry)
                      }
                      type="button"
                    >
                      {entry.name}
                    </button>
                    {entry.kind === 'file' ? (
                      <>
                        <span className="shrink-0 app-text-caption text-app-ink/45">
                          {formatByteSize(entry.size_bytes ?? 0)}
                        </span>
                        <button
                          aria-label={t('hermesTerminal.actions.downloadFile', {
                            name: entry.name,
                          })}
                          className="rounded p-1.5 text-app-ink/55 hover:bg-app-surface-hover hover:text-app-accent disabled:opacity-50"
                          disabled={downloadingPath === entry.relative_path}
                          onClick={() => void download(entry)}
                          title={t('hermesTerminal.actions.download')}
                          type="button"
                        >
                          {downloadingPath === entry.relative_path ? (
                            <RefreshCw
                              aria-hidden="true"
                              className="size-4 animate-spin"
                            />
                          ) : (
                            <Download aria-hidden="true" className="size-4" />
                          )}
                        </button>
                      </>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto">
          {approvalsLoading ? (
            <div className="flex items-center gap-2 px-3 py-8 app-text-caption text-app-ink/55">
              <RefreshCw aria-hidden="true" className="size-4 animate-spin" />
              {t('hermesTerminal.activity.loadingApprovals')}
            </div>
          ) : approvals.length === 0 ? (
            <EmptyState
              title={t('hermesTerminal.activity.noApprovalsTitle')}
              description={t('hermesTerminal.activity.noApprovalsDescription')}
            />
          ) : (
            <ul className="divide-y divide-app-border">
              {approvals.map((approval) => (
                <li className="space-y-2 px-3 py-3" key={approval.id}>
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5">
                        <ShieldCheck
                          aria-hidden="true"
                          className="size-4 shrink-0 text-app-accent"
                        />
                        <span className="truncate font-mono app-text-label">
                          {approval.tool_name}
                        </span>
                      </div>
                      <p className="mt-0.5 app-text-caption text-app-ink/50">
                        {t('hermesTerminal.activity.oneTimeApproval')}
                      </p>
                    </div>
                    <Badge tone={approvalTone(approval.status)}>
                      {t(`hermesTerminal.approvalStatus.${approval.status}`)}
                    </Badge>
                  </div>
                  <pre className="max-h-44 overflow-auto rounded bg-app-bg p-2 font-mono app-text-caption text-app-ink/70">
                    {JSON.stringify(approval.arguments, null, 2)}
                  </pre>
                  {approval.status === 'pending' ? (
                    <div className="flex justify-end gap-2">
                      <Button
                        disabled={decidingId !== null}
                        onClick={() => void decide(approval, 'deny')}
                        variant="secondary"
                      >
                        <X aria-hidden="true" className="size-4" />
                        {t('hermesTerminal.actions.deny')}
                      </Button>
                      <Button
                        disabled={decidingId !== null}
                        onClick={() => void decide(approval, 'approve')}
                        variant="primary"
                      >
                        {decidingId === approval.id ? (
                          <RefreshCw
                            aria-hidden="true"
                            className="size-4 animate-spin"
                          />
                        ) : (
                          <Check aria-hidden="true" className="size-4" />
                        )}
                        {t('hermesTerminal.actions.approveOnce')}
                      </Button>
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
