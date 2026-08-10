import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { AnimatePresence, LazyMotion, domAnimation, m } from 'motion/react';
import { ChevronDown, ChevronRight, GraduationCap } from 'lucide-react';

import {
  buildLearningSidebarTree,
  type LearningSidebarCourseNode,
  type LearningSidebarExpansionOverrides,
} from './learning-sidebar-tree-model';
import { cn } from '@/src/lib/utils';

interface LearningSidebarTreeProps {
  currentPathname: string;
}

export function LearningSidebarTree({
  currentPathname,
}: LearningSidebarTreeProps) {
  const { t } = useTranslation('apps');
  const [courseExpansionOverrides, setCourseExpansionOverrides] =
    useState<LearningSidebarExpansionOverrides>({});
  const tree = useMemo(
    () =>
      buildLearningSidebarTree({
        currentPathname,
        expansionOverrides: courseExpansionOverrides,
      }),
    [courseExpansionOverrides, currentPathname],
  );

  const toggleCourse = (slug: string, isExpanded: boolean) => {
    setCourseExpansionOverrides((current) => ({
      ...current,
      [slug]: !isExpanded,
    }));
  };

  return (
    <div className="mt-2 space-y-1 border-t border-app-border pt-2">
      <span className="sidebar-section-label block px-3 py-1 text-app-ink/55">
        {t('learning.tableOfContents')}
      </span>
      <div className="space-y-2">
        {tree.courses.map((course) => {
          return (
            <div key={course.slug} className="space-y-1">
              <button
                type="button"
                onClick={() => toggleCourse(course.slug, course.isExpanded)}
                aria-expanded={course.isExpanded}
                data-testid={`learning-course-toggle-${course.slug}`}
                className={cn(
                  'group/course flex w-full items-center gap-1 rounded-md px-2 py-1 text-left text-[13px] font-medium text-app-ink/75 transition-colors hover:bg-app-surface-hover hover:text-app-ink',
                  course.isActive && 'text-app-ink',
                )}
              >
                {course.isExpanded ? (
                  <ChevronDown
                    size={11}
                    className="shrink-0 text-app-ink/55 dark:text-app-ink/65"
                  />
                ) : (
                  <ChevronRight
                    size={11}
                    className="shrink-0 text-app-ink/55 dark:text-app-ink/65"
                  />
                )}
                <GraduationCap
                  size={13}
                  className={cn(
                    'shrink-0 text-app-ink/55 dark:text-app-ink/65',
                    course.isActive && 'text-app-accent',
                  )}
                />
                <span className="truncate">{course.title}</span>
              </button>
              <LazyMotion features={domAnimation}>
                <AnimatePresence initial={false}>
                  {course.isExpanded ? (
                    <m.div
                      key="content"
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.15 }}
                      className="overflow-hidden"
                    >
                      <LearningCourseParts course={course} />
                    </m.div>
                  ) : null}
                </AnimatePresence>
              </LazyMotion>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function LearningCourseParts({
  course,
}: {
  course: LearningSidebarCourseNode;
}) {
  return (
    <div className="ml-3 flex flex-col gap-3 border-l border-app-border pl-2">
      {course.parts.map((part) => (
        <section
          key={part.slug}
          aria-labelledby={`learning-tree-part-${part.slug}`}
        >
          <span
            id={`learning-tree-part-${part.slug}`}
            className="sidebar-section-label block px-2 py-0.5 text-app-ink/55"
          >
            {part.title}
          </span>
          <ol className="flex flex-col">
            {part.lessons.map((lesson) => {
              return (
                <li key={lesson.id}>
                  <Link
                    to={lesson.href}
                    data-testid={`learning-lesson-link-${lesson.slug}`}
                    className={cn(
                      'group flex items-start gap-2 rounded-md px-2 py-1 text-[12px] leading-5 transition-colors',
                      lesson.isActive
                        ? 'bg-app-accent/10 font-medium text-app-accent'
                        : 'text-app-ink/70 hover:bg-app-surface-hover hover:text-app-ink dark:text-app-ink/75',
                    )}
                  >
                    <span
                      className={cn(
                        'shrink-0 tabular-nums text-[12px] leading-5',
                        lesson.isActive
                          ? 'text-app-accent/80'
                          : 'text-app-ink/35',
                      )}
                    >
                      {lesson.positionLabel}
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
