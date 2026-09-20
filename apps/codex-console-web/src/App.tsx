import { Button, Dialog, Input } from '@open-work-hub/ui';
import {
  ArrowUp,
  CircleStop,
  Code2,
  History,
  ListTodo,
  LogOut,
  Menu,
  Paperclip,
  Plus,
  RefreshCw,
  Search,
  X,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  active,
  api,
  apiBasePath,
  ApiError,
  locked,
  record,
  uploadAttachment,
  type Account,
  type Model,
  type Attachment,
  type Detail,
  type DeviceLogin,
  type Revision,
  type Task,
  type Thread,
  type ThreadPage,
} from './api';
import {
  errorCopy,
  statusCopy,
  translate,
  type Copy,
  type Locale,
} from './i18n';
import {
  Command,
  Confirm,
  Documents,
  MessageItem,
  RequestForm,
  type DocumentDraft,
} from './views';
import { AttachmentBadges, FileLibrary } from './attachments';
import { GitWorkspace, GitSummary, useGitState } from './git';
import {
  ExecutionSettings,
  ExecutionStatus,
  resolveExecution,
  type Execution,
} from './execution';

type Tab = 'requirements' | 'plan' | 'branch' | 'checks' | 'files';
const tabs: { id: Tab; label: Copy }[] = [
  { id: 'requirements', label: 'Requirements' },
  { id: 'plan', label: 'Plan' },
  { id: 'branch', label: 'Branch' },
  { id: 'checks', label: 'Execution results' },
  { id: 'files', label: 'Files' },
];

