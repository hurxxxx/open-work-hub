import { Button, Dialog, Input } from '@open-work-hub/ui';
import { MultiFileDiff } from '@pierre/diffs/react';
import {
  Check,
  FileCode2,
  FileText,
  Play,
  Save,
  SquareTerminal,
} from 'lucide-react';
import {
  useEffect,
  useState,
  type Dispatch,
  type SetStateAction,
  type ReactNode,
} from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  api,
  locked,
  record,
  string,
  type Change,
  type Attachment,
  type Detail,
  type Diff,
  type Pending,
  type Revision,
} from './api';
import type { Copy, Translate } from './i18n';
import { AttachmentBadges } from './attachments';

export function Markdown({ text }: { text: string }) {
  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ children, ...props }) => (
            <a {...props} target="_blank" rel="noreferrer noopener">
              {children}
            </a>
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}

export function MessageItem({
  item,
  t,
  taskId = '',
}: {
  item: Record<string, unknown>;
  t: Translate;
  taskId?: string;
}) {
  const kind = string(item.type);
  if (kind === 'userMessage') {
    const content = Array.isArray(item.content) ? item.content : [];
    return (
      <article className="message user-message">
        <Markdown
          text={content.map((part) => string(record(part).text)).join('\n')}
        />
        {Array.isArray(item.attachments) && (
          <AttachmentBadges
            files={item.attachments as Attachment[]}
            taskId={taskId}
            t={t}
          />
        )}
      </article>
    );
  }
  if (kind === 'agentMessage' || kind === 'plan') {
    return (
      <article
        className={`message agent-message ${kind === 'plan' ? 'plan-message' : ''}`}
      >
        <div className="message-label">
          {kind === 'plan' ? (
            <>
              <FileText size={14} />
              {t('Plan')}
            </>
          ) : (
            'Codex'
          )}
        </div>
        <Markdown text={string(item.text)} />
      </article>
    );
  }
  if (kind === 'commandExecution') return <Command item={item} t={t} />;
  if (kind === 'fileChange')
    return (
      <details className="activity">
        <summary>
          <FileCode2 size={14} />
          {t('Changes')}
        </summary>
        {Array.isArray(item.changes) &&
          item.changes.map((change, i) => (
            <details key={i}>
              <summary>{string(record(change).path)}</summary>
              <pre>{string(record(change).diff)}</pre>
            </details>
          ))}
      </details>
    );
  return null;
}

export function Command({
  item,
  t,
}: {
  item: Record<string, unknown>;
  t: Translate;
}) {
  const code = typeof item.exitCode === 'number' ? item.exitCode : null;
  return (
    <details className="activity command">
      <summary>
        <SquareTerminal size={14} />
        <code>{string(item.command)}</code>
        <span
          className={
            code === 0 ? 'success' : code === null ? 'muted' : 'danger'
          }
        >
          {code === null ? t('In progress') : `${t('Exit code')} ${code}`}
        </span>
      </summary>
      <pre aria-label={t('Command output')}>
        {string(item.aggregatedOutput)}
      </pre>
    </details>
  );
}

