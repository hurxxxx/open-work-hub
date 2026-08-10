import { useEffect, useRef, useState } from 'react';
import { LazyMotion, domAnimation, m } from 'motion/react';
import { useTranslation } from 'react-i18next';
import { Link, Navigate, useParams } from 'react-router-dom';
import ReactMarkdown, { type Components } from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import remarkGfm from 'remark-gfm';
import {
  ChevronLeft,
  ChevronRight,
  GraduationCap,
  Maximize2,
  Minimize2,
} from 'lucide-react';

import {
  type LearningCourse,
  type LearningLesson,
} from '../model/manifest';
import { loadLessonBody, resolveLessonAsset } from '../model/content';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { normalizeTimeZone } from '@/src/platform/time/time-utils';
import {
  LearningImagePreviewDialog,
  type LearningImagePreview,
} from './LearningImagePreview';
import { LearningPageNotesPanel } from './learning-notes/LearningPageNotesPanel';
import { resolveLearningCourseRoute } from './learning-course-route-model';

const REMARK_PLUGINS = [remarkGfm];
const REHYPE_PLUGINS = [rehypeHighlight];

const WIDTH_PREF_KEY = 'learning:wide-mode';

function useWideMode() {
  const [wide, setWide] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    return window.localStorage.getItem(WIDTH_PREF_KEY) === '1';
  });
  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(WIDTH_PREF_KEY, wide ? '1' : '0');
  }, [wide]);
  return [wide, setWide] as const;
}

export function LearningCourseView() {
  const { workspaceSlug, courseSlug, lessonSlug } = useParams();
  const route = resolveLearningCourseRoute({
    workspaceSlug,
    courseSlug,
    lessonSlug,
  });

  switch (route.kind) {
    case 'redirect':
      return <Navigate to={route.to} replace />;
    case 'emptyCourse':
      return (
        <CourseWithoutLessons
          courseTitle={route.course.title}
          basePath={route.basePath}
        />
      );
    case 'lesson':
      return (
        <LessonLayout
          course={route.course}
          lesson={route.lesson}
          index={route.index}
          total={route.total}
          basePath={route.basePath}
          prev={route.prev}
          next={route.next}
        />
      );
  }
}

