import { useEffect, useEffectEvent, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, LazyMotion, domAnimation, m } from 'motion/react';
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
import { BlockEditor, type BlockContent } from '@ai-do/ui';
import { useTranslation } from 'react-i18next';

import { useLearningPageNoteDetail } from '../../api/learning-notes-hooks';
import type {
  LearningPageNoteDetail,
  LearningPageNoteListItem,
  LearningPageNoteVisibility,
} from '../../api/types';
import {
  LearningNoteReadonlyDialog,
  LearningNoteReadSurface,
  LearningNoteVisibilityPill,
} from './LearningNoteReadSurface';
import {
  authorInitials,
  formatLearningNoteRelativeTime,
  type MyEditorMode,
} from './learning-page-notes-panel-model';
import { useLearningPageNotesController } from './useLearningPageNotesController';

export interface LearningPageNotesPanelProps {
  token: string | null;
  courseSlug: string;
  lessonId: string;
  lessonTitle: string;
  timeZone?: string | null;
}

export function LearningPageNotesPanel({
  token,
  courseSlug,
  lessonId,
  lessonTitle,
  timeZone,
}: LearningPageNotesPanelProps) {
  const { t } = useTranslation('apps');
  const controller = useLearningPageNotesController({
    token,
    courseSlug,
    lessonId,
    lessonTitle,
    timeZone,
  });
  const { list, mine, panelState, savedContent, resolvedTimeZone, actions } =
    controller;
  const { mode, draftBlocks, draftVisibility, flash, actionError, expanded } =
    panelState;

  return (
    <LazyMotion features={domAnimation}>
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

        {controller.busy ? (
          <NotesSkeleton />
        ) : list.status === 'error' ? (
          <InlineError
            message={list.error ?? t('learning.notesPanel.loadFailed')}
          />
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
          onEdit={() => actions.enterEditMode(true)}
          onCreate={() => actions.enterEditMode(false)}
          onArchive={actions.archiveMine}
          onCancel={actions.cancelEdit}
          onSave={actions.saveDraft}
          onToggleExpanded={actions.toggleExpanded}
          onDraftChange={actions.onDraftChange}
          onVisibilityChange={actions.onVisibilityChange}
        />

        {list.othersNotes.length > 0 ? (
          <div className="flex flex-col gap-1.5">
            <h3 className="app-text-overline text-app-ink/40">
              {t('learning.notesPanel.otherLearners', {
                count: list.othersNotes.length,
              })}
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
    </LazyMotion>
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
          <m.span
            key="saved-flash"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            className="inline-flex items-center gap-1 rounded-full bg-app-success/10 px-2 py-0.5 text-[12px] font-medium text-app-success-text dark:text-app-success-text"
          >
            <Check size={11} /> {t('learning.notesPanel.saved')}
          </m.span>
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
        <LearningNoteReadSurface content={savedContent} />

        <div
          className={
            'pointer-events-none absolute right-1 top-1 flex items-center gap-1 ' +
            'opacity-0 transition-opacity group-hover:pointer-events-auto group-hover:opacity-100 ' +
            'group-focus-within:pointer-events-auto group-focus-within:opacity-100'
          }
          aria-hidden="true"
        >
          <LearningNoteVisibilityPill visibility={note.visibility} />
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
        <LearningNoteReadonlyDialog
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
        'flex size-6 items-center justify-center rounded-md border border-app-border bg-app-surface text-app-ink/70 shadow-sm transition-colors hover:text-app-ink disabled:cursor-not-allowed disabled:opacity-50 ' +
        (tone === 'danger'
          ? 'hover:border-rose-400 hover:text-app-danger-text'
          : 'hover:border-app-accent hover:text-app-accent')
      }
    >
      {children}
    </button>
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
  const toggleExpandedEvent = useEffectEvent(onToggleExpanded);
  // ESC collapses the fullscreen overlay back to inline edit. Cancel is a
  // distinct action (discards the draft).
  useEffect(() => {
    if (!expanded || typeof window === 'undefined') return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        toggleExpandedEvent();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [expanded, toggleExpandedEvent]);

  const toolbar = (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <VisibilityToggle
          value={initialVisibility}
          onChange={onVisibilityChange}
        />
        <button
          type="button"
          onClick={onToggleExpanded}
          title={
            expanded
              ? t('learning.notesPanel.collapse')
              : t('learning.notesPanel.viewLarge')
          }
          aria-label={
            expanded
              ? t('learning.notesPanel.collapse')
              : t('learning.notesPanel.viewLarge')
          }
          data-testid="learning-page-notes-my-expand"
          className="inline-flex items-center gap-1 rounded-full border border-app-border bg-app-surface px-2.5 py-1 text-xs text-app-ink/70 transition-colors hover:border-app-accent hover:text-app-accent"
        >
          {expanded ? <Minimize2 size={12} /> : <Maximize2 size={12} />}
          <span className="app-text-overline">
            {expanded
              ? t('learning.notesPanel.collapse')
              : t('learning.notesPanel.large')}
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
          <Check size={12} />{' '}
          {saving ? t('learning.notesPanel.saving') : t('common:actions.save')}
        </button>
      </div>
    </>
  );

  if (expanded && typeof document !== 'undefined') {
    return createPortal(
      <dialog
        open
        className="fixed inset-0 z-[9000] m-0 flex h-auto max-h-none w-auto max-w-none items-stretch justify-center border-0 bg-black/60 p-0 backdrop-blur-sm"
        aria-label={t('learning.notesPanel.fullscreenEdit')}
      >
        <m.div
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.15 }}
          className="m-4 flex w-full max-w-5xl flex-col gap-3 rounded-2xl border border-app-border bg-app-surface p-5 shadow-2xl lg:m-8 lg:p-6"
          data-testid="learning-page-notes-my-editor"
        >
          {toolbar}
          {editor}
          {footer}
        </m.div>
      </dialog>,
      document.body,
    );
  }

  return (
    <m.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex flex-col gap-3 rounded-xl border border-app-accent/40 bg-app-surface p-3 shadow-[var(--ui-shadow-focus-ring)] lg:p-4"
      data-testid="learning-page-notes-my-editor"
    >
      {toolbar}
      {editor}
      {footer}
    </m.div>
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
  const detail = useLearningPageNoteDetail(
    open ? token : null,
    open ? item.doc_id : null,
  );
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
          <m.div
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
                <InlineError
                  message={
                    detail.error ?? t('learning.notesPanel.loadNoteFailed')
                  }
                />
              ) : detail.note ? (
                <div className="flex flex-col gap-2">
                  <LearningNoteReadSurface content={readerContent} />
                  <div className="flex justify-end">
                    <button
                      type="button"
                      onClick={() => setReading(true)}
                      className="inline-flex items-center gap-1 rounded-full border border-app-border bg-app-surface px-2.5 py-1 text-[12px] text-app-ink/70 transition-colors hover:border-app-accent hover:text-app-accent"
                      data-testid={`learning-page-notes-other-expand-${item.doc_id}`}
                    >
                      <Maximize2 size={11} />
                      <span className="app-text-overline">
                        {t('learning.notesPanel.large')}
                      </span>
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
          </m.div>
        ) : null}
      </AnimatePresence>
      {reading && detail.note ? (
        <LearningNoteReadonlyDialog
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
  const initials = useMemo(() => authorInitials(name), [name]);

  return (
    <span
      aria-hidden="true"
      className="flex size-6 shrink-0 items-center justify-center rounded-full bg-app-accent/10 text-[10px] font-semibold uppercase text-app-accent"
    >
      {initials}
    </span>
  );
}

// -------------------------------------------------------------------- shared

function NotesSkeleton({ rows = 3 }: { rows?: number }) {
  const { t } = useTranslation('apps');
  return (
    <output
      aria-live="polite"
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
    </output>
  );
}

function InlineError({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-app-danger-border bg-app-danger-bg p-2 text-xs text-app-danger-text dark:border-app-danger-border dark:bg-app-danger/10 dark:text-app-danger-text">
      {message}
    </div>
  );
}

function formatRelative(iso: string, timeZone: string, locale: string): string {
  return formatLearningNoteRelativeTime({ iso, locale, timeZone });
}