export function RequestForm({
  request,
  t,
  disabled,
  onAnswer,
}: {
  request: Pending;
  t: Translate;
  disabled: boolean;
  onAnswer: (id: string, response: unknown) => void;
}) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const params = request.payload;
  const questions = Array.isArray(params.questions)
    ? params.questions.map(record)
    : [];
  const isQuestion = request.method === 'item/tool/requestUserInput';
  if (!isQuestion)
    return (
      <section className="request-panel" aria-label={t('Execution approval')}>
        <h3>
          {t(
            request.method.includes('fileChange')
              ? 'File change approval'
              : 'Execution approval',
          )}
        </h3>
        <p>{string(params.reason)}</p>
        {params.command != null && <pre>{string(params.command)}</pre>}
        {params.grantRoot != null && <code>{string(params.grantRoot)}</code>}
        {params.networkApprovalContext != null && (
          <pre>{JSON.stringify(params.networkApprovalContext, null, 2)}</pre>
        )}
        {params.permissions != null && (
          <pre>{JSON.stringify(params.permissions, null, 2)}</pre>
        )}
        <div className="actions">
          <Button
            variant="primary"
            disabled={disabled}
            onClick={() => onAnswer(request.id, { decision: 'accept' })}
          >
            {t(
              request.method === 'item/permissions/requestApproval'
                ? 'Allow for this turn'
                : 'Approve once',
            )}
          </Button>
          <Button
            disabled={disabled}
            onClick={() => onAnswer(request.id, { decision: 'decline' })}
          >
            {t('Decline')}
          </Button>
          <Button
            variant="ghost"
            disabled={disabled}
            onClick={() => onAnswer(request.id, { decision: 'cancel' })}
          >
            {t('Cancel')}
          </Button>
        </div>
      </section>
    );
  return (
    <form
      className="request-panel"
      onSubmit={(event) => {
        event.preventDefault();
        onAnswer(request.id, {
          answers: Object.fromEntries(
            questions.map((q) => [string(q.id), [answers[string(q.id)] ?? '']]),
          ),
        });
      }}
    >
      {questions.map((q) => {
        const id = string(q.id);
        const options = Array.isArray(q.options) ? q.options.map(record) : [];
        return (
          <fieldset key={id}>
            <legend>{string(q.question)}</legend>
            {options.map((option) => (
              <label className="answer-option" key={string(option.label)}>
                <input
                  type="radio"
                  name={`${request.id}-${id}`}
                  value={string(option.label)}
                  checked={answers[id] === option.label}
                  onChange={() =>
                    setAnswers({ ...answers, [id]: string(option.label) })
                  }
                />
                <span>
                  <strong>{string(option.label)}</strong>
                  <small>{string(option.description)}</small>
                </span>
              </label>
            ))}
            <Input
              aria-label={`${string(q.header) || t('Answer')} · ${t('Additional answer')}`}
              value={answers[id] ?? ''}
              type={q.isSecret ? 'password' : 'text'}
              maxLength={8000}
              onChange={(event) =>
                setAnswers({ ...answers, [id]: event.target.value })
              }
            />
          </fieldset>
        );
      })}
      <Button
        type="submit"
        variant="primary"
        disabled={
          disabled || questions.some((q) => !answers[string(q.id)]?.trim())
        }
      >
        {t('Submit answers')}
      </Button>
    </form>
  );
}

export type DocumentDraft = { body: string; base: Revision | undefined };

