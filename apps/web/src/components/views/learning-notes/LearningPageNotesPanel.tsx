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
  Sparkles,
  StickyNote,
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
      className="rounded-2xl border border-app-border/70 bg-gradient-to-b from-app-surface/70 to-app-surface/30 p-4 shadow-sm backdrop-blur-[2px] lg:p-5"
    >
      <PanelHeader
        count={list.items.length}
        othersCount={list.othersNotes.length}
        flash={flash}
      />

      <div className="mt-5 flex flex-col gap-6">
        {busy ? (
          <NotesSkeleton />
        ) : list.status === 'error' ? (
          <InlineError message={list.error ?? '불러오는 중 오류가 발생했습니다.'} />
        ) : null}

        {/* --- My note slot -------------------------------------------------- */}
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

        {/* --- Other learners' public notes --------------------------------- */}
        {list.othersNotes.length > 0 ? (
          <div className="flex flex-col gap-2">
            <h3 className="app-text-overline text-app-ink/45">
              다른 학습자의 공개 노트 · {list.othersNotes.length}
            </h3>
            <div className="flex flex-col gap-2">
              {list.othersNotes.map((item) => (
                <OthersNoteCard key={item.doc_id} item={item} token={token} />
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}

// -------------------------------------------------------------------- header

function PanelHeader({
  count,
  othersCount,
  flash,
}: {
  count: number;
  othersCount: number;
  flash: 'saved' | null;
}) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-3">
      <div className="flex items-start gap-2.5">
        <span
          className="mt-0.5 flex h-8 w-8 items-center justify-center rounded-xl bg-app-accent/10 text-app-accent"
          aria-hidden="true"
        >
          <StickyNote size={16} />
        </span>
        <div className="flex flex-col">
          <h2 className="app-text-title text-app-ink">
            페이지 노트
            {count > 0 ? (
              <span className="ml-2 text-app-ink/40 font-normal">· {count}</span>
            ) : null}
          </h2>
          <p className="app-text-meta text-app-ink/55">
            이 레슨에 대한 개인 학습 노트를 남기세요.{' '}
            {othersCount > 0 ? `${othersCount}개의 공개 노트가 있습니다.` : '원하면 공개로 공유할 수도 있어요.'}
          </p>
        </div>
      </div>

      <AnimatePresence>
        {flash === 'saved' ? (
          <motion.span
            key="saved-flash"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2.5 py-1 text-xs font-medium text-emerald-600 dark:text-emerald-400"
          >
            <Check size={12} /> 저장됨
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
  return (
    <div
      className="rounded-2xl border border-app-accent/30 bg-app-surface/80 p-4 shadow-[0_0_0_3px_rgba(99,102,241,0.06)] lg:p-5"
      data-testid="learning-page-notes-my-slot"
    >
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 className="app-text-overline text-app-accent">내 노트</h3>
        {myNote && mode === 'view' ? (
          <VisibilityBadge visibility={myNote.visibility} />
        ) : null}
      </div>

      {mode === 'edit' ? (
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
      ) : myNote ? (
        <div className="flex flex-col gap-3" data-testid="learning-page-notes-my-viewer">
          <div className="rounded-xl border border-app-border/50 bg-app-surface/60 px-2 py-1 lg:px-3 lg:py-2">
            <div className="app-markdown prose prose-base max-w-none dark:prose-invert">
              <BlockViewer content={savedContent} />
            </div>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="app-text-meta text-app-ink/50">
              {formatRelative(myNote.updated_at)} 업데이트
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={onArchive}
                disabled={saving}
                className="inline-flex items-center gap-1.5 rounded-full border border-app-border px-3 py-1 text-xs font-medium text-app-ink/70 transition-colors hover:border-rose-400 hover:text-rose-600 disabled:cursor-not-allowed disabled:opacity-50"
                data-testid="learning-page-notes-my-archive"
              >
                <Archive size={12} /> 보관
              </button>
              <button
                type="button"
                onClick={onEdit}
                disabled={saving}
                className="inline-flex items-center gap-1.5 rounded-full bg-app-ink/90 px-3 py-1 text-xs font-medium text-app-surface shadow-sm transition-colors hover:bg-app-ink disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white/95 dark:text-app-ink"
                data-testid="learning-page-notes-my-edit"
              >
                <Pencil size={12} /> 편집
              </button>
            </div>
          </div>
          {actionError ? <InlineError message={actionError} /> : null}
        </div>
      ) : (
        <EmptyMyNoteCTA onCreate={onCreate} />
      )}
    </div>
  );
}

function EmptyMyNoteCTA({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-app-border/70 bg-app-surface/30 px-4 py-7 text-center">
      <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-full bg-app-accent/10 text-app-accent">
        <Sparkles size={18} />
      </div>
      <p className="app-text-body text-app-ink/75">
        이 레슨을 읽으며 든 생각·질문·요약을 남겨보세요.
      </p>
      <p className="mt-1 app-text-meta text-app-ink/50">
        기본은 비공개입니다. 원하면 공개로 전환해 다른 학습자와 공유할 수 있어요.
      </p>
      <button
        type="button"
        onClick={onCreate}
        className="mt-4 inline-flex items-center gap-1.5 rounded-full bg-app-accent px-4 py-1.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-app-accent/90 focus:outline-none focus:ring-2 focus:ring-app-accent/40"
        data-testid="learning-page-notes-my-create"
      >
        <Pencil size={13} /> 노트 작성
      </button>
    </div>
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
      className="flex flex-col gap-3"
      data-testid="learning-page-notes-my-editor"
    >
      <VisibilityToggle value={initialVisibility} onChange={onVisibilityChange} />
      <div className="rounded-xl border border-app-accent/50 bg-app-surface px-2 py-1 shadow-[0_0_0_3px_rgba(99,102,241,0.08)] focus-within:shadow-[0_0_0_4px_rgba(99,102,241,0.15)] lg:px-3 lg:py-2">
        <BlockEditor
          initialContent={initialContent}
          onChange={onDraftChange}
          placeholder="이 레슨에 대한 내 생각, 질문, 요약…"
        />
      </div>
      {actionError ? <InlineError message={actionError} /> : null}
      <div className="flex items-center justify-between gap-2">
        <span className="app-text-meta text-app-ink/50">
          {hasExisting ? '기존 노트를 덮어씁니다.' : '첫 저장 시 내 노트로 기록됩니다.'}
        </span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={saving}
            className="inline-flex items-center gap-1.5 rounded-full border border-app-border px-3 py-1 text-xs font-medium text-app-ink/70 transition-colors hover:text-app-ink disabled:cursor-not-allowed disabled:opacity-50"
            data-testid="learning-page-notes-my-cancel"
          >
            <X size={12} /> 취소
          </button>
          <button
            type="button"
            onClick={onSave}
            disabled={saving}
            className="inline-flex items-center gap-1.5 rounded-full bg-app-accent px-4 py-1 text-xs font-medium text-white shadow-sm transition-colors hover:bg-app-accent/90 disabled:cursor-not-allowed disabled:opacity-60"
            data-testid="learning-page-notes-my-save"
          >
            <Check size={12} /> {saving ? '저장 중…' : '저장'}
          </button>
        </div>
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
          ? 'bg-app-accent text-white shadow-sm'
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
      className="overflow-hidden rounded-xl border border-app-border/60 bg-app-surface/50 transition-colors hover:border-app-accent/40"
      data-testid={`learning-page-notes-other-card-${item.doc_id}`}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
        aria-expanded={open}
      >
        <div className="flex min-w-0 items-center gap-3">
          <AuthorAvatar name={item.author_name} />
          <div className="flex min-w-0 flex-col">
            <span className="app-text-control truncate text-app-ink">
              {item.author_name || '학습자'}
            </span>
            <span className="app-text-meta text-app-ink/50">
              {formatRelative(item.updated_at)} 업데이트
            </span>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <VisibilityBadge visibility={item.visibility} subtle />
          <span
            className={
              'text-app-ink/40 transition-transform ' + (open ? 'rotate-90' : '')
            }
            aria-hidden="true"
          >
            <ChevronRight size={14} />
          </span>
        </div>
      </button>

      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            key="content"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="overflow-hidden"
          >
            <div className="border-t border-app-border/50 bg-app-surface/30 px-4 py-3">
              {detail.status === 'loading' ? (
                <NotesSkeleton rows={2} />
              ) : detail.status === 'error' ? (
                <InlineError message={detail.error ?? '불러오지 못했습니다.'} />
              ) : detail.note ? (
                <div className="app-markdown prose prose-base max-w-none dark:prose-invert">
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
      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-app-accent/10 text-xs font-semibold uppercase text-app-accent"
    >
      {initials}
    </span>
  );
}

// -------------------------------------------------------------------- shared

function VisibilityBadge({
  visibility,
  subtle,
}: {
  visibility: LearningPageNoteVisibility;
  subtle?: boolean;
}) {
  const isPublic = visibility === 'public';
  const className = subtle
    ? 'inline-flex items-center gap-1 rounded-full border border-app-border/60 px-2 py-0.5 text-[11px] text-app-ink/55'
    : isPublic
    ? 'inline-flex items-center gap-1 rounded-full border border-emerald-400/50 bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:text-emerald-300'
    : 'inline-flex items-center gap-1 rounded-full border border-app-border/70 bg-app-surface px-2 py-0.5 text-xs font-medium text-app-ink/60';
  return (
    <span className={className}>
      {isPublic ? <Globe2 size={11} /> : <Lock size={11} />}
      {isPublic ? '공개' : '비공개'}
    </span>
  );
}

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
    <div className="rounded-xl border border-rose-300/60 bg-rose-50/50 p-3 text-sm text-rose-700 dark:border-rose-400/40 dark:bg-rose-500/10 dark:text-rose-200">
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

