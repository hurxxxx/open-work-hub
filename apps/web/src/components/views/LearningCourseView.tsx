import { useEffect, useRef, useState } from 'react';
import { motion } from 'motion/react';
import { Link, Navigate, useParams } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
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
  findCourse,
  findLesson,
  getAllLessons,
  type LearningCourse,
  type LearningLesson,
} from '@/src/domains/learning/manifest';
import { getLessonBody } from '@/src/domains/learning/content';

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
  const basePath = workspaceSlug ? `/w/${workspaceSlug}/learning` : '/learning';

  const course = courseSlug ? findCourse(courseSlug) : null;

  if (!course) {
    return <Navigate to={basePath} replace />;
  }

  const allLessons = getAllLessons(course);

  // No lesson slug in the URL? Send the reader into the first lesson so the
  // course landing URL stays stable and the reader lands on real content.
  if (!lessonSlug) {
    const first = allLessons[0];
    if (!first) {
      return <CourseWithoutLessons courseTitle={course.title} basePath={basePath} />;
    }
    return <Navigate to={`${basePath}/${course.slug}/${first.slug}`} replace />;
  }

  const resolved = findLesson(course, lessonSlug);
  if (!resolved) {
    return <Navigate to={`${basePath}/${course.slug}`} replace />;
  }

  const { lesson, index } = resolved;
  const prev: LearningLesson | null = index > 0 ? allLessons[index - 1] : null;
  const next: LearningLesson | null =
    index < allLessons.length - 1 ? allLessons[index + 1] : null;

  const body = getLessonBody(lesson.file);

  return (
    <LessonLayout
      course={course}
      lesson={lesson}
      index={index}
      total={allLessons.length}
      basePath={basePath}
      body={body}
      prev={prev}
      next={next}
    />
  );
}

function LessonLayout({
  course,
  lesson,
  index,
  total,
  basePath,
  body,
  prev,
  next,
}: {
  course: LearningCourse;
  lesson: LearningLesson;
  index: number;
  total: number;
  basePath: string;
  body: string | null;
  prev: LearningLesson | null;
  next: LearningLesson | null;
}) {
  const [wide, setWide] = useWideMode();
  const rootRef = useRef<HTMLDivElement>(null);

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

  // Narrow mode: 3-col grid with a right balance column so the article sits in
  // viewport center. Wide mode: TOC hides entirely, article spans full width.
  const gridClass = wide
    ? 'lg:grid-cols-1'
    : 'lg:grid-cols-[16rem_minmax(0,1fr)] xl:grid-cols-[16rem_minmax(0,1fr)_16rem]';

  const contentMaxW = wide ? 'max-w-none' : 'max-w-3xl';

  return (
    <motion.div
      ref={rootRef}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className={
        'grid w-full grid-cols-1 gap-8 px-4 py-6 lg:gap-12 lg:px-8 lg:py-10 ' +
        gridClass
      }
    >
      <aside
        aria-label="레슨 목차"
        className={
          'lg:sticky lg:top-6 lg:max-h-[calc(100vh-3rem)] lg:self-start lg:overflow-y-auto ' +
          (wide ? 'lg:hidden' : '')
        }
      >
        <Link
          to={basePath}
          className="mb-4 inline-flex items-center gap-2 text-app-ink/60 transition-colors hover:text-app-accent"
        >
          <GraduationCap size={14} />
          <span className="app-text-overline">{course.title}</span>
        </Link>
        <nav>
          <div className="flex flex-col gap-5">
            {course.parts.map((part) => (
              <section key={part.slug} aria-labelledby={`learning-part-${part.slug}`}>
                <h2
                  id={`learning-part-${part.slug}`}
                  className="app-text-overline mb-2 text-app-ink/45"
                >
                  {part.title}
                </h2>
                <ol className="flex flex-col">
                  {part.lessons.map((item, i) => {
                    const active = item.slug === lesson.slug;
                    return (
                      <li key={item.slug} className="relative">
                        <Link
                          to={`${basePath}/${course.slug}/${item.slug}`}
                          className={
                            'group flex items-start gap-3 border-l-2 py-1.5 pl-3 pr-2 text-sm transition-colors ' +
                            (active
                              ? 'border-app-accent font-medium text-app-accent'
                              : 'border-transparent text-app-ink/70 hover:border-app-ink/20 hover:text-app-ink')
                          }
                          data-testid={`learning-lesson-link-${item.slug}`}
                        >
                          <span
                            className={
                              'shrink-0 tabular-nums text-xs leading-5 ' +
                              (active ? 'text-app-accent/70' : 'text-app-ink/35')
                            }
                          >
                            {String(i + 1).padStart(2, '0')}
                          </span>
                          <span className="leading-5">{item.title}</span>
                        </Link>
                      </li>
                    );
                  })}
                </ol>
              </section>
            ))}
          </div>
        </nav>
      </aside>

      <article className="min-w-0">
        <div className={`mx-auto ${contentMaxW}`}>
          <div className="mb-6 flex items-center justify-between gap-3">
            <div className="inline-flex items-center gap-2 rounded-full border border-app-border bg-app-surface px-3 py-1">
              <span className="app-text-overline text-app-ink/60">
                레슨 {index + 1} / {total}
              </span>
            </div>
            <button
              type="button"
              onClick={() => setWide((v) => !v)}
              className="hidden items-center gap-1.5 rounded-md border border-app-border px-2.5 py-1 text-app-ink/60 transition-colors hover:border-app-accent hover:text-app-accent lg:inline-flex"
              aria-pressed={wide}
              title={wide ? '좁게 보기' : '넓게 보기'}
              data-testid="learning-width-toggle"
            >
              {wide ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
              <span className="app-text-overline">
                {wide ? '좁게' : '넓게'}
              </span>
            </button>
          </div>

          <header className="mb-10">
            <h1 className="app-text-display text-app-ink">{lesson.title}</h1>
          </header>

          {body ? (
            <div
              data-testid={`learning-lesson-body-${lesson.slug}`}
              className="app-markdown prose prose-base max-w-none dark:prose-invert lg:prose-lg"
            >
              <ReactMarkdown remarkPlugins={REMARK_PLUGINS} rehypePlugins={REHYPE_PLUGINS}>
                {body}
              </ReactMarkdown>
            </div>
          ) : (
            <p className="app-text-body text-app-ink/60">
              이 레슨 본문을 불러오지 못했습니다. 파일이 정상적으로 배포되었는지 확인하세요.
            </p>
          )}

          <nav
            aria-label="레슨 이동"
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
                  이전 레슨
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
                  다음 레슨
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
    </motion.div>
  );
}

function CourseWithoutLessons({
  courseTitle,
  basePath,
}: {
  courseTitle: string;
  basePath: string;
}) {
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col items-center gap-3 p-10 text-center">
      <GraduationCap size={28} className="text-app-ink/40" />
      <h1 className="app-text-title text-app-ink">{courseTitle}</h1>
      <p className="app-text-body text-app-ink/60">
        이 코스에는 아직 레슨이 없습니다.
      </p>
      <Link to={basePath} className="app-text-control text-app-accent hover:underline">
        ← 전체 코스로 돌아가기
      </Link>
    </div>
  );
}