function LessonLayout({
  course,
  lesson,
  index,
  total,
  basePath,
  prev,
  next,
}: {
  course: LearningCourse;
  lesson: LearningLesson;
  index: number;
  total: number;
  basePath: string;
  prev: LearningLesson | null;
  next: LearningLesson | null;
}) {
  const { t } = useTranslation('apps');
  const [wide, setWide] = useWideMode();
  const [previewImage, setPreviewImage] = useState<LearningImagePreview | null>(
    null,
  );
  const rootRef = useRef<HTMLDivElement>(null);
  const { token, user } = useAuth();
  const timeZone = normalizeTimeZone(user?.time_zone);

  useEffect(() => {
    let el: HTMLElement | null = rootRef.current;
    while (el) {
      const { overflowY } = getComputedStyle(el);
      if (overflowY === 'auto' || overflowY === 'scroll') {
        el.scrollTo({ top: 0, behavior: 'auto' });
        return;
      }
      el = el.parentElement;
    }
    window.scrollTo({ top: 0, behavior: 'auto' });
  }, [lesson.slug]);

  // Course/lesson navigation now lives in the app sub-sidebar, so this view
  // renders just the article and the notes panel. At xl+ the notes get a
  // dedicated right column; below xl they fall to the bottom of the article.
  const gridClass = wide
    ? 'xl:grid-cols-1'
    : 'xl:grid-cols-[minmax(0,1fr)_30rem]';

  const contentMaxW = wide ? 'max-w-none' : 'max-w-3xl';

  const notesPlacementClass = wide
    ? ''
    : 'xl:col-start-2 xl:row-start-1 xl:sticky xl:top-6 xl:self-start xl:max-h-[calc(100vh-3rem)] xl:overflow-y-auto';

  return (
    <LazyMotion features={domAnimation}>
      <m.div
        ref={rootRef}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className={
          'grid w-full grid-cols-1 gap-8 px-4 py-6 lg:gap-10 lg:px-8 lg:py-10 ' +
          gridClass
        }
      >
        <article className="min-w-0">
          <div className={`mx-auto ${contentMaxW}`}>
            <div className="mb-6 flex items-center justify-between gap-3">
              <div className="inline-flex items-center gap-2 rounded-full border border-app-border bg-app-surface px-3 py-1">
                <span className="app-text-overline text-app-ink/60">
                  {t('learning.lessonIndex', { index: index + 1, total })}
                </span>
              </div>
              <button
                type="button"
                onClick={() => setWide((v) => !v)}
                className="hidden items-center gap-1.5 rounded-md border border-app-border px-2.5 py-1 text-app-ink/60 transition-colors hover:border-app-accent hover:text-app-accent xl:inline-flex"
                aria-pressed={wide}
                title={
                  wide
                    ? t('learning.viewNarrowTitle')
                    : t('learning.viewWideTitle')
                }
                data-testid="learning-width-toggle"
              >
                {wide ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
                <span className="app-text-overline">
                  {wide ? t('learning.viewNarrow') : t('learning.viewWide')}
                </span>
              </button>
            </div>

            <header className="mb-10">
              <h1 className="app-text-display text-app-ink">{lesson.title}</h1>
            </header>

            <LessonBody
              key={lesson.file}
              lesson={lesson}
              onPreviewImageChange={setPreviewImage}
            />

            <nav
              aria-label={t('learning.lessonNav')}
              className="mt-16 grid grid-cols-1 gap-3 border-t border-app-border pt-6 sm:grid-cols-2"
            >
              {prev ? (
                <Link
                  to={`${basePath}/${course.slug}/${prev.slug}`}
                  className="group flex flex-col gap-1 rounded-lg border border-app-border p-4 transition-colors hover:border-app-accent hover:bg-app-surface"
                  data-testid="learning-lesson-prev"
                >
                  <span className="flex items-center gap-1 app-text-overline text-app-ink/50">
                    <ChevronLeft size={12} />
                    {t('learning.previousLesson')}
                  </span>
                  <span className="app-text-control text-app-ink group-hover:text-app-accent">
                    {prev.title}
                  </span>
                </Link>
              ) : (
                <span aria-hidden="true" />
              )}
              {next ? (
                <Link
                  to={`${basePath}/${course.slug}/${next.slug}`}
                  className="group flex flex-col gap-1 rounded-lg border border-app-border p-4 text-right transition-colors hover:border-app-accent hover:bg-app-surface sm:col-start-2"
                  data-testid="learning-lesson-next"
                >
                  <span className="flex items-center justify-end gap-1 app-text-overline text-app-ink/50">
                    {t('learning.nextLesson')}
                    <ChevronRight size={12} />
                  </span>
                  <span className="app-text-control text-app-ink group-hover:text-app-accent">
                    {next.title}
                  </span>
                </Link>
              ) : (
                <span aria-hidden="true" />
              )}
            </nav>
          </div>
        </article>

        <aside
          aria-label={t('learning.notes')}
          className={notesPlacementClass}
          data-testid="learning-page-notes-slot"
        >
          <LearningPageNotesPanel
            key={lesson.id}
            token={token}
            courseSlug={course.slug}
            lessonId={lesson.id}
            lessonTitle={lesson.title}
            timeZone={timeZone}
          />
        </aside>
        {previewImage ? (
          <LearningImagePreviewDialog
            image={previewImage}
            onClose={() => setPreviewImage(null)}
          />
        ) : null}
      </m.div>
    </LazyMotion>
  );
}

function LessonBody({
  lesson,
  onPreviewImageChange,
}: {
  lesson: LearningLesson;
  onPreviewImageChange: (image: LearningImagePreview | null) => void;
}) {
  const { t } = useTranslation('apps');
  const [bodyState, setBodyState] = useState<{
    body: string | null;
    isLoading: boolean;
  }>({
    body: null,
    isLoading: true,
  });

  useEffect(() => {
    let isMounted = true;

    loadLessonBody(lesson.file).then((loadedBody) => {
      if (!isMounted) return;
      setBodyState({ body: loadedBody, isLoading: false });
    });

    return () => {
      isMounted = false;
    };
  }, [lesson.file]);

  const markdownComponents: Components = {
    img({ src, alt, ...props }) {
      const resolvedSrc = resolveLessonAsset(lesson.file, src);
      const className = src?.includes('assets/logos/')
        ? 'learning-markdown-logo'
        : undefined;
      if (!resolvedSrc) {
        return (
          <img
            {...props}
            src={resolvedSrc}
            alt={alt ?? ''}
            className={className}
            loading="lazy"
          />
        );
      }
      const imageAlt = alt ?? '';
      return (
        <button
          type="button"
          onClick={() =>
            onPreviewImageChange({ src: resolvedSrc, alt: imageAlt })
          }
          aria-label={
            imageAlt
              ? t('learning.openImagePreviewWithName', { name: imageAlt })
              : t('learning.openImagePreview')
          }
          title={t('learning.openImagePreview')}
          className="learning-image-preview-trigger"
          data-testid="learning-image-preview-trigger"
        >
          <img
            {...props}
            src={resolvedSrc}
            alt={imageAlt}
            className={
              className
                ? `${className} learning-image-preview-image`
                : 'learning-image-preview-image'
            }
            loading="lazy"
          />
        </button>
      );
    },
  };

  if (bodyState.isLoading) {
    return (
      <p className="app-text-body text-app-ink/60">
        {t('learning.lessonLoading')}
      </p>
    );
  }

  if (!bodyState.body) {
    return (
      <p className="app-text-body text-app-ink/60">
        {t('learning.lessonLoadFailed')}
      </p>
    );
  }

  return (
    <div
      data-testid={`learning-lesson-body-${lesson.slug}`}
      className="app-markdown prose prose-base max-w-none dark:prose-invert lg:prose-lg"
    >
      <ReactMarkdown
        remarkPlugins={REMARK_PLUGINS}
        rehypePlugins={REHYPE_PLUGINS}
        components={markdownComponents}
      >
        {bodyState.body}
      </ReactMarkdown>
    </div>
  );
}

function CourseWithoutLessons({
  courseTitle,
  basePath,
}: {
  courseTitle: string;
  basePath: string;
}) {
  const { t } = useTranslation('apps');
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col items-center gap-3 p-10 text-center">
      <GraduationCap size={28} className="text-app-ink/40" />
      <h1 className="app-text-title text-app-ink">{courseTitle}</h1>
      <p className="app-text-body text-app-ink/60">{t('learning.noLessons')}</p>
      <Link
        to={basePath}
        className="app-text-control text-app-accent hover:underline"
      >
        {t('learning.backToCourses')}
      </Link>
    </div>
  );
}