export function App() {
  const [locale, setLocale] = useState<Locale>('ko-KR');
  const t = useMemo(() => translate(locale), [locale]);
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);
  const [sessionFailed, setSessionFailed] = useState(false);
  const [password, setPassword] = useState('');
  const [tasks, setTasks] = useState<Task[]>([]);
  const [task, setTask] = useState<Detail | null>(null);
  const [documentDrafts, setDocumentDrafts] = useState<
    Record<string, DocumentDraft>
  >({});
  const [selected, setSelected] = useState<string | null>(() => {
    const id = new URLSearchParams(window.location.search).get('task');
    return id && /^[0-9a-f-]{36}$/.test(id) ? id : null;
  });
  const selectedRef = useRef(selected);
  selectedRef.current = selected;
  const [account, setAccount] = useState<Account | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [tab, setTab] = useState<Tab>('requirements');
  const [mobileView, setMobileView] = useState<'conversation' | 'results'>(
    'conversation',
  );
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [history, setHistory] = useState<Thread[]>([]);
  const [historyCursor, setHistoryCursor] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const searchRef = useRef(search);
  searchRef.current = search;
  const [historySearch, setHistorySearch] = useState('');
  const [importThread, setImportThread] = useState<Thread | null>(null);
  const [confirmInactive, setConfirmInactive] = useState(false);
  const [newOpen, setNewOpen] = useState(false);
  const [title, setTitle] = useState('');
  const [message, setMessage] = useState('');
  const [stage, setStage] = useState<'plan' | 'implement'>('plan');
  const git = useGitState(task);
  const [models, setModels] = useState<Model[]>([]);
  const [modelsFailed, setModelsFailed] = useState(false);
  const [execution, setExecution] = useState<Execution>({
    model: null,
    effort: null,
    permissions: 'ask',
  });
  const selectedExecution = useMemo(
    () => resolveExecution(execution, models),
    [execution, models],
  );
  const [approvalExecution, setApprovalExecution] =
    useState<Execution>(execution);
  const [approvalText, setApprovalText] = useState('');
  const initializedTask = useRef<string | null>(null);
  const [planToApprove, setPlanToApprove] = useState<Revision | null>(null);
  const [attachmentIds, setAttachmentIds] = useState<string[]>([]);
  const [attachmentPicker, setAttachmentPicker] = useState(false);
  const [approvalFiles, setApprovalFiles] = useState<Attachment[]>([]);
  const [fileToDelete, setFileToDelete] = useState<Attachment | null>(null);
  const uploadAbort = useRef<AbortController | null>(null);
  const uploadIds = useRef(new WeakMap<File, string>());
  const [uploads, setUploads] = useState<
    { file: File; progress: number; failed: boolean; select: boolean }[]
  >([]);
  const [connected, setConnected] = useState(false);
  const [device, setDevice] = useState<DeviceLogin | null>(null);
  const [usageOpen, setUsageOpen] = useState(false);
  const requestKeys = useRef(new Map<string, string>());
  const chatEnd = useRef<HTMLDivElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const nearBottom = useRef(true);

  const onError = useCallback((value: unknown) => {
    const code = value instanceof ApiError ? value.code : 'request_failed';
    setError(code);
    if (code === 'unauthenticated') {
      setAuthenticated(false);
      setTask(null);
      setTasks([]);
    }
  }, []);
  const checkSession = useCallback(async () => {
    setSessionFailed(false);
    setError(null);
    try {
      const value = await api<{ authenticated: boolean }>('/session');
      setAuthenticated(value.authenticated);
    } catch (error) {
      setSessionFailed(true);
      onError(error);
    }
  }, [onError]);
  const refreshTasks = useCallback(async () => {
    const query = searchRef.current.trim();
    const rows = await api<Task[]>(
      query ? `/tasks?search=${encodeURIComponent(query)}` : '/tasks',
    );
    if (searchRef.current.trim() === query) setTasks(rows);
  }, []);
  const refreshAccount = useCallback(async () => {
    const value = await api<Account>('/codex/account');
    setAccount(value);
    if (value.auth_type === 'chatgpt') setDevice(null);
  }, []);
  const refreshModels = useCallback(async () => {
    setModelsFailed(false);
    try {
      setModels(await api<Model[]>('/codex/models'));
    } catch {
      setModelsFailed(true);
    }
  }, []);
  const refreshTask = useCallback(async (id: string, signal?: AbortSignal) => {
    const detail = await api<Detail>(
      `/tasks/${id}`,
      undefined,
      undefined,
      signal,
    );
    if (selectedRef.current === id)
      setTask((current) =>
        current?.id === id && current.event_id > detail.event_id
          ? current
          : detail,
      );
  }, []);
  const act = useCallback(
    async (operation: () => Promise<void>) => {
      if (busyRef.current) return false;
      busyRef.current = true;
      setBusy(true);
      setError(null);
      try {
        await operation();
        return true;
      } catch (err) {
        onError(err);
        return false;
      } finally {
        busyRef.current = false;
        setBusy(false);
      }
    },
    [onError],
  );
  const mutate = useCallback(
    async (suffix: string, body: unknown, method?: string) => {
      const id = selectedRef.current;
      if (!id) return false;
      return act(async () => {
        await api(`/tasks/${id}/${suffix}`, body, method);
        if (suffix === 'recover') {
          // Only explicit, successful recovery permits a fresh submission. Keep
          // other tasks' retry identities and never replay an uncertain request.
          for (const key of requestKeys.current.keys()) {
            if (JSON.parse(key)[0] === id) requestKeys.current.delete(key);
          }
        }
        await refreshTask(id);
        await refreshTasks();
      });
    },
    [act, refreshTask, refreshTasks],
  );
  const send = useCallback(
    async (suffix: string, data: Record<string, unknown>) => {
      const taskId = selectedRef.current;
      if (!taskId) return false;
      const payload = { attachment_ids: attachmentIds, ...data };
      const key = JSON.stringify([taskId, suffix, payload]);
      const id = requestKeys.current.get(key) ?? crypto.randomUUID();
      requestKeys.current.set(key, id);
      const ok = await act(async () => {
        const detail = await api<Detail>(`/tasks/${taskId}/${suffix}`, {
          ...payload,
          operation_id: id,
        });
        requestKeys.current.delete(key);
        if (selectedRef.current === taskId) {
          setTask((current) =>
            current?.id === taskId && current.event_id > detail.event_id
              ? current
              : detail,
          );
          setAttachmentIds([]);
        }
        await refreshTasks().catch(onError);
      });
      return ok;
    },
    [act, attachmentIds, refreshTasks, onError],
  );

  const approveImplementation = (revision: Revision, text = '') => {
    if (!task) return;
    setApprovalFiles(
      task.attachments.filter((file) => attachmentIds.includes(file.id)),
    );
    setApprovalExecution(selectedExecution);
    setApprovalText(text);
    setPlanToApprove(revision);
  };

  const toggleAttachment = (id: string) => {
    if (attachmentIds.includes(id))
      setAttachmentIds((ids) => ids.filter((value) => value !== id));
    else if (attachmentIds.length < (task?.attachment_limits.selection ?? 20))
      setAttachmentIds((ids) => [...ids, id]);
    else setError('attachment_selection_limit');
  };
  const uploadFiles = async (files: File[], select: boolean) => {
    const taskId = selectedRef.current;
    if (!taskId || !files.length) return;
    await act(async () => {
      const controller = new AbortController();
      uploadAbort.current = controller;
      try {
        for (const file of files) {
          if (controller.signal.aborted || selectedRef.current !== taskId)
            break;
          const id = uploadIds.current.get(file) ?? crypto.randomUUID();
          uploadIds.current.set(file, id);
          setUploads((rows) => [
            ...rows.filter((row) => row.file !== file),
            { file, progress: 0, failed: false, select },
          ]);
          try {
            if (file.size > (task?.attachment_limits.file_bytes ?? 0))
              throw new ApiError('attachment_too_large');
            const result = await uploadAttachment(
              taskId,
              id,
              file,
              controller.signal,
              (progress) => {
                if (selectedRef.current === taskId)
                  setUploads((rows) =>
                    rows.map((row) =>
                      row.file === file ? { ...row, progress } : row,
                    ),
                  );
              },
            );
            if (selectedRef.current !== taskId) break;
            setUploads((rows) => rows.filter((row) => row.file !== file));
            if (select)
              setAttachmentIds((ids) =>
                ids.includes(result.id) ||
                ids.length >= (task?.attachment_limits.selection ?? 20)
                  ? ids
                  : [...ids, result.id],
              );
            await refreshTask(taskId);
          } catch (error) {
            if (selectedRef.current !== taskId) break;
            setUploads((rows) =>
              rows.map((row) =>
                row.file === file ? { ...row, failed: true } : row,
              ),
            );
            onError(
              controller.signal.aborted
                ? new ApiError('attachment_upload_cancelled')
                : error,
            );
          }
        }
      } finally {
        if (uploadAbort.current === controller) uploadAbort.current = null;
      }
    });
  };

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);
  useEffect(() => {
    if (
      !Object.values(documentDrafts).some(
        (draft) => draft.body !== (draft.base?.body ?? ''),
      )
    )
      return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [documentDrafts]);
  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const update = () =>
      document.documentElement.classList.toggle('dark', media.matches);
    update();
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);
  useEffect(() => {
    void checkSession();
  }, [checkSession]);
  useEffect(() => {
    if (!authenticated) return;
    void refreshAccount().catch(onError);
    void refreshModels();
    const timer = window.setInterval(
      () => void refreshAccount().catch(onError),
      30000,
    );
    return () => window.clearInterval(timer);
  }, [authenticated, refreshTasks, refreshAccount, refreshModels, onError]);
  useEffect(() => {
    if (!authenticated) return;
    const timer = window.setTimeout(
      () => void refreshTasks().catch(onError),
      200,
    );
    return () => window.clearTimeout(timer);
  }, [search, authenticated, refreshTasks, onError]);
  useEffect(() => {
    initializedTask.current = null;
    setTask(null);
    setMessage('');
    uploadAbort.current?.abort();
    setUploads([]);
    setAttachmentIds([]);
    setAttachmentPicker(false);
    setFileToDelete(null);
    setApprovalFiles([]);
    setConnected(false);
    setPlanToApprove(null);
    nearBottom.current = true;
    if (!selected || !authenticated) return;
    const controller = new AbortController();
    void refreshTask(selected, controller.signal).catch((err) => {
      if (!controller.signal.aborted) onError(err);
    });
    const stream = new EventSource(`${apiBasePath}/tasks/${selected}/events`);
    const refresh = () => {
      void refreshTask(selected, controller.signal).catch((err) => {
        if (!controller.signal.aborted) onError(err);
      });
      void refreshTasks().catch(onError);
    };
    const fallback = window.setInterval(refresh, 10000);
    const visible = () => {
      if (document.visibilityState === 'visible') refresh();
    };
    document.addEventListener('visibilitychange', visible);
    stream.addEventListener('changed', refresh);
    stream.addEventListener('open', () => {
      setConnected(true);
      refresh();
    });
    stream.addEventListener('error', () => setConnected(false));
    stream.addEventListener('expired', () => {
      stream.close();
      setAuthenticated(false);
      setTask(null);
    });
    return () => {
      window.clearInterval(fallback);
      document.removeEventListener('visibilitychange', visible);
      controller.abort();
      uploadAbort.current?.abort();
      stream.close();
    };
  }, [selected, authenticated, refreshTask, refreshTasks, onError]);
  useEffect(() => {
    if (nearBottom.current) chatEnd.current?.scrollIntoView({ block: 'end' });
  }, [task?.event_id]);

  useEffect(() => {
    if (!task || initializedTask.current === task.id) return;
    initializedTask.current = task.id;
    setStage(
      task.stage === 'review' || task.stage === 'implement'
        ? 'implement'
        : 'plan',
    );
    setExecution({
      model: task.model ?? null,
      effort: task.effort ?? null,
      permissions: task.permissions === 'yolo' ? 'yolo' : 'ask',
    });
  }, [task]);

  const loadHistory = async (cursor: string | null = null) => {
    await act(async () => {
      const result = await api<ThreadPage>(
        `/codex/threads?search=${encodeURIComponent(historySearch)}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`,
      );
      setHistory((rows) =>
        cursor ? [...rows, ...result.items] : result.items,
      );
      setHistoryCursor(result.cursor ?? null);
    });
  };
  const choose = (id: string) => {
    window.history.replaceState(null, '', `?task=${encodeURIComponent(id)}`);
    setSelected(id);
    setSidebarOpen(false);
    setError(null);
    setMobileView('conversation');
  };
  const uploadStatus = uploads.map((upload, index) => (
    <div className="upload-status" key={index} role="status">
      <span>{upload.file.name}</span>
      {upload.failed ? (
        <Button
          variant="ghost"
          disabled={busy}
          onClick={() => void uploadFiles([upload.file], upload.select)}
        >
          {t('Retry upload')}
        </Button>
      ) : (
        <>
          <progress
            max={100}
            value={upload.progress}
            aria-label={t('Uploading')}
          />
          <Button variant="ghost" onClick={() => uploadAbort.current?.abort()}>
            {t('Cancel upload')}
          </Button>
        </>
      )}
    </div>
  ));
  const language = (
    <select
      className="language"
      aria-label="Language / 언어"
      value={locale}
      onChange={(event) => setLocale(event.target.value as Locale)}
    >
      <option value="ko-KR">한국어</option>
      <option value="en-US">English</option>
    </select>
  );
  const feedback = error && (
    <div className="feedback" role="alert">
      <span>{t(errorCopy(error))}</span>
      <Button
        size="icon"
        variant="ghost"
        aria-label={t('Close')}
        onClick={() => setError(null)}
      >
        <X size={16} />
      </Button>
    </div>
  );
  const taskIsActive = active(task);
  const composerImplementation = task
    ? taskIsActive
      ? task.stage === 'implement'
      : stage === 'implement'
    : false;
  const composerYolo = task
    ? composerImplementation &&
      (taskIsActive
        ? task.permissions === 'yolo'
        : execution.permissions === 'yolo')
    : false;
  const composerPlanningHelp = !!task && stage === 'plan' && !taskIsActive;

  if (!authenticated)
    return (
      <div className="login-page">
        <div className="login-language">{language}</div>
        <main className="login-form">
          <div className="brand-mark">
            <Code2 size={24} />
          </div>
          <p className="eyebrow">CODEX CONSOLE</p>
          <h1>{t('Your private development workspace')}</h1>
          <p className="login-description">
            {t(
              'Use your existing Codex subscription to turn an idea into a reviewed change.',
            )}
          </p>
          {sessionFailed && (
            <Button onClick={() => void checkSession()}>
              {t('Retry connection')}
            </Button>
          )}
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void act(async () => {
                const result = await api<{ authenticated: boolean }>(
                  '/session',
                  { password },
                );
                setPassword('');
                setAuthenticated(result.authenticated);
              });
            }}
          >
            <label htmlFor="password">{t('Owner password')}</label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              maxLength={1024}
            />
            <Button
              variant="primary"
              type="submit"
              disabled={busy || authenticated === null}
              fullWidth
            >
              {t('Sign in')}
            </Button>
          </form>
          <small>
            {t(
              'This password protects the console. Your ChatGPT login stays with Codex.',
            )}
          </small>
        </main>
        {feedback}
      </div>
    );

  return (
    <div className="console-shell" data-mobile-view={mobileView}>
      <header className="topbar">
        <Button
          className="mobile-only"
          size="icon"
          variant="ghost"
          aria-label={t('Open tasks')}
          onClick={() => setSidebarOpen(true)}
        >
          <Menu size={18} />
        </Button>
        <div className="brand">
          <Code2 size={21} />
          <strong>{t('Codex workspace')}</strong>
        </div>
        <div className="topbar-actions">
          <button className="account-badge" onClick={() => setUsageOpen(true)}>
            <span
              className={`dot ${account?.auth_type === 'chatgpt' ? 'online' : ''}`}
            />
            {t(
              account?.auth_type === 'chatgpt'
                ? 'Subscription connected'
                : 'Codex unavailable',
            )}
          </button>
          {language}
          <Button
            variant="ghost"
            size="icon"
            aria-label={t('Sign out')}
            onClick={() =>
              void act(async () => {
                await api('/session', undefined, 'DELETE');
                setAuthenticated(false);
                setTask(null);
                setSelected(null);
                setTasks([]);
                setDocumentDrafts({});
              })
            }
          >
            <LogOut size={16} />
          </Button>
        </div>
      </header>
      {sidebarOpen && (
        <button
          className="sidebar-backdrop"
          aria-label={t('Close')}
          onClick={() => setSidebarOpen(false)}
        />
      )}
      <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
        <Button variant="primary" onClick={() => setNewOpen(true)} fullWidth>
          <Plus size={16} />
          {t('New task')}
        </Button>
        <div className="sidebar-tabs">
          <button
            aria-pressed={!showHistory}
            onClick={() => setShowHistory(false)}
          >
            <ListTodo size={15} />
            {t('Tasks')}
          </button>
          <button
            aria-pressed={showHistory}
            onClick={() => {
              setShowHistory(true);
              void loadHistory();
            }}
          >
            <History size={15} />
            {t('History')}
          </button>
        </div>
        {showHistory ? (
          <>
            <form
              className="search"
              onSubmit={(event) => {
                event.preventDefault();
                void loadHistory();
              }}
            >
              <Input
                aria-label={t('Search Codex history')}
                placeholder={t('Search Codex history')}
                value={historySearch}
                onChange={(event) => setHistorySearch(event.target.value)}
              />
              <Button
                type="submit"
                variant="ghost"
                size="icon"
                aria-label={t('Search Codex history')}
              >
                <Search size={15} />
              </Button>
            </form>
            <div className="task-list">
              {history.map((row) => (
                <button
                  key={row.id}
                  className="task-row"
                  onClick={() => {
                    setImportThread(row);
                    setConfirmInactive(false);
                  }}
                >
                  <strong>{row.title}</strong>
                  <small>
                    {new Date(row.updated_at * 1000).toLocaleDateString(locale)}
                  </small>
                </button>
              ))}
            </div>
            {historyCursor && (
              <Button
                disabled={busy}
                onClick={() => void loadHistory(historyCursor)}
              >
                {t('Load more')}
              </Button>
            )}
          </>
        ) : (
          <>
            <Input
              aria-label={t('Search tasks')}
              placeholder={t('Search tasks')}
              value={search}
              maxLength={200}
              onChange={(event) => setSearch(event.target.value)}
            />
            <nav className="task-list" aria-label={t('Tasks')}>
              {tasks.map((row) => (
                <button
                  className={`task-row ${selected === row.id ? 'selected' : ''}`}
                  key={row.id}
                  aria-current={selected === row.id ? 'page' : undefined}
                  onClick={() => choose(row.id)}
                >
                  <strong>{row.title}</strong>
                  <small>
                    <span
                      className={`dot ${active(row) ? 'online pulse' : ''}`}
                    />
                    {t(statusCopy(row.status))}
                  </small>
                </button>
              ))}
              {!tasks.length && (
                <p className="muted sidebar-empty">{t('No tasks yet')}</p>
              )}
            </nav>
          </>
        )}
        <footer className="sidebar-footer">
          <span className="muted">Codex · ChatGPT</span>
          <Button
            variant="ghost"
            size="icon"
            aria-label={t('Refresh')}
            onClick={() =>
              void act(async () => {
                await refreshTasks();
                await refreshAccount();
                if (selected) await refreshTask(selected);
              })
            }
          >
            <RefreshCw size={14} />
          </Button>
        </footer>
      </aside>
      {!task ? (
        <main className="welcome">
          <div className="brand-mark">
            <Code2 size={28} />
          </div>
          <h1>{t('Start with what you want to change.')}</h1>
          <p>
            {t(
              'Describe a feature or a problem. Codex will inspect the repository and help define the requirements.',
            )}
          </p>
          <Button
            variant="primary"
            disabled={!!selected}
            onClick={() => setNewOpen(true)}
          >
            <Plus size={16} />
            {t('New task')}
          </Button>
        </main>
      ) : (
        <main className="workspace">
          <div className="task-header">
            <div>
              <h1>{task.title}</h1>
              <div className="task-meta">
                <span>{t(statusCopy(task.status))}</span>
                <span>·</span>
                <span title={task.root}>
                  {task.root.split('/').at(-1)}
                  {task.isolated && ` · ${t('Isolated checkout')}`}
                </span>
                <span className="connection">
                  <span className={`dot ${connected ? 'online' : ''}`} />
                  {t(connected ? 'Connected' : 'Reconnecting')}
                </span>
              </div>
              <GitSummary state={git.state} t={t} />
            </div>
            {(task.error_code || task.status === 'uncertain') && (
              <div className="runtime-notice" role="status">
                {t(errorCopy(task.error_code ?? 'codex_request_uncertain'))}
                {(task.status === 'uncertain' ||
                  task.error_code === 'codex_request_uncertain' ||
                  task.error_code === 'workspace_changed') && (
                  <>
                    <small>
                      {t('No request will be automatically replayed.')}
                    </small>
                    <Button
                      disabled={busy}
                      onClick={() => {
                        const confirmWorkspace =
                          task.stage === 'implement' || task.stage === 'review';
                        if (
                          confirmWorkspace &&
                          !window.confirm(
                            t(
                              'Review the current diff first. Keep these changes in this task and continue in the same workspace?',
                            ),
                          )
                        )
                          return;
                        void mutate('recover', {
                          confirm_workspace: confirmWorkspace,
                        });
                      }}
                    >
                      {t('Recover state')}
                    </Button>
                  </>
                )}
              </div>
            )}
          </div>
          <div className="mobile-tabs">
            <button
              aria-pressed={mobileView === 'conversation'}
              onClick={() => setMobileView('conversation')}
            >
              {t('Conversation')}
            </button>
            <button
              aria-pressed={mobileView === 'results'}
              onClick={() => setMobileView('results')}
            >
              {t('Results')}
            </button>
          </div>
          <section className="conversation" aria-label={t('Conversation')}>
            <ExecutionStatus task={task} connected={connected} t={t} />
            <div
              className="messages"
              ref={scroller}
              tabIndex={0}
              onScroll={() => {
                const element = scroller.current;
                if (element)
                  nearBottom.current =
                    element.scrollHeight -
                      element.scrollTop -
                      element.clientHeight <
                    120;
              }}
            >
              {!task.items.length && (
                <div className="conversation-empty">
                  <Code2 size={26} />
                  <h2>{t('Start with what you want to change.')}</h2>
                  <p>
                    {t(
                      'Describe a feature or a problem. Codex will inspect the repository and help define the requirements.',
                    )}
                  </p>
                </div>
              )}
              {task.history_truncated && (
                <p className="muted">
                  {t(
                    'Showing the latest 2,000 items. The full conversation remains in Codex.',
                  )}
                </p>
              )}
              {task.items.map((item, i) => (
                <MessageItem
                  key={typeof item.id === 'string' ? item.id : i}
                  item={item}
                  t={t}
                  taskId={task.id}
                />
              ))}
              {task.requests.map((request) => (
                <RequestForm
                  key={request.id}
                  request={request}
                  t={t}
                  disabled={busy}
                  onAnswer={(id, response) =>
                    void mutate(`requests/${id}`, response)
                  }
                />
              ))}
              <div ref={chatEnd} />
            </div>
            <form
              className="composer"
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => {
                event.preventDefault();
                if (!busy && task.status !== 'uncertain')
                  void uploadFiles(Array.from(event.dataTransfer.files), true);
              }}
              onSubmit={(event) => {
                event.preventDefault();
                void send(
                  active(task)
                    ? 'steer'
                    : stage === 'implement'
                      ? 'implement'
                      : 'messages',
                  {
                    text: message,
                    ...(active(task)
                      ? {}
                      : {
                          ...selectedExecution,
                          ...(stage === 'plan' ? { stage } : {}),
                        }),
                  },
                ).then((ok) => {
                  if (ok && selectedRef.current === task.id)
                    setMessage((current) =>
                      current === message ? '' : current,
                    );
                });
              }}
            >
              {task.failed_request_text && !message && (
                <Button
                  variant="ghost"
                  type="button"
                  onClick={() => setMessage(task.failed_request_text ?? '')}
                >
                  {t('Restore unsent request')}
                </Button>
              )}
              {attachmentIds.length > 0 && (
                <AttachmentBadges
                  files={task.attachments.filter((file) =>
                    attachmentIds.includes(file.id),
                  )}
                  taskId={task.id}
                  t={t}
                  disabled={busy}
                  onRemove={(id) =>
                    setAttachmentIds((ids) =>
                      ids.filter((value) => value !== id),
                    )
                  }
                />
              )}
              {uploadStatus}
              <textarea
                aria-label={t('Describe your request')}
                placeholder={t('Describe your request')}
                value={message}
                onChange={(event) => setMessage(event.target.value)}
                rows={3}
                maxLength={32000}
                onKeyDown={(event) => {
                  if (
                    event.key === 'Enter' &&
                    (event.metaKey || event.ctrlKey) &&
                    !event.nativeEvent.isComposing
                  )
                    event.currentTarget.form?.requestSubmit();
                }}
              />
              <div className="composer-toolbar">
                <div className="composer-controls">
                  <label className="mode-selector">
                    <span className="sr-only">{t('Execution mode')}</span>
                    <select
                      aria-label={t('Execution mode')}
                      disabled={busy || locked(task)}
                      value={
                        active(task)
                          ? task.stage === 'implement'
                            ? 'implement'
                            : 'plan'
                          : stage
                      }
                      onChange={(event) => {
                        setStage(event.target.value as typeof stage);
                      }}
                    >
                      <option value="plan">{t('Plan')}</option>
                      <option value="implement">{t('Execute')}</option>
                    </select>
                  </label>
                  <ExecutionSettings
                    models={models}
                    value={
                      active(task)
                        ? {
                            model: task.model ?? null,
                            effort: task.effort ?? null,
                            permissions:
                              task.permissions === 'yolo' ? 'yolo' : 'ask',
                          }
                        : selectedExecution
                    }
                    onChange={setExecution}
                    disabled={busy || locked(task)}
                    implementation={
                      active(task)
                        ? task.stage === 'implement'
                        : stage === 'implement'
                    }
                    failed={modelsFailed}
                    onRetry={() => void refreshModels()}
                    t={t}
                  />
                </div>
                <div className="actions">
                  <Button
                    variant="ghost"
                    size="icon"
                    disabled={busy || task.status === 'uncertain'}
                    aria-label={t('Attach files')}
                    onClick={() => setAttachmentPicker(true)}
                  >
                    <Paperclip size={17} />
                  </Button>
                  {(active(task) ||
                    (task.status === 'uncertain' && task.thread_id)) && (
                    <Button
                      variant="ghost"
                      disabled={busy}
                      onClick={() => void mutate('interrupt', {})}
                    >
                      <CircleStop size={15} />
                      {t('Stop')}
                    </Button>
                  )}
                  <Button
                    type="submit"
                    variant="primary"
                    disabled={
                      busy ||
                      (!message.trim() &&
                        (stage === 'implement' || !attachmentIds.length)) ||
                      task.status === 'starting'
                    }
                    aria-label={t(active(task) ? 'Add instruction' : 'Send')}
                  >
                    <ArrowUp size={17} />
                    {t(active(task) ? 'Add instruction' : 'Send')}
                  </Button>
                </div>
              </div>
              <p
                className={`composer-help ${
                  composerYolo
                    ? 'danger'
                    : composerPlanningHelp
                      ? ''
                      : 'layout-placeholder'
                }`}
                aria-hidden={!(composerYolo || composerPlanningHelp)}
              >
                {t(
                  composerYolo
                    ? 'YOLO runs commands without approval or sandbox restrictions.'
                    : 'Planning is read-only. Documents are updated only when requested or when agreed changes affect an existing document.',
                )}
              </p>
            </form>
          </section>
          <aside className="results" aria-label={t('Results')}>
            <nav className="result-tabs" aria-label={t('Results')}>
              {tabs.map((entry) => (
                <button
                  key={entry.id}
                  aria-pressed={tab === entry.id}
                  onClick={() => setTab(entry.id)}
                >
                  {t(entry.label)}
                </button>
              ))}
            </nav>
            {(tab === 'requirements' || tab === 'plan') && (
              <Documents
                key={`${task.id}-${tab}`}
                task={task}
                kind={tab}
                draft={documentDrafts[`${task.id}:${tab}`] ?? null}
                onDraftChange={(next) => {
                  const key = `${task.id}:${tab}`;
                  setDocumentDrafts((current) => {
                    const draft =
                      typeof next === 'function'
                        ? next(current[key] ?? null)
                        : next;
                    const result = { ...current };
                    if (draft) result[key] = draft;
                    else delete result[key];
                    return result;
                  });
                }}
                t={t}
                busy={busy}
                onSave={(body) => mutate('documents', body, 'PUT')}
                onPlan={() => {
                  setStage('plan');
                  setTab('plan');
                  void send('messages', {
                    ...selectedExecution,
                    stage: 'plan',
                    text: t(
                      'Create an execution plan from the requirements, including acceptance checks.',
                    ),
                  });
                }}
                onImplement={(revision) => {
                  setStage('implement');
                  approveImplementation(revision);
                }}
              />
            )}
            {tab === 'files' && uploadStatus}
            {tab === 'files' && (
              <FileLibrary
                task={task}
                selectedIds={attachmentIds}
                t={t}
                busy={busy}
                onToggle={toggleAttachment}
                onUpload={(files, select) => void uploadFiles(files, select)}
                onDelete={(id) =>
                  setFileToDelete(
                    task.attachments.find((file) => file.id === id) ?? null,
                  )
                }
              />
            )}
            {tab === 'branch' && (
              <GitWorkspace
                task={task}
                git={git}
                locale={locale}
                t={t}
                onError={onError}
              />
            )}
            {tab === 'checks' && (
              <div className="checks-pane">
                <p className="muted">
                  {t(
                    'Command results are execution evidence. Read the final response for tests run and checks skipped.',
                  )}
                </p>
                {task.items
                  .filter((item) => item.type === 'commandExecution')
                  .map((item, index) => (
                    <Command key={index} item={item} t={t} />
                  ))}
                {!task.items.some(
                  (item) => item.type === 'commandExecution',
                ) && (
                  <p className="empty-result">
                    {t('No commands have run yet.')}
                  </p>
                )}
              </div>
            )}
          </aside>
        </main>
      )}
      <Dialog
        open={newOpen}
        onOpenChange={setNewOpen}
        title={t('New task')}
        closeLabel={t('Close')}
      >
        <form
          className="stack"
          onSubmit={(event) => {
            event.preventDefault();
            void act(async () => {
              const next = await api<Detail>('/tasks', { title });
              await refreshTasks();
              choose(next.id);
              setNewOpen(false);
              setTitle('');
            });
          }}
        >
          <label htmlFor="task-title">{t('Task title')}</label>
          <Input
            id="task-title"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            required
            maxLength={200}
            autoFocus
          />
          <Button
            variant="primary"
            type="submit"
            disabled={busy || !title.trim()}
          >
            {t('Create task')}
          </Button>
        </form>
      </Dialog>
      <Confirm
        open={!!planToApprove}
        title="Execute the saved plan?"
        description="Codex may edit this checkout and run checks. The approved plan does not authorize publishing or deployment."
        action="Execute this plan"
        t={t}
        busy={busy}
        onClose={() => {
          setPlanToApprove(null);
        }}
        onConfirm={() => {
          if (planToApprove)
            void (async () => {
              return send('implement', {
                ...approvalExecution,
                text: approvalText,
                revision_id: planToApprove.id,
                attachment_ids: approvalFiles.map((file) => file.id),
              });
            })().then((ok) => {
              if (ok) {
                setPlanToApprove(null);
                setMessage((current) =>
                  current === approvalText ? '' : current,
                );
                setTab('branch');
              }
            });
        }}
      >
        {error && (
          <p role="alert" className="danger">
            {t(errorCopy(error))}
          </p>
        )}
        <p>
          {approvalExecution.model ?? t('Loading model catalog…')}
          {approvalExecution.effort
            ? ` · ${approvalExecution.effort}`
            : ''} ·{' '}
          {t(
            approvalExecution.permissions === 'yolo'
              ? 'YOLO · Full access'
              : 'Ask when needed',
          )}
        </p>
        {approvalExecution.permissions === 'yolo' && (
          <p className="danger">
            {t('YOLO runs commands without approval or sandbox restrictions.')}
          </p>
        )}
        {approvalText && <p className="confirmation-request">{approvalText}</p>}
        {task && approvalFiles.length > 0 && (
          <AttachmentBadges files={approvalFiles} taskId={task.id} t={t} />
        )}
      </Confirm>
      <Dialog
        open={attachmentPicker && !!task}
        onOpenChange={setAttachmentPicker}
        title={t('Attach files')}
        description={t('Only selected files are attached to this message.')}
        closeLabel={t('Close')}
      >
        {task && (
          <FileLibrary
            task={task}
            selectedIds={attachmentIds}
            t={t}
            busy={busy}
            selectUploads
            onToggle={toggleAttachment}
            onUpload={(files, select) => void uploadFiles(files, select)}
            onDelete={(id) =>
              setFileToDelete(
                task.attachments.find((file) => file.id === id) ?? null,
              )
            }
          />
        )}
        {uploadStatus}
        <Button onClick={() => setAttachmentPicker(false)}>{t('Done')}</Button>
      </Dialog>
      <Confirm
        open={!!fileToDelete}
        title="Delete file"
        description="The original will be deleted. Earlier conversation content is retained."
        action="Delete file"
        t={t}
        busy={busy}
        onClose={() => setFileToDelete(null)}
        onConfirm={() => {
          if (!fileToDelete) return;
          const id = fileToDelete.id;
          void mutate(`attachments/${id}`, undefined, 'DELETE').then((ok) => {
            if (ok) {
              setAttachmentIds((ids) => ids.filter((value) => value !== id));
              setFileToDelete(null);
            }
          });
        }}
      >
        <p>{fileToDelete?.name}</p>
      </Confirm>
      <Dialog
        open={!!importThread}
        onOpenChange={(open) => {
          if (!open) setImportThread(null);
        }}
        title={t('Resume conversation')}
        description={t('Confirm before resuming a CLI conversation.')}
        closeLabel={t('Close')}
      >
        <div className="stack">
          <p>{importThread?.title}</p>
          <label className="answer-option">
            <input
              type="checkbox"
              checked={confirmInactive}
              onChange={(event) => setConfirmInactive(event.target.checked)}
            />
            {t('The original CLI conversation is no longer running.')}
          </label>
          <Button
            variant="primary"
            disabled={!confirmInactive || busy}
            onClick={() =>
              void act(async () => {
                const next = await api<Detail>('/tasks/import', {
                  thread_id: importThread?.id,
                  confirm_inactive: true,
                });
                await refreshTasks();
                choose(next.id);
                setImportThread(null);
              })
            }
          >
            {t('Resume conversation')}
          </Button>
        </div>
      </Dialog>
      <Dialog
        open={usageOpen}
        onOpenChange={setUsageOpen}
        title={t('Usage')}
        closeLabel={t('Close')}
      >
        <div className="stack">
          <strong>
            {t(
              account?.auth_type === 'chatgpt'
                ? 'Subscription connected'
                : 'Codex unavailable',
            )}
          </strong>
          {account?.error_code && <p>{t(errorCopy(account.error_code))}</p>}
          {account?.plan_type && <p>{account.plan_type}</p>}
          {account?.auth_type === 'chatgpt' ? (
            <Usage account={account} locale={locale} t={t} />
          ) : (
            <Button
              disabled={busy}
              onClick={() =>
                void act(async () =>
                  setDevice(await api<DeviceLogin>('/codex/login', {})),
                )
              }
            >
              {t('Connect ChatGPT')}
            </Button>
          )}
          {device && (
            <div className="stack">
              <p>{t('Enter this code on the sign-in page.')}</p>
              <code className="device-code">{device.user_code}</code>
              <a
                href={device.verification_url}
                target="_blank"
                rel="noreferrer"
              >
                {t('Open sign-in page')}
              </a>
            </div>
          )}
          <Button disabled={busy} onClick={() => void act(refreshAccount)}>
            <RefreshCw size={14} />
            {t('Refresh')}
          </Button>
        </div>
      </Dialog>
      {feedback}
    </div>
  );
}

function Usage({
  account,
  locale,
  t,
}: {
  account: Account;
  locale: Locale;
  t: ReturnType<typeof translate>;
}) {
  const limits = record(account.rate_limits);
  const rate = record(limits.rateLimits);
  const windows = [record(rate.primary), record(rate.secondary)].filter(
    (window) => typeof window.usedPercent === 'number',
  );
  if (!windows.length) return <p>{t('Usage is unavailable.')}</p>;
  return (
    <div className="stack">
      {windows.map((window, index) => (
        <div key={index} className="usage-window">
          <label>
            {t('Used')} {String(window.usedPercent)}%
            <progress max={100} value={Number(window.usedPercent)} />
          </label>
          {typeof window.resetsAt === 'number' && (
            <small>
              {t('Resets')} ·{' '}
              {new Date(window.resetsAt * 1000).toLocaleString(locale)}
            </small>
          )}
        </div>
      ))}
    </div>
  );
}
