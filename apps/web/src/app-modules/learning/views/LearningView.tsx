import { motion } from 'motion/react';
import { GraduationCap, BookOpen } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { LEARNING_COURSES, getAllLessons } from '../model/manifest';

export function LearningView() {
  const { t } = useTranslation('apps');
  const { workspaceSlug } = useParams();
  const basePath = workspaceSlug ? `/w/${workspaceSlug}/learning` : '/learning';

  return (
    <motion.div
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
            const allLessons = getAllLessons(course);
            const first = allLessons[0];
            const target = first ? `${basePath}/${course.slug}/${first.slug}` : `${basePath}/${course.slug}`;
            return (
              <Link
                key={course.slug}
                to={target}
                className="group flex flex-col gap-3 rounded-lg border border-app-border bg-app-surface p-5 transition-colors hover:border-app-accent"
                data-testid={`learning-course-${course.slug}`}
              >
                <div className="flex items-center gap-2 text-app-ink/60">
                  <BookOpen size={16} />
                  <span className="app-text-overline">{t('learning.lessonCount', { count: allLessons.length })}</span>
                </div>
                <h2 className="app-text-title font-semibold text-app-ink">
                  {course.title}
                </h2>
                <p className="app-text-body-sm text-app-ink/70">{course.description}</p>
                <span className="mt-auto app-text-control text-app-accent group-hover:underline">
                  {t('learning.start')} →
                </span>
              </Link>
            );
          })}
        </section>
      )}
    </motion.div>
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
