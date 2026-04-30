import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import { ChevronDown, ChevronRight, GraduationCap } from 'lucide-react';

import { LEARNING_COURSES, type LearningCourse } from '@/src/domains/learning/manifest';
import { cn } from '@/src/lib/utils';

interface LearningPathState {
  workspaceSlug: string | null;
  courseSlug: string | null;
  lessonSlug: string | null;
}

interface LearningSidebarTreeProps {
  currentPathname: string;
}

function parseLearningPathname(pathname: string): LearningPathState {
  const match = pathname.match(
    /^\/w\/([^/]+)\/learning(?:\/([^/]+)(?:\/([^/]+))?)?/,
  );
  return {
    workspaceSlug: match?.[1] ?? null,
    courseSlug: match?.[2] ?? null,
    lessonSlug: match?.[3] ?? null,
  };
}

export function LearningSidebarTree({ currentPathname }: LearningSidebarTreeProps) {
  const {
    workspaceSlug: activeWorkspaceSlug,
    courseSlug: activeCourseSlug,
    lessonSlug: activeLessonSlug,
  } = parseLearningPathname(currentPathname);
  const [expandedCourses, setExpandedCourses] = useState<Set<string>>(() => {
    const initial = new Set<string>();
    if (activeCourseSlug) initial.add(activeCourseSlug);
    return initial;
  });

  useEffect(() => {
    if (!activeCourseSlug) return;
    setExpandedCourses((current) => {
      if (current.has(activeCourseSlug)) return current;
      const next = new Set(current);
      next.add(activeCourseSlug);
      return next;
    });
  }, [activeCourseSlug]);

  const toggleCourse = (slug: string) => {
    setExpandedCourses((current) => {
      const next = new Set(current);
      if (next.has(slug)) {
        next.delete(slug);
      } else {
        next.add(slug);
      }
      return next;
    });
  };

  return (
    <div className="mt-2 space-y-1 border-t border-app-border pt-2">
      <span className="sidebar-section-label block px-3 py-1 text-gray-500">
        목차
      </span>
      <div className="space-y-2">
        {LEARNING_COURSES.map((course) => {
          const isExpanded = expandedCourses.has(course.slug);
          const isActiveCourse = course.slug === activeCourseSlug;
          return (
            <div key={course.slug} className="space-y-1">
              <button
                type="button"
                onClick={() => toggleCourse(course.slug)}
                aria-expanded={isExpanded}
                data-testid={`learning-course-toggle-${course.slug}`}
                className={cn(
                  'group/course flex w-full items-center gap-1 rounded-md px-2 py-1 text-left text-[13px] font-medium text-app-ink/75 transition-colors hover:bg-app-surface-hover hover:text-app-ink',
                  isActiveCourse && 'text-app-ink',
                )}
              >
                {isExpanded ? (
                  <ChevronDown size={11} className="shrink-0 text-gray-500 dark:text-gray-400" />
                ) : (
                  <ChevronRight size={11} className="shrink-0 text-gray-500 dark:text-gray-400" />
                )}
                <GraduationCap
                  size={13}
                  className={cn(
                    'shrink-0 text-gray-500 dark:text-gray-400',
                    isActiveCourse && 'text-app-accent',
                  )}
                />
                <span className="truncate">{course.title}</span>
              </button>
              <AnimatePresence initial={false}>
                {isExpanded ? (
                  <motion.div
                    key="content"
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.15 }}
                    className="overflow-hidden"
                  >
                    <LearningCourseParts
                      course={course}
                      workspaceSlug={activeWorkspaceSlug}
                      activeLessonSlug={
                        isActiveCourse ? activeLessonSlug : null
                      }
                    />
                  </motion.div>
                ) : null}
              </AnimatePresence>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function LearningCourseParts({
  course,
  workspaceSlug,
  activeLessonSlug,
}: {
  course: LearningCourse;
  workspaceSlug: string | null;
  activeLessonSlug: string | null;
}) {
  const encodedWorkspace = workspaceSlug ? encodeURIComponent(workspaceSlug) : '';
  return (
    <div className="ml-3 flex flex-col gap-3 border-l border-app-border pl-2">
      {course.parts.map((part) => (
        <section
          key={part.slug}
          aria-labelledby={`learning-tree-part-${part.slug}`}
        >
          <span
            id={`learning-tree-part-${part.slug}`}
            className="sidebar-section-label block px-2 py-0.5 text-gray-500"
          >
            {part.title}
          </span>
          <ol className="flex flex-col">
            {part.lessons.map((lesson, idx) => {
              const isActive = lesson.slug === activeLessonSlug;
              const href = encodedWorkspace
                ? `/w/${encodedWorkspace}/learning/${course.slug}/${lesson.slug}`
                : `/learning/${course.slug}/${lesson.slug}`;
              return (
                <li key={lesson.id}>
                  <Link
                    to={href}
                    data-testid={`learning-lesson-link-${lesson.slug}`}
                    className={cn(
                      'group flex items-start gap-2 rounded-md px-2 py-1 text-[12px] leading-5 transition-colors',
                      isActive
                        ? 'bg-app-accent/10 font-medium text-app-accent'
                        : 'text-app-ink/70 hover:bg-app-surface-hover hover:text-app-ink dark:text-app-ink/75',
                    )}
                  >
                    <span
                      className={cn(
                        'shrink-0 tabular-nums text-[11px] leading-5',
                        isActive ? 'text-app-accent/80' : 'text-app-ink/35',
                      )}
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
    </div>
  );
}
