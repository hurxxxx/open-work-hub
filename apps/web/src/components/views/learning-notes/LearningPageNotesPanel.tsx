import { useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import {
  Archive,
  Check,
  ChevronRight,
  Eye,
  Globe2,
  Lock,
  Pencil,
  X,
} from 'lucide-react';
import { BlockEditor, BlockViewer, type BlockContent } from '@aidoo/ui';

import {
  useLearningPageNoteDetail,
  useLearningPageNotesList,
  useMyLearningPageNote,
} from '@/src/domains/learning-notes/learning-notes-hooks';
import { LearningNotesApiError } from '@/src/domains/learning-notes/learning-notes-api';
import type {
  LearningPageNoteDetail,
  LearningPageNoteListItem,
  LearningPageNoteVisibility,
} from '@/src/domains/learning-notes/types';

export interface LearningPageNotesPanelProps {
  token: string | null;
  courseSlug: string;
  lessonId: string;
  lessonTitle: string;
}

type MyEditorMode = 'view' | 'edit';

const EMPTY_BLOCKS: BlockContent = [];

export function LearningPageNotesPanel({
  token,
  courseSlug,
  lessonId,
  lessonTitle,
}: LearningPageNotesPanelProps) {
  const list = useLearningPageNotesList(token, courseSlug, lessonId);
  const mine = useMyLearningPageNote(token, courseSlug, lessonId);

  const [mode, setMode] = useState<MyEditorMode>('view');
  const [draftBlocks, setDraftBlocks] = useState<BlockContent>(EMPTY_BLOCKS);
  const [draftVisibility, setDraftVisibility] = useState<LearningPageNoteVisibility>('private');
  const [flash, setFlash] = useState<'saved' | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const draftDirtyRef = useRef(false);

  // When the lesson changes, reset the editor state to avoid draft bleed.
  useEffect(() => {
    setMode('view');
    setDraftBlocks(EMPTY_BLOCKS);
    setDraftVisibility('private');
    setActionError(null);
    draftDirtyRef.current = false;
  }, [lessonId]);

  const savedContent = useMemo<BlockContent>(
    () => (mine.note?.content_blocks ?? []) as BlockContent,
    [mine.note],
  );

  const enterEditMode = (startingFromExisting: boolean) => {
    setDraftBlocks(startingFromExisting ? savedContent : EMPTY_BLOCKS);
    setDraftVisibility(mine.note?.visibility ?? 'private');
    draftDirtyRef.current = false;
    setMode('edit');
    setActionError(null);
  };

  const cancelEdit = () => {
    if (draftDirtyRef.current) {
      const confirmed =
        typeof window !== 'undefined'
          ? window.confirm('작성 중인 변경 사항이 있습니다. 취소하시겠어요?')
          : true;
      if (!confirmed) return;
    }
    setMode('view');
    setDraftBlocks(EMPTY_BLOCKS);
    draftDirtyRef.current = false;
    setActionError(null);
  };

  const saveDraft = async () => {
    setActionError(null);
    try {
      await mine.upsert({
        course_slug: courseSlug,
        lesson_id: lessonId,
        lesson_title: lessonTitle,
        visibility: draftVisibility,
        content_blocks: draftBlocks as unknown[],
      });
      setMode('view');
      draftDirtyRef.current = false;
      setFlash('saved');
      window.setTimeout(() => setFlash(null), 1800);
      list.refresh();
    } catch (caught) {
      setActionError(
        caught instanceof LearningNotesApiError
          ? caught.message
          : '저장에 실패했습니다. 잠시 후 다시 시도해 주세요.',
      );
    }
  };

  const archiveMine = async () => {
    if (!mine.note) return;
    const confirmed =
      typeof window !== 'undefined'
        ? window.confirm('내 노트를 보관하시겠어요? 언제든 복원할 수 있습니다.')
        : true;
    if (!confirmed) return;
    try {
      await mine.archive(mine.note.doc_id);
      list.refresh();
    } catch (caught) {
      setActionError(
        caught instanceof LearningNotesApiError
          ? caught.message
          : '보관에 실패했습니다.',
      );
    }
  };

  const busy = list.status === 'loading' || mine.status === 'loading';

  return (
    <section
      aria-label="페이지 노트"
      data-testid="learning-page-notes-panel"
      className="flex flex-col gap-4"
    >
      <CompactHeader
        totalCount={list.items.length}
        othersCount={list.othersNotes.length}
        flash={flash}
      />

      {busy ? (
        <NotesSkeleton />
      ) : list.status === 'error' ? (
        <InlineError message={list.error ?? '불러오는 중 오류가 발생했습니다.'} />
      ) : null}

      <MyNoteSlot
        mode={mode}
        saving={mine.saving}
        myNote={mine.note}
        draftBlocks={draftBlocks}
        draftVisibility={draftVisibility}
        actionError={actionError}
        savedContent={savedContent}
        onEdit={() => enterEditMode(true)}
        onCreate={() => enterEditMode(false)}
        onArchive={archiveMine}
        onCancel={cancelEdit}
        onSave={saveDraft}
        onDraftChange={(content) => {
          setDraftBlocks(content);
          draftDirtyRef.current = true;
        }}
        onVisibilityChange={(v) => {
          setDraftVisibility(v);
          draftDirtyRef.current = true;
        }}
      />

      {list.othersNotes.length > 0 ? (
        <div className="flex flex-col gap-1.5">
          <h3 className="app-text-overline text-app-ink/40">
            다른 학습자 · {list.othersNotes.length}
          </h3>
          <div className="flex flex-col gap-1.5">
            {list.othersNotes.map((item) => (
              <OthersNoteCard key={item.doc_id} item={item} token={token} />
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}

// -------------------------------------------------------------------- header

/**
 * Minimal top row — just a label + saved flash. No icon, no description,
 * no fixed padding. Stays out of the way in read mode.
 */
function CompactHeader({
  totalCount,
  othersCount,
  flash,
}: {
  totalCount: number;
  othersCount: number;
  flash: 'saved' | null;
}) {
  // If there are notes, the label is redundant context (the cards speak for
  // themselves). If the slot is empty we keep the hint to seed curiosity.
  const showHint = totalCount === 0;
  return (
    <header className="flex min-h-[1rem] items-center justify-between gap-2">
      <span className="app-text-overline text-app-ink/40">
        {showHint
          ? '페이지 노트'
          : othersCount > 0
          ? `페이지 노트 · 공개 ${othersCount}`
          : '페이지 노트'}
      </span>
      <AnimatePresence>
        {flash === 'saved' ? (
          <motion.span
            key="saved-flash"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] font-medium text-emerald-600 dark:text-emerald-400"
          >
            <Check size={11} /> 저장됨
          </motion.span>
        ) : null}
      </AnimatePresence>
    </header>
  );
}

// -------------------------------------------------------------------- my note

function MyNoteSlot({
  mode,
  saving,
  myNote,
  draftBlocks,
  draftVisibility,
  actionError,
  savedContent,
  onEdit,
  onCreate,
  onArchive,
  onCancel,
  onSave,
  onDraftChange,
  onVisibilityChange,
}: {
  mode: MyEditorMode;
  saving: boolean;
  myNote: LearningPageNoteDetail | null;
  draftBlocks: BlockContent;
  draftVisibility: LearningPageNoteVisibility;
  actionError: string | null;
  savedContent: BlockContent;
  onEdit: () => void;
  onCreate: () => void;
  onArchive: () => void;
  onCancel: () => void;
  onSave: () => void;
  onDraftChange: (content: BlockContent) => void;
  onVisibilityChange: (visibility: LearningPageNoteVisibility) => void;
}) {
  if (mode === 'edit') {
    return (
      <EditForm
        initialContent={draftBlocks}
        initialVisibility={draftVisibility}
        saving={saving}
        actionError={actionError}
        onDraftChange={onDraftChange}
        onVisibilityChange={onVisibilityChange}
        onCancel={onCancel}
        onSave={onSave}
        hasExisting={myNote !== null}
      />
    );
  }

  if (myNote) {
    return (
      <MyNoteViewer
        note={myNote}
        savedContent={savedContent}
        saving={saving}
        onEdit={onEdit}
        onArchive={onArchive}
        actionError={actionError}
      />
    );
  }

  return <EmptyMyNotePill onCreate={onCreate} />;
}

/**
 * Read mode: strip everything that isn't the text. A subtle outline on
 * hover + a floating action toolbar appears at the top-right only while
 * the card is focused or hovered, keeping the reading surface clean.
 */
function MyNoteViewer({
  note,
  savedContent,
  saving,
  onEdit,
  onArchive,
  actionError,
}: {
  note: LearningPageNoteDetail;
  savedContent: BlockContent;
  saving: boolean;
  onEdit: () => void;
  onArchive: () => void;
  actionError: string | null;
}) {
  return (
    <div className="flex flex-col gap-2">
      <div
        className="group relative rounded-lg px-1 py-1 transition-colors hover:bg-app-surface/40 focus-within:bg-app-surface/40"
        data-testid="learning-page-notes-my-viewer"
      >
        <div className="learning-note-dense app-markdown prose prose-sm max-w-none dark:prose-invert">
          <BlockViewer content={savedContent} />
        </div>

        <div
          className={
            'pointer-events-none absolute right-1 top-1 flex items-center gap-1 ' +
            'opacity-0 transition-opacity group-hover:pointer-events-auto group-hover:opacity-100 ' +
            'group-focus-within:pointer-events-auto group-focus-within:opacity-100'
          }
          aria-hidden="true"
        >
          <VisibilityPill visibility={note.visibility} />
          <IconButton
            label="편집"
            onClick={onEdit}
            disabled={saving}
            testId="learning-page-notes-my-edit"
            tone="default"
          >
            <Pencil size={12} />
          </IconButton>
          <IconButton
            label="보관"
            onClick={onArchive}
            disabled={saving}
            testId="learning-page-notes-my-archive"
            tone="danger"
          >
            <Archive size={12} />
          </IconButton>
        </div>
      </div>
      {actionError ? <InlineError message={actionError} /> : null}
    </div>
  );
}

function IconButton({
  label,
  onClick,
  disabled,
  testId,
  tone,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  testId?: string;
  tone?: 'default' | 'danger';
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={label}
      data-testid={testId}
      className={
        'flex h-6 w-6 items-center justify-center rounded-md border border-app-border bg-app-surface text-app-ink/70 shadow-sm transition-colors hover:text-app-ink disabled:cursor-not-allowed disabled:opacity-50 ' +
        (tone === 'danger' ? 'hover:border-rose-400 hover:text-rose-600' : 'hover:border-app-accent hover:text-app-accent')
      }
    >
      {children}
    </button>
  );
}

function VisibilityPill({ visibility }: { visibility: LearningPageNoteVisibility }) {
  const isPublic = visibility === 'public';
  return (
    <span
      aria-label={isPublic ? '공개 노트' : '비공개 노트'}
      title={isPublic ? '공개' : '비공개'}
      className={
        'flex h-6 w-6 items-center justify-center rounded-md border shadow-sm ' +
        (isPublic
          ? 'border-emerald-400/60 bg-emerald-500/10 text-emerald-600 dark:text-emerald-300'
          : 'border-app-border bg-app-surface text-app-ink/60')
      }
    >
      {isPublic ? <Globe2 size={11} /> : <Lock size={11} />}
    </span>
  );
}

function EmptyMyNotePill({ onCreate }: { onCreate: () => void }) {
  return (
    <button
      type="button"
      onClick={onCreate}
      data-testid="learning-page-notes-my-create"
      className="group inline-flex items-center gap-1.5 self-start rounded-full border border-dashed border-app-border px-3 py-1 text-xs text-app-ink/55 transition-colors hover:border-app-accent hover:text-app-accent"
    >
      <Pencil size={11} />
      <span>내 노트 작성</span>
    </button>
  );
}

// -------------------------------------------------------------------- editor

function EditForm({
  initialContent,
  initialVisibility,
  saving,
  actionError,
  onDraftChange,
  onVisibilityChange,
  onCancel,
  onSave,
  hasExisting,
}: {
  initialContent: BlockContent;
  initialVisibility: LearningPageNoteVisibility;
  saving: boolean;
  actionError: string | null;
  onDraftChange: (content: BlockContent) => void;
  onVisibilityChange: (visibility: LearningPageNoteVisibility) => void;
  onCancel: () => void;
  onSave: () => void;
  hasExisting: boolean;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex flex-col gap-3 rounded-xl border border-app-accent/40 bg-app-surface p-3 shadow-[0_0_0_3px_rgba(99,102,241,0.08)] lg:p-4"
      data-testid="learning-page-notes-my-editor"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <VisibilityToggle value={initialVisibility} onChange={onVisibilityChange} />
        <span className="app-text-meta text-app-ink/50">
          {hasExisting ? '기존 노트를 덮어씁니다.' : '첫 저장 시 내 노트로 기록됩니다.'}
        </span>
      </div>
      <div className="rounded-lg border border-app-border/50 px-1.5 py-1 focus-within:border-app-accent">
        <BlockEditor
          initialContent={initialContent}
          onChange={onDraftChange}
          placeholder="이 레슨에 대한 내 생각, 질문, 요약…"
        />
      </div>
      {actionError ? <InlineError message={actionError} /> : null}
      <div className="flex items-center justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          disabled={saving}
          className="inline-flex items-center gap-1.5 rounded-full border border-app-border bg-app-surface px-3 py-1 text-xs font-medium text-app-ink transition-colors hover:border-app-ink/40 disabled:cursor-not-allowed disabled:opacity-50"
          data-testid="learning-page-notes-my-cancel"
        >
          <X size={12} /> 취소
        </button>
        <button
          type="button"
          onClick={onSave}
          disabled={saving}
          className="inline-flex items-center gap-1.5 rounded-full bg-app-accent px-4 py-1 text-xs font-semibold text-app-accent-fg shadow-sm transition-colors hover:bg-app-accent/90 disabled:cursor-not-allowed disabled:opacity-60"
          data-testid="learning-page-notes-my-save"
        >
          <Check size={12} /> {saving ? '저장 중…' : '저장'}
        </button>
      </div>
    </motion.div>
  );
}

function VisibilityToggle({
  value,
  onChange,
}: {
  value: LearningPageNoteVisibility;
  onChange: (visibility: LearningPageNoteVisibility) => void;
}) {
  return (
    <div
      role="radiogroup"
      aria-label="공개 범위"
      className="inline-flex self-start rounded-full border border-app-border bg-app-surface/80 p-0.5 text-xs"
    >
      <VisibilityOption
        active={value === 'private'}
        onClick={() => onChange('private')}
        icon={<Lock size={12} />}
        label="비공개"
        testId="learning-page-notes-visibility-private"
      />
      <VisibilityOption
        active={value === 'public'}
        onClick={() => onChange('public')}
        icon={<Globe2 size={12} />}
        label="공개"
        testId="learning-page-notes-visibility-public"
      />
    </div>
  );
}

function VisibilityOption({
  active,
  onClick,
  icon,
  label,
  testId,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
  testId: string;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={active}
      onClick={onClick}
      data-testid={testId}
      className={
        'inline-flex items-center gap-1 rounded-full px-2.5 py-1 transition-colors ' +
        (active
          ? 'bg-app-accent text-app-accent-fg shadow-sm'
          : 'text-app-ink/60 hover:text-app-ink')
      }
    >
      {icon}
      <span>{label}</span>
    </button>
  );
}

// -------------------------------------------------------------------- others

function OthersNoteCard({
  item,
  token,
}: {
  item: LearningPageNoteListItem;
  token: string | null;
}) {
  const [open, setOpen] = useState(false);
  const detail = useLearningPageNoteDetail(open ? token : null, open ? item.doc_id : null);

  return (
    <article
      className="overflow-hidden rounded-lg border border-app-border/50 bg-app-surface/40 transition-colors hover:border-app-accent/40"
      data-testid={`learning-page-notes-other-card-${item.doc_id}`}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 px-2.5 py-2 text-left"
        aria-expanded={open}
      >
        <div className="flex min-w-0 items-center gap-2">
          <AuthorAvatar name={item.author_name} />
          <span className="app-text-control truncate text-app-ink">
            {item.author_name || '학습자'}
          </span>
          <span className="app-text-meta shrink-0 text-app-ink/45">
            · {formatRelative(item.updated_at)}
          </span>
        </div>
        <span
          className={
            'text-app-ink/40 transition-transform ' + (open ? 'rotate-90' : '')
          }
          aria-hidden="true"
        >
          <ChevronRight size={13} />
        </span>
      </button>

      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            key="content"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.16 }}
            className="overflow-hidden"
          >
            <div className="border-t border-app-border/40 px-3 py-2">
              {detail.status === 'loading' ? (
                <NotesSkeleton rows={2} />
              ) : detail.status === 'error' ? (
                <InlineError message={detail.error ?? '불러오지 못했습니다.'} />
              ) : detail.note ? (
                <div className="learning-note-dense app-markdown prose prose-sm max-w-none dark:prose-invert">
                  <BlockViewer content={detail.note.content_blocks as BlockContent} />
                </div>
              ) : (
                <span className="app-text-meta text-app-ink/50">
                  <Eye size={12} className="mr-1 inline" />
                  이 노트를 더 이상 볼 수 없습니다.
                </span>
              )}
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </article>
  );
}

function AuthorAvatar({ name }: { name: string }) {
  const initials = useMemo(() => {
    const trimmed = (name || '').trim();
    if (!trimmed) return '·';
    // Take first two characters — handles Korean names cleanly; for Latin
    // names it ends up with initials like "AB".
    const parts = trimmed.split(/\s+/);
    if (parts.length >= 2) {
      return (parts[0][0] ?? '') + (parts[1][0] ?? '');
    }
    return trimmed.slice(0, 2);
  }, [name]);

  return (
    <span
      aria-hidden="true"
      className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-app-accent/10 text-[10px] font-semibold uppercase text-app-accent"
    >
      {initials}
    </span>
  );
}

// -------------------------------------------------------------------- shared

function NotesSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div
      role="status"
      aria-label="페이지 노트 불러오는 중"
      className="flex flex-col gap-2"
    >
      {Array.from({ length: rows }).map((_, idx) => (
        <div
          key={idx}
          className="h-3 animate-pulse rounded-full bg-app-ink/10"
          style={{ width: `${95 - idx * 15}%` }}
        />
      ))}
    </div>
  );
}

function InlineError({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-rose-300/60 bg-rose-50/50 p-2 text-xs text-rose-700 dark:border-rose-400/40 dark:bg-rose-500/10 dark:text-rose-200">
      {message}
    </div>
  );
}

function formatRelative(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';
  const diffSeconds = Math.round((Date.now() - then) / 1000);
  if (diffSeconds < 60) return '방금 전';
  const diffMinutes = Math.round(diffSeconds / 60);
  if (diffMinutes < 60) return `${diffMinutes}분 전`;
  const diffHours = Math.round(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours}시간 전`;
  const diffDays = Math.round(diffHours / 24);
  if (diffDays < 7) return `${diffDays}일 전`;
  return new Date(iso).toLocaleDateString();
}
