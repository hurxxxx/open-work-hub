import { motion } from 'motion/react';
import { Link, Navigate, useParams } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import remarkGfm from 'remark-gfm';
import { ChevronLeft, ChevronRight, GraduationCap } from 'lucide-react';

import { findCourse, findLesson, type LearningLesson } from '@/src/domains/learning/manifest';
import { getLessonBody } from '@/src/domains/learning/content';

const REMARK_PLUGINS = [remarkGfm];
const REHYPE_PLUGINS = [rehypeHighlight];

export function LearningCourseView() {
  const { workspaceSlug, courseSlug, lessonSlug } = useParams();
  const basePath = workspaceSlug ? `/w/${workspaceSlug}/learning` : '/learning';

  const course = courseSlug ? findCourse(courseSlug) : null;

  if (!course) {
    return <Navigate to={basePath} replace />;
  }

  // No lesson slug in the URL? Send the reader into the first lesson so the
  // course landing URL stays stable and the reader lands on real content.
  if (!lessonSlug) {
    const first = course.lessons[0];
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
  const prev: LearningLesson | null = index > 0 ? course.lessons[index - 1] : null;
  const next: LearningLesson | null =
    index < course.lessons.length - 1 ? course.lessons[index + 1] : null;

  const body = getLessonBody(lesson.file);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="mx-auto flex w-full max-w-7xl flex-col gap-4 p-4 lg:flex-row lg:gap-6 lg:p-6"
    >
      <aside
        aria-label="레슨 목차"
        className="flex-shrink-0 rounded-lg border border-app-border bg-app-surface p-3 lg:w-72 lg:self-start"
      >
        <Link
          to={basePath}
          className="mb-3 flex items-center gap-2 text-app-ink/60 transition-colors hover:text-app-accent"
        >
          <GraduationCap size={16} />
          <span className="app-text-overline">{course.title}</span>
        </Link>
        <nav className="max-h-[70vh] overflow-y-auto pr-1">
          <ol className="flex flex-col gap-1">
            {course.lessons.map((item, i) => {
              const active = item.slug === lesson.slug;
              return (
                <li key={item.slug}>
                  <Link
                    to={`${basePath}/${course.slug}/${item.slug}`}
                    className={
                      'flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors ' +
                      (active
                        ? 'bg-app-accent/10 font-medium text-app-accent'
                        : 'text-app-ink/80 hover:bg-app-surface-sidebar')
                    }
                    data-testid={`learning-lesson-link-${item.slug}`}
                  >
                    <span className="shrink-0 tabular-nums text-app-ink/40">
                      {String(i + 1).padStart(2, '0')}
                    </span>
                    <span className="truncate">{item.title}</span>
                  </Link>
                </li>
              );
            })}
          </ol>
        </nav>
      </aside>

      <section className="min-w-0 flex-1 rounded-lg border border-app-border bg-app-surface p-6 lg:p-8">
        <header className="mb-6 border-b border-app-border pb-4">
          <p className="app-text-overline text-app-ink/60">
            레슨 {index + 1} / {course.lessons.length}
          </p>
          <h1 className="app-text-display mt-1 text-app-ink">{lesson.title}</h1>
        </header>

        {body ? (
          <div
            data-testid={`learning-lesson-body-${lesson.slug}`}
            className="app-markdown prose prose-sm max-w-none dark:prose-invert"
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
          className="mt-10 flex items-center justify-between gap-3 border-t border-app-border pt-4"
        >
          {prev ? (
            <Link
              to={`${basePath}/${course.slug}/${prev.slug}`}
              className="flex items-center gap-2 rounded-md border border-app-border px-3 py-2 app-text-control text-app-ink transition-colors hover:border-app-accent"
              data-testid="learning-lesson-prev"
            >
              <ChevronLeft size={16} />
              <span className="truncate">{prev.title}</span>
            </Link>
          ) : (
            <span aria-hidden="true" />
          )}
          {next ? (
            <Link
              to={`${basePath}/${course.slug}/${next.slug}`}
              className="flex items-center gap-2 rounded-md bg-app-accent px-3 py-2 app-text-control text-app-accent-fg transition-colors hover:bg-app-accent-hover"
              data-testid="learning-lesson-next"
            >
              <span className="truncate">{next.title}</span>
              <ChevronRight size={16} />
            </Link>
          ) : (
            <span aria-hidden="true" />
          )}
        </nav>
      </section>
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
