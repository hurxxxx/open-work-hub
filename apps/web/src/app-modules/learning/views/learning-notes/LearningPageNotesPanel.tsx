import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'motion/react';
import {
  Archive,
  Check,
  ChevronRight,
  Eye,
  Globe2,
  Lock,
  Maximize2,
  Minimize2,
  Pencil,
  X,
} from 'lucide-react';
import { BlockEditor, BlockViewer, type BlockContent } from '@aidoo/ui';
import { useTranslation } from 'react-i18next';

import { formatRelativeTime, normalizeTimeZone } from '@/src/platform/time/time-utils';
import {
  useLearningPageNoteDetail,
  useLearningPageNotesList,
  useMyLearningPageNote,
} from '../../api/learning-notes-hooks';
import { LearningNotesApiError } from '../../api/learning-notes-api';
import type {
  LearningPageNoteDetail,
  LearningPageNoteListItem,
  LearningPageNoteVisibility,
} from '../../api/types';

export interface LearningPageNotesPanelProps {
  token: string | null;
  courseSlug: string;
  lessonId: string;
  lessonTitle: string;
  timeZone?: string | null;
}

type MyEditorMode = 'view' | 'edit';

const EMPTY_BLOCKS: BlockContent = [];

export function LearningPageNotesPanel({
  token,
  courseSlug,
  lessonId,
  lessonTitle,
  timeZone,
}: LearningPageNotesPanelProps) {
  const { t } = useTranslation('apps');
  const resolvedTimeZone = normalizeTimeZone(timeZone);
  const list = useLearningPageNotesList(token, courseSlug, lessonId);
  const mine = useMyLearningPageNote(token, courseSlug, lessonId);

  const [mode, setMode] = useState<MyEditorMode>('view');
  const [draftBlocks, setDraftBlocks] = useState<BlockContent>(EMPTY_BLOCKS);
  const [draftVisibility, setDraftVisibility] = useState<LearningPageNoteVisibility>('private');
  const [flash, setFlash] = useState<'saved' | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const draftDirtyRef = useRef(false);

  // When the lesson changes, reset the editor state to avoid draft bleed.
  useEffect(() => {
    setMode('view');
    setDraftBlocks(EMPTY_BLOCKS);
    setDraftVisibility('private');
    setActionError(null);
    setExpanded(false);
    draftDirtyRef.current = false;
  }, [lessonId]);

  // Always return to the inline editor when we leave edit mode, so the
  // next "편집" click starts from a clean small size.
  useEffect(() => {
    if (mode === 'view' && expanded) {
      setExpanded(false);
    }
  }, [mode, expanded]);

  // Scroll-lock the page while the editor is in fullscreen.
  useEffect(() => {
    if (!expanded || typeof document === 'undefined') return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previous;
    };
  }, [expanded]);

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
          ? window.confirm(t('learning.notesPanel.cancelDirtyConfirm'))
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
          : t('learning.notesPanel.saveFailed'),
      );
    }
  };

  const archiveMine = async () => {
    if (!mine.note) return;
    const confirmed =
      typeof window !== 'undefined'
        ? window.confirm(t('learning.notesPanel.archiveConfirm'))
        : true;
    if (!confirmed) return;
    try {
      await mine.archive(mine.note.doc_id);
      list.refresh();
    } catch (caught) {
      setActionError(
        caught instanceof LearningNotesApiError
          ? caught.message
          : t('learning.notesPanel.archiveFailed'),
      );
    }
  };

  const busy = list.status === 'loading' || mine.status === 'loading';

  return (
    <section
      aria-label={t('learning.notesPanel.pageNotes')}
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
        <InlineError message={list.error ?? t('learning.notesPanel.loadFailed')} />
      ) : null}

      <MyNoteSlot
        mode={mode}
        saving={mine.saving}
        myNote={mine.note}
        draftBlocks={draftBlocks}
        draftVisibility={draftVisibility}
        actionError={actionError}
        savedContent={savedContent}
        expanded={expanded}
        timeZone={resolvedTimeZone}
        onEdit={() => enterEditMode(true)}
        onCreate={() => enterEditMode(false)}
        onArchive={archiveMine}
        onCancel={cancelEdit}
        onSave={saveDraft}
        onToggleExpanded={() => setExpanded((v) => !v)}
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
            {t('learning.notesPanel.otherLearners', { count: list.othersNotes.length })}
          </h3>
          <div className="flex flex-col gap-1.5">
            {list.othersNotes.map((item) => (
              <OthersNoteCard
                key={item.doc_id}
                item={item}
                timeZone={resolvedTimeZone}
                token={token}
              />
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
  const { t } = useTranslation('apps');
  const showHint = totalCount === 0;
  return (
    <header className="flex min-h-[1rem] items-center justify-between gap-2">
      <span className="app-text-overline text-app-ink/40">
        {showHint
          ? t('learning.notesPanel.pageNotes')
          : othersCount > 0
          ? t('learning.notesPanel.pageNotesPublic', { count: othersCount })
          : t('learning.notesPanel.pageNotes')}
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
            <Check size={11} /> {t('learning.notesPanel.saved')}
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
  expanded,
  timeZone,
  onEdit,
  onCreate,
  onArchive,
  onCancel,
  onSave,
  onToggleExpanded,
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
  expanded: boolean;
  timeZone: string;
  onEdit: () => void;
  onCreate: () => void;
  onArchive: () => void;
  onCancel: () => void;
  onSave: () => void;
  onToggleExpanded: () => void;
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
        expanded={expanded}
        onDraftChange={onDraftChange}
        onVisibilityChange={onVisibilityChange}
        onCancel={onCancel}
        onSave={onSave}
        onToggleExpanded={onToggleExpanded}
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
        timeZone={timeZone}
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
  timeZone,
}: {
  note: LearningPageNoteDetail;
  savedContent: BlockContent;
  saving: boolean;
  onEdit: () => void;
  onArchive: () => void;
  actionError: string | null;
  timeZone: string;
}) {
  const { t, i18n } = useTranslation('apps');
  const [reading, setReading] = useState(false);
  return (
    <div className="flex flex-col gap-2">
      <div
        className="group relative rounded-lg py-0.5 transition-colors hover:bg-app-surface/40 focus-within:bg-app-surface/40"
        data-testid="learning-page-notes-my-viewer"
      >
        <div className="learning-note-readable learning-note-dense app-markdown prose prose-sm max-w-none dark:prose-invert">
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
            label={t('learning.notesPanel.viewLarge')}
            onClick={() => setReading(true)}
            testId="learning-page-notes-my-expand-view"
            tone="default"
          >
            <Maximize2 size={12} />
          </IconButton>
          <IconButton
            label={t('learning.notesPanel.edit')}
            onClick={onEdit}
            disabled={saving}
            testId="learning-page-notes-my-edit"
            tone="default"
          >
            <Pencil size={12} />
          </IconButton>
          <IconButton
            label={t('learning.notesPanel.archive')}
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
      {reading ? (
        <FullscreenReadonlyViewer
          content={savedContent}
          title={t('learning.notesPanel.myNote')}
          subtitle={t('learning.notesPanel.updated', {
            time: formatRelative(note.updated_at, timeZone, i18n.language),
          })}
          visibility={note.visibility}
          onClose={() => setReading(false)}
        />
      ) : null}
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
  const { t } = useTranslation('apps');
  const isPublic = visibility === 'public';
  return (
    <span
      aria-label={isPublic ? t('learning.notesPanel.publicNote') : t('learning.notesPanel.privateNote')}
      title={isPublic ? t('learning.notesPanel.public') : t('learning.notesPanel.private')}
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
  const { t } = useTranslation('apps');
  return (
    <button
      type="button"
      onClick={onCreate}
      data-testid="learning-page-notes-my-create"
      className="group inline-flex items-center gap-1.5 self-start rounded-full border border-dashed border-app-border px-3 py-1 text-xs text-app-ink/55 transition-colors hover:border-app-accent hover:text-app-accent"
    >
      <Pencil size={11} />
      <span>{t('learning.notesPanel.createMyNote')}</span>
    </button>
  );
}

// -------------------------------------------------------------------- editor

function EditForm({
  initialContent,
  initialVisibility,
  saving,
  actionError,
  expanded,
  onDraftChange,
  onVisibilityChange,
  onCancel,
  onSave,
  onToggleExpanded,
  hasExisting,
}: {
  initialContent: BlockContent;
  initialVisibility: LearningPageNoteVisibility;
  saving: boolean;
  actionError: string | null;
  expanded: boolean;
  onDraftChange: (content: BlockContent) => void;
  onVisibilityChange: (visibility: LearningPageNoteVisibility) => void;
  onCancel: () => void;
  onSave: () => void;
  onToggleExpanded: () => void;
  hasExisting: boolean;
}) {
  const { t } = useTranslation('apps');
  // ESC collapses the fullscreen overlay back to inline edit. Cancel is a
  // distinct action (discards the draft).
  useEffect(() => {
    if (!expanded || typeof window === 'undefined') return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        onToggleExpanded();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [expanded, onToggleExpanded]);

  const toolbar = (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <VisibilityToggle value={initialVisibility} onChange={onVisibilityChange} />
        <button
          type="button"
          onClick={onToggleExpanded}
          title={expanded ? t('learning.notesPanel.collapse') : t('learning.notesPanel.viewLarge')}
          aria-label={expanded ? t('learning.notesPanel.collapse') : t('learning.notesPanel.viewLarge')}
          data-testid="learning-page-notes-my-expand"
          className="inline-flex items-center gap-1 rounded-full border border-app-border bg-app-surface px-2.5 py-1 text-xs text-app-ink/70 transition-colors hover:border-app-accent hover:text-app-accent"
        >
          {expanded ? <Minimize2 size={12} /> : <Maximize2 size={12} />}
          <span className="app-text-overline">
            {expanded ? t('learning.notesPanel.collapse') : t('learning.notesPanel.large')}
          </span>
        </button>
      </div>
      <span className="app-text-meta text-app-ink/50">
        {hasExisting
          ? t('learning.notesPanel.overwriteExisting')
          : t('learning.notesPanel.firstSave')}
      </span>
    </div>
  );

  const editor = (
    <div
      className={
        'learning-note-readable rounded-lg border border-app-border/50 px-1.5 py-1 focus-within:border-app-accent ' +
        (expanded ? 'flex-1 min-h-0 overflow-y-auto' : 'learning-note-dense')
      }
    >
      <BlockEditor
        // Remount when switching between inline and fullscreen so the
        // editor picks up the parent's live draftBlocks as its initial
        // content and re-lays-out for the new container width.
        key={expanded ? 'expanded' : 'inline'}
        initialContent={initialContent}
        onChange={onDraftChange}
        placeholder={t('learning.notesPanel.editorPlaceholder')}
      />
    </div>
  );

  const footer = (
    <>
      {actionError ? <InlineError message={actionError} /> : null}
      <div className="flex items-center justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          disabled={saving}
          className="inline-flex items-center gap-1.5 rounded-full border border-app-border bg-app-surface px-3 py-1 text-xs font-medium text-app-ink transition-colors hover:border-app-ink/40 disabled:cursor-not-allowed disabled:opacity-50"
          data-testid="learning-page-notes-my-cancel"
        >
          <X size={12} /> {t('common:actions.cancel')}
        </button>
        <button
          type="button"
          onClick={onSave}
          disabled={saving}
          className="inline-flex items-center gap-1.5 rounded-full bg-app-accent px-4 py-1 text-xs font-semibold text-app-accent-fg shadow-sm transition-colors hover:bg-app-accent/90 disabled:cursor-not-allowed disabled:opacity-60"
          data-testid="learning-page-notes-my-save"
        >
          <Check size={12} /> {saving ? t('learning.notesPanel.saving') : t('common:actions.save')}
        </button>
      </div>
    </>
  );

  if (expanded && typeof document !== 'undefined') {
    return createPortal(
      <div
        className="fixed inset-0 z-[9000] flex items-stretch justify-center bg-black/60 backdrop-blur-sm"
        role="dialog"
        aria-label={t('learning.notesPanel.fullscreenEdit')}
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.15 }}
          className="m-4 flex w-full max-w-5xl flex-col gap-3 rounded-2xl border border-app-border bg-app-surface p-5 shadow-2xl lg:m-8 lg:p-6"
          data-testid="learning-page-notes-my-editor"
        >
          {toolbar}
          {editor}
          {footer}
        </motion.div>
      </div>,
      document.body,
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex flex-col gap-3 rounded-xl border border-app-accent/40 bg-app-surface p-3 shadow-[0_0_0_3px_rgba(99,102,241,0.08)] lg:p-4"
      data-testid="learning-page-notes-my-editor"
    >
      {toolbar}
      {editor}
      {footer}
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
  const { t } = useTranslation('apps');
  return (
    <div
      role="radiogroup"
      aria-label={t('learning.notesPanel.visibility')}
      className="inline-flex self-start rounded-full border border-app-border bg-app-surface/80 p-0.5 text-xs"
    >
      <VisibilityOption
        active={value === 'private'}
        onClick={() => onChange('private')}
        icon={<Lock size={12} />}
        label={t('learning.notesPanel.private')}
        testId="learning-page-notes-visibility-private"
      />
      <VisibilityOption
        active={value === 'public'}
        onClick={() => onChange('public')}
        icon={<Globe2 size={12} />}
        label={t('learning.notesPanel.public')}
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
  timeZone,
  token,
}: {
  item: LearningPageNoteListItem;
  timeZone: string;
  token: string | null;
}) {
  const { t, i18n } = useTranslation('apps');
  const [open, setOpen] = useState(false);
  const [reading, setReading] = useState(false);
  const detail = useLearningPageNoteDetail(open ? token : null, open ? item.doc_id : null);
  const readerContent = (detail.note?.content_blocks ?? []) as BlockContent;

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
            {item.author_name || t('learning.notesPanel.learner')}
          </span>
          <span className="app-text-meta shrink-0 text-app-ink/45">
            · {formatRelative(item.updated_at, timeZone, i18n.language)}
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
                <InlineError message={detail.error ?? t('learning.notesPanel.loadNoteFailed')} />
              ) : detail.note ? (
                <div className="flex flex-col gap-2">
                  <div className="learning-note-readable learning-note-dense app-markdown prose prose-sm max-w-none dark:prose-invert">
                    <BlockViewer content={readerContent} />
                  </div>
                  <div className="flex justify-end">
                    <button
                      type="button"
                      onClick={() => setReading(true)}
                      className="inline-flex items-center gap-1 rounded-full border border-app-border bg-app-surface px-2.5 py-1 text-[11px] text-app-ink/70 transition-colors hover:border-app-accent hover:text-app-accent"
                      data-testid={`learning-page-notes-other-expand-${item.doc_id}`}
                    >
                      <Maximize2 size={11} />
                      <span className="app-text-overline">{t('learning.notesPanel.large')}</span>
                    </button>
                  </div>
                </div>
              ) : (
                <span className="app-text-meta text-app-ink/50">
                  <Eye size={12} className="mr-1 inline" />
                  {t('learning.notesPanel.noteUnavailable')}
                </span>
              )}
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
      {reading && detail.note ? (
        <FullscreenReadonlyViewer
          content={readerContent}
          title={item.author_name || t('learning.notesPanel.learner')}
          subtitle={t('learning.notesPanel.updated', {
            time: formatRelative(item.updated_at, timeZone, i18n.language),
          })}
          visibility={item.visibility}
          onClose={() => setReading(false)}
        />
      ) : null}
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

function FullscreenReadonlyViewer({
  content,
  title,
  subtitle,
  visibility,
  onClose,
}: {
  content: BlockContent;
  title: string;
  subtitle?: string;
  visibility: LearningPageNoteVisibility;
  onClose: () => void;
}) {
  const { t } = useTranslation('apps');
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        onClose();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  useEffect(() => {
    if (typeof document === 'undefined') return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previous;
    };
  }, []);

  if (typeof document === 'undefined') return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[9000] flex items-stretch justify-center bg-black/60 backdrop-blur-sm"
      role="dialog"
      aria-label={t('learning.notesPanel.readLarge')}
      onClick={onClose}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.98 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.15 }}
        className="m-4 flex w-full max-w-5xl flex-col gap-3 rounded-2xl border border-app-border bg-app-surface p-5 shadow-2xl lg:m-8 lg:p-6"
        onClick={(event) => event.stopPropagation()}
        data-testid="learning-page-notes-readonly-viewer"
      >
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-app-border/50 pb-3">
          <div className="flex min-w-0 items-center gap-2">
            <VisibilityPill visibility={visibility} />
            <span className="app-text-control truncate text-app-ink">{title}</span>
            {subtitle ? (
              <span className="app-text-meta text-app-ink/45">· {subtitle}</span>
            ) : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t('common:actions.close')}
            title={t('common:actions.close')}
            className="flex h-8 w-8 items-center justify-center rounded-md border border-app-border bg-app-surface text-app-ink/70 transition-colors hover:border-app-accent hover:text-app-accent"
          >
            <X size={14} />
          </button>
        </header>
        <div className="learning-note-readable app-markdown prose prose-base max-w-none flex-1 overflow-y-auto pr-2 dark:prose-invert">
          <BlockViewer content={content} />
        </div>
      </motion.div>
    </div>,
    document.body,
  );
}

function NotesSkeleton({ rows = 3 }: { rows?: number }) {
  const { t } = useTranslation('apps');
  return (
    <div
      role="status"
      aria-label={t('learning.notesPanel.loading')}
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

function formatRelative(iso: string, timeZone: string, locale: string): string {
  return formatRelativeTime(iso, { locale, timeZone });
}