export function Documents({
  task,
  kind,
  t,
  busy,
  onSave,
  onPlan,
  onImplement,
  draft: savedDraft,
  onDraftChange,
}: {
  task: Detail;
  kind: 'requirements' | 'plan';
  t: Translate;
  busy: boolean;
  onSave: (body: unknown) => Promise<boolean>;
  onPlan: () => void;
  onImplement: (revision: Revision) => void;
  draft?: DocumentDraft | null;
  onDraftChange?: Dispatch<SetStateAction<DocumentDraft | null>>;
}) {
  const versions = task.revisions.filter((row) => row.kind === kind);
  const latest = versions.at(-1);
  const [selected, setSelected] = useState<number | null>(null);
  const revision = versions.find((row) => row.id === selected) ?? latest;
  const [localDraft, setLocalDraft] = useState<DocumentDraft | null>(null);
  const draft = onDraftChange ? savedDraft : localDraft;
  const setDraft = onDraftChange ?? setLocalDraft;
  const base = draft ? draft.base : revision;
  const body = draft?.body ?? revision?.body ?? '';
  const [editing, setEditing] = useState(false);
  useEffect(() => {
    setSelected(null);
    setEditing(false);
    setLocalDraft(null);
  }, [kind, task.id]);
  const modified = body !== (base?.body ?? '');
  const conflict = !!draft && base?.id !== latest?.id;
  const disabled = busy || locked(task) || base?.id !== latest?.id;
  const requirements = task.revisions
    .filter((r) => r.kind === 'requirements')
    .at(-1);
  const stale =
    kind === 'plan' &&
    requirements &&
    latest &&
    requirements.created_at > latest.created_at;
  return (
    <section className="document-pane">
      <div className="document-toolbar">
        <strong>{t(kind === 'requirements' ? 'Requirements' : 'Plan')}</strong>
        <div className="actions">
          {versions.length > 0 && (
            <select
              aria-label={t('Version')}
              value={base?.id}
              disabled={!!draft}
              onChange={(event) => {
                setSelected(Number(event.target.value));
                setEditing(false);
                setDraft(null);
              }}
            >
              {versions.map((row) => (
                <option key={row.id} value={row.id}>
                  {t('Version')} {row.version}
                </option>
              ))}
            </select>
          )}
          <Button
            variant="ghost"
            disabled={busy || locked(task) || (!draft && !!disabled)}
            onClick={() => setEditing(!editing)}
          >
            {t(editing ? 'Preview' : 'Edit document')}
          </Button>
        </div>
      </div>
      <div className="document-content">
        {editing ? (
          <textarea
            className="document-editor"
            aria-label={t('Edit document')}
            value={body}
            maxLength={100000}
            disabled={busy || locked(task)}
            onChange={(event) => setDraft({ body: event.target.value, base })}
          />
        ) : revision || draft ? (
          <Markdown text={body} />
        ) : (
          <div className="empty-result">
            <FileText size={24} />
            <p>
              {t('No document yet. Continue the conversation to create one.')}
            </p>
          </div>
        )}
      </div>
      <div className="document-footer">
        {conflict && (
          <small role="alert">
            {t(
              'The document changed in another tab. Your edits are preserved. Copy them before loading the latest version.',
            )}
          </small>
        )}
        {draft && (
          <Button
            variant="ghost"
            disabled={busy}
            onClick={() => {
              setDraft(null);
              setSelected(null);
            }}
          >
            {t('Discard edits and load latest version')}
          </Button>
        )}
        {modified && (
          <Button
            disabled={!!disabled || !body.trim()}
            onClick={async () => {
              if (
                await onSave({ kind, base_version: base?.version ?? 0, body })
              ) {
                setDraft((current) => (current === draft ? null : current));
                setSelected(null);
                setEditing(false);
              }
            }}
          >
            <Save size={14} />
            {t('Save document')}
          </Button>
        )}
        {kind === 'requirements' ? (
          <Button
            variant="primary"
            disabled={!!disabled || modified || !latest}
            onClick={onPlan}
          >
            <FileText size={14} />
            {t('Create implementation plan')}
          </Button>
        ) : (
          <Button
            variant="primary"
            disabled={!!disabled || modified || !latest || !!stale}
            onClick={() => latest && onImplement(latest)}
          >
            <Play size={14} />
            {t('Implement this plan')}
          </Button>
        )}
        {modified && (
          <small>{t('Save your changes before implementing.')}</small>
        )}
        {stale && (
          <small>
            {t('The saved plan changed. Review the latest version.')}
          </small>
        )}
      </div>
    </section>
  );
}

