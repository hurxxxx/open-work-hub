import { useEffect, useEffectEvent } from 'react';
import { createPortal } from 'react-dom';
import { BlockViewer, type BlockContent } from '@open-alm/ui';
import { Globe2, Lock, X } from 'lucide-react';
import { m } from 'motion/react';
import { useTranslation } from 'react-i18next';

import type { LearningPageNoteVisibility } from '../../api/types';
import { LearningImagePreviewSurface } from '../LearningImagePreview';

export function LearningNoteReadSurface({
  content,
  density = 'dense',
}: {
  content: BlockContent;
  density?: 'dense' | 'full';
}) {
  const densityClass =
    density === 'full'
      ? 'prose-base max-w-none flex-1 overflow-y-auto pr-2'
      : 'learning-note-dense prose-sm max-w-none';

  return (
    <LearningImagePreviewSurface
      className={`learning-note-readable app-markdown prose ${densityClass} dark:prose-invert`}
    >
      <BlockViewer content={content} />
    </LearningImagePreviewSurface>
  );
}

export function LearningNoteVisibilityPill({
  visibility,
}: {
  visibility: LearningPageNoteVisibility;
}) {
  const { t } = useTranslation('apps');
  const isPublic = visibility === 'public';
  return (
    <span
      aria-label={
        isPublic
          ? t('learning.notesPanel.publicNote')
          : t('learning.notesPanel.privateNote')
      }
      title={
        isPublic
          ? t('learning.notesPanel.public')
          : t('learning.notesPanel.private')
      }
      className={
        'flex size-6 items-center justify-center rounded-md border shadow-sm ' +
        (isPublic
          ? 'border-app-success-border bg-app-success/10 text-app-success-text dark:text-app-success-text'
          : 'border-app-border bg-app-surface text-app-ink/60')
      }
    >
      {isPublic ? <Globe2 size={11} /> : <Lock size={11} />}
    </span>
  );
}

export function LearningNoteReadonlyDialog({
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
  const closeEvent = useEffectEvent(onClose);
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        closeEvent();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [closeEvent]);

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
    <dialog
      open
      className="fixed inset-0 z-[9000] m-0 flex h-auto max-h-none w-auto max-w-none items-stretch justify-center border-0 bg-black/60 p-0 backdrop-blur-sm"
      aria-label={t('learning.notesPanel.readLarge')}
    >
      <button
        type="button"
        aria-label={t('common:actions.close')}
        className="absolute inset-0"
        onClick={onClose}
      />
      <m.div
        initial={{ opacity: 0, scale: 0.98 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.15 }}
        className="relative z-10 m-4 flex w-full max-w-5xl flex-col gap-3 rounded-2xl border border-app-border bg-app-surface p-5 shadow-2xl lg:m-8 lg:p-6"
        data-testid="learning-page-notes-readonly-viewer"
      >
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-app-border/50 pb-3">
          <div className="flex min-w-0 items-center gap-2">
            <LearningNoteVisibilityPill visibility={visibility} />
            <span className="app-text-control truncate text-app-ink">
              {title}
            </span>
            {subtitle ? (
              <span className="app-text-meta text-app-ink/45">
                · {subtitle}
              </span>
            ) : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t('common:actions.close')}
            title={t('common:actions.close')}
            className="flex size-8 items-center justify-center rounded-md border border-app-border bg-app-surface text-app-ink/70 transition-colors hover:border-app-accent hover:text-app-accent"
          >
            <X size={14} />
          </button>
        </header>
        <LearningNoteReadSurface content={content} density="full" />
      </m.div>
    </dialog>,
    document.body,
  );
}
