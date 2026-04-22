import { motion } from 'motion/react';
import { GraduationCap, BookOpen } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';

import { LEARNING_COURSES, getAllLessons } from '@/src/domains/learning/manifest';

export function LearningView() {
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
          <span className="app-text-overline">학습</span>
        </div>
        <h1 className="app-text-display text-app-ink">전체 코스</h1>
        <p className="app-text-body text-app-ink/70">
          모든 구성원이 열람할 수 있는 교육 콘텐츠 모음입니다. 새 코스가 준비되면 여기에 추가됩니다.
        </p>
      </header>

      {LEARNING_COURSES.length === 0 ? (
        <EmptyCourses />
      ) : (
        <section
          aria-label="코스 목록"
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
                  <span className="app-text-overline">{allLessons.length}개 레슨</span>
                </div>
                <h2 className="app-text-title font-semibold text-app-ink">
                  {course.title}
                </h2>
                <p className="app-text-body-sm text-app-ink/70">{course.description}</p>
                <span className="mt-auto app-text-control text-app-accent group-hover:underline">
                  시작하기 →
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
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-app-border bg-app-surface p-12 text-center">
      <GraduationCap size={28} className="text-app-ink/40" />
      <p className="app-text-body text-app-ink/70">
        콘텐츠가 준비되는 대로 이 공간에 게시됩니다.
      </p>
    </div>
  );
}