export function Changes({
  task,
  t,
  onError,
}: {
  task: Detail;
  t: Translate;
  onError: (error: unknown) => void;
}) {
  const [changes, setChanges] = useState<Change[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [diff, setDiff] = useState<Diff | null>(null);
  const [listState, setListState] = useState('loading');
  const [diffState, setDiffState] = useState('loading');
  const [listAttempt, setListAttempt] = useState(0);
  const [diffAttempt, setDiffAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setListState('loading');
    setChanges([]);
    setSelected(null);
    void api<Change[]>(
      `/tasks/${task.id}/changes`,
      undefined,
      undefined,
      controller.signal,
    )
      .then((rows) => {
        if (controller.signal.aborted) return;
        setListState('ready');
        setChanges(rows);
        setSelected((current) =>
          rows.some((row) => row.path === current)
            ? current
            : (rows[0]?.path ?? null),
        );
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          setListState('error');
          onError(error);
        }
      });
    return () => controller.abort();
  }, [task.id, task.status, onError, listAttempt]);
  useEffect(() => {
    setDiff(null);
    setDiffState('loading');
    if (!selected) return;
    const controller = new AbortController();
    void api<Diff>(
      `/tasks/${task.id}/diff?path=${encodeURIComponent(selected)}`,
      undefined,
      undefined,
      controller.signal,
    )
      .then((value) => {
        if (controller.signal.aborted) return;
        setDiff(value);
        setDiffState('ready');
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          setDiffState('error');
          onError(error);
        }
      });
    return () => controller.abort();
  }, [task.id, task.status, selected, onError, diffAttempt]);
  return (
    <div className="changes-pane">
      {task.isolated && (
        <p className="context-note">
          {t(
            'Your original changes are preserved. Review the isolated diff before integrating it.',
          )}
        </p>
      )}
      <nav className="file-list" aria-label={t('File changes')}>
        {changes.map((row) => (
          <button
            key={row.path}
            aria-pressed={selected === row.path}
            onClick={() => setSelected(row.path)}
          >
            <code>{row.status}</code>
            <span>{row.path}</span>
          </button>
        ))}
      </nav>
      {listState === 'loading' ? (
        <p role="status">{t('Loading changes…')}</p>
      ) : listState === 'error' ? (
        <div role="alert">
          <p>{t('Could not load changes.')}</p>
          <Button onClick={() => setListAttempt((value) => value + 1)}>
            {t('Retry')}
          </Button>
        </div>
      ) : !changes.length ? (
        <div className="empty-result">
          <Check size={24} />
          <p>{t('No file changes')}</p>
        </div>
      ) : diffState === 'error' ? (
        <div role="alert">
          <p>{t('Could not load this diff.')}</p>
          <Button onClick={() => setDiffAttempt((value) => value + 1)}>
            {t('Retry')}
          </Button>
        </div>
      ) : !diff ? (
        <p className="context-note">
          {t(
            selected
              ? 'Loading changes…'
              : 'Select a file to inspect its diff.',
          )}
        </p>
      ) : diff.binary ? (
        <p className="context-note">{t('Binary file changed')}</p>
      ) : (
        <div className="diff-content" aria-label={diff.path}>
          <MultiFileDiff
            oldFile={{ name: diff.path, contents: diff.old }}
            newFile={{ name: diff.path, contents: diff.new }}
            disableWorkerPool
            options={{
              diffStyle: 'unified',
              overflow: 'wrap',
              themeType: 'system',
            }}
          />
        </div>
      )}
    </div>
  );
}

export function Confirm({
  open,
  title,
  description,
  t,
  busy,
  onClose,
  onConfirm,
  children,
  action = 'Implement this plan',
}: {
  open: boolean;
  title: Copy;
  description: Copy;
  t: Translate;
  busy: boolean;
  onClose: () => void;
  onConfirm: () => void;
  children?: ReactNode;
  action?: Copy;
}) {
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
      title={t(title)}
      description={t(description)}
      closeLabel={t('Close')}
      actions={
        <>
          <Button onClick={onClose}>{t('Cancel')}</Button>
          <Button variant="primary" disabled={busy} onClick={onConfirm}>
            {t(action)}
          </Button>
        </>
      }
    >
      {action === 'Implement this plan' && (
        <p>
          {t('Read-only planning')} → {t('Implement')}
        </p>
      )}
      {children}
    </Dialog>
  );
}
