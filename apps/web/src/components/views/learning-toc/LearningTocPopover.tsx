import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { Link } from 'react-router-dom';
import { ArrowLeft, BookOpen, ListTree, X } from 'lucide-react';

import {
  LEARNING_COURSES,
  type LearningCourse,
} from '@/src/domains/learning/manifest';

export interface LearningTocPopoverProps {
  courseSlug: string;
  lessonSlug: string;
  basePath: string;
  /**
   * Optional label shown as the trigger button's count/caption
   * (e.g. "레슨 3 / 15"). If omitted the button just shows "목차".
   */
  progressLabel?: string;
}

/**
 * ClickUp/Notion-style in-course navigator. Collapsed → a single button in
 * the lesson header. Expanded → an anchored popover with a home link and
 * the full course → parts → lessons tree. Scrolls the active lesson into
 * view on open. Closes on ESC, outside click, or route change.
 */
export function LearningTocPopover({
  courseSlug,
  lessonSlug,
  basePath,
  progressLabel,
}: LearningTocPopoverProps) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const activeItemRef = useRef<HTMLAnchorElement | null>(null);

  const currentCourse = useMemo<LearningCourse | null>(
    () => LEARNING_COURSES.find((course) => course.slug === courseSlug) ?? null,
    [courseSlug],
  );

  // Close when navigating to a different lesson (Link click inside the popover).
  useEffect(() => {
    setOpen(false);
  }, [lessonSlug, courseSlug]);

  // ESC / outside click.
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        setOpen(false);
      }
    };
    const onPointer = (event: MouseEvent) => {
      const target = event.target as Node | null;
      if (!target) return;
      if (panelRef.current?.contains(target)) return;
      if (triggerRef.current?.contains(target)) return;
      setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    window.addEventListener('mousedown', onPointer);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('mousedown', onPointer);
    };
  }, [open]);

  // Scroll the active lesson into view whenever the panel opens.
  useLayoutEffect(() => {
    if (!open) return;
    const node = activeItemRef.current;
    if (!node) return;
    node.scrollIntoView({ block: 'center', behavior: 'auto' });
  }, [open]);

  return (
    <div className="relative">
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label="목차 열기"
        title="목차"
        data-testid="learning-toc-trigger"
        className={
          'inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-app-ink/70 transition-colors hover:border-app-accent hover:text-app-accent ' +
          (open
            ? 'border-app-accent bg-app-accent/10 text-app-accent'
            : 'border-app-border')
        }
      >
        <ListTree size={14} />
        <span className="app-text-overline">
          {progressLabel ?? '목차'}
        </span>
      </button>

      <AnimatePresence>
        {open ? (
          <motion.div
            key="toc-panel"
            ref={panelRef}
            role="dialog"
            aria-label="코스 목차"
            initial={{ opacity: 0, y: -6, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.98 }}
            transition={{ duration: 0.14, ease: 'easeOut' }}
            className="absolute right-0 top-full z-40 mt-2 w-[22rem] origin-top-right overflow-hidden rounded-xl border border-app-border bg-app-surface shadow-2xl"
            data-testid="learning-toc-panel"
          >
            <div className="flex items-center justify-between border-b border-app-border/70 px-3 py-2">
              <Link
                to={basePath}
                className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-app-ink/70 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
                data-testid="learning-toc-home-link"
              >
                <ArrowLeft size={12} />
                <span className="app-text-control-sm">전체 학습 홈</span>
              </Link>
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="목차 닫기"
                className="flex h-6 w-6 items-center justify-center rounded text-app-ink/50 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
              >
                <X size={12} />
              </button>
            </div>

            <div className="max-h-[min(28rem,calc(100vh-10rem))] overflow-y-auto px-2 pb-3 pt-2">
              {currentCourse ? (
                <CourseSection
                  course={currentCourse}
                  basePath={basePath}
                  activeLessonSlug={lessonSlug}
                  activeItemRef={activeItemRef}
                />
              ) : (
                <p className="px-3 py-4 text-sm text-app-ink/50">
                  코스를 찾을 수 없습니다.
                </p>
              )}
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

function CourseSection({
  course,
  basePath,
  activeLessonSlug,
  activeItemRef,
}: {
  course: LearningCourse;
  basePath: string;
  activeLessonSlug: string;
  activeItemRef: React.MutableRefObject<HTMLAnchorElement | null>;
}) {
  return (
    <nav aria-label={`${course.title} 목차`} className="flex flex-col gap-4">
      <div className="flex items-center gap-2 px-2 pt-1 text-app-ink">
        <BookOpen size={14} className="text-app-accent" />
        <span className="app-text-control text-app-ink">{course.title}</span>
      </div>
      {course.parts.map((part) => (
        <section
          key={part.slug}
          aria-labelledby={`learning-toc-part-${part.slug}`}
          className="flex flex-col gap-1"
        >
          <h3
            id={`learning-toc-part-${part.slug}`}
            className="app-text-overline px-2 text-app-ink/45"
          >
            {part.title}
          </h3>
          <ol className="flex flex-col">
            {part.lessons.map((lesson, idx) => {
              const isActive = lesson.slug === activeLessonSlug;
              const href = `${basePath}/${course.slug}/${lesson.slug}`;
              return (
                <li key={lesson.id}>
                  <Link
                    ref={isActive ? activeItemRef : undefined}
                    to={href}
                    data-testid={`learning-toc-lesson-${lesson.slug}`}
                    className={
                      'group flex items-start gap-2.5 rounded-md px-2 py-1 text-sm transition-colors ' +
                      (isActive
                        ? 'bg-app-accent/10 font-medium text-app-accent'
                        : 'text-app-ink/75 hover:bg-app-surface-hover hover:text-app-ink')
                    }
                  >
                    <span
                      className={
                        'shrink-0 tabular-nums text-xs leading-5 ' +
                        (isActive ? 'text-app-accent/80' : 'text-app-ink/35')
                      }
                    >
                      {String(idx + 1).padStart(2, '0')}
                    </span>
                    <span className="leading-5">{lesson.title}</span>
                  </Link>
                </li>
              );
            })}
          </ol>
        </section>
      ))}
    </nav>
  );
}
