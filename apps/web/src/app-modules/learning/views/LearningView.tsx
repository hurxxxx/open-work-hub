import { LazyMotion, domAnimation, m } from 'motion/react';
import { GraduationCap, BookOpen } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { LEARNING_COURSES, getAllLessons } from '../model/manifest';

type LearningCourse = (typeof LEARNING_COURSES)[number];

export interface LearningCourseCardModel {
  description: string;
  lessonCount: number;
  slug: string;
  target: string;
  title: string;
}

export function buildLearningCourseCardModel({
  basePath,
  course,
}: {
  basePath: string;
  course: LearningCourse;
}): LearningCourseCardModel {
  const allLessons = getAllLessons(course);
  const firstLesson = allLessons[0];
  return {
    description: course.description,
    lessonCount: allLessons.length,
    slug: course.slug,
    target: firstLesson
      ? `${basePath}/${course.slug}/${firstLesson.slug}`
      : `${basePath}/${course.slug}`,
    title: course.title,
  };
}

export function LearningView() {
  const { t } = useTranslation('apps');
  const { workspaceSlug } = useParams();
  const basePath = workspaceSlug ? `/w/${workspaceSlug}/learning` : '/learning';

  return (
    <LazyMotion features={domAnimation}>
      <m.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="mx-auto flex w-full max-w-7xl flex-col gap-8 p-6 lg:p-8"
      >
      <header className="flex flex-col gap-2">
        <div className="flex items-center gap-2 text-app-ink/60">
          <GraduationCap size={18} />
          <span className="app-text-overline">{t('learning.title')}</span>
        </div>
        <h1 className="app-text-display text-app-ink">{t('learning.allCourses')}</h1>
        <p className="app-text-body text-app-ink/70">
          {t('learning.subtitle')}
        </p>
      </header>

      {LEARNING_COURSES.length === 0 ? (
        <EmptyCourses />
      ) : (
        <section
          aria-label={t('learning.courseList')}
          className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3"
        >
          {LEARNING_COURSES.map((course) => {
            const card = buildLearningCourseCardModel({ basePath, course });
            return (
              <Link
                key={card.slug}
                to={card.target}
                className="group flex flex-col gap-3 rounded-lg border border-app-border bg-app-surface p-5 transition-colors hover:border-app-accent"
                data-testid={`learning-course-${card.slug}`}
              >
                <div className="flex items-center gap-2 text-app-ink/60">
                  <BookOpen size={16} />
                  <span className="app-text-overline">
                    {t('learning.lessonCount', { count: card.lessonCount })}
                  </span>
                </div>
                <h2 className="app-text-title font-semibold text-app-ink">
                  {card.title}
                </h2>
                <p className="app-text-body-sm text-app-ink/70">
                  {card.description}
                </p>
                <span className="mt-auto app-text-control text-app-accent group-hover:underline">
                  {t('learning.start')} →
                </span>
              </Link>
            );
          })}
        </section>
      )}
      </m.div>
    </LazyMotion>
  );
}

function EmptyCourses() {
  const { t } = useTranslation('apps');
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-app-border bg-app-surface p-12 text-center">
      <GraduationCap size={28} className="text-app-ink/40" />
      <p className="app-text-body text-app-ink/70">
        {t('learning.emptyCourses')}
      </p>
    </div>
  );
}
