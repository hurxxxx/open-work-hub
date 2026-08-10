import {
  findCourse as findCourseFromManifest,
  getAllLessons as getAllLessonsFromManifest,
  type LearningCourse,
  type LearningLesson,
} from '../model/manifest';

export type LearningCourseRoute =
  | { kind: 'redirect'; to: string }
  | { kind: 'emptyCourse'; course: LearningCourse; basePath: string }
  | {
      kind: 'lesson';
      course: LearningCourse;
      lesson: LearningLesson;
      index: number;
      total: number;
      basePath: string;
      prev: LearningLesson | null;
      next: LearningLesson | null;
    };

export type LearningCourseRouteModelDeps = {
  findCourse: (slug: string) => LearningCourse | null;
  getAllLessons: (course: LearningCourse) => LearningLesson[];
};

const DEFAULT_DEPS = {
  findCourse: findCourseFromManifest,
  getAllLessons: getAllLessonsFromManifest,
} satisfies LearningCourseRouteModelDeps;

export function resolveLearningCourseRoute(
  {
    workspaceSlug,
    courseSlug,
    lessonSlug,
  }: {
    workspaceSlug?: string;
    courseSlug?: string;
    lessonSlug?: string;
  },
  deps: LearningCourseRouteModelDeps = DEFAULT_DEPS,
): LearningCourseRoute {
  const basePath = workspaceSlug ? `/w/${workspaceSlug}/learning` : '/learning';
  const course = courseSlug ? deps.findCourse(courseSlug) : null;

  if (!course) {
    return { kind: 'redirect', to: basePath };
  }

  const allLessons = deps.getAllLessons(course);

  if (!lessonSlug) {
    const first = allLessons[0] ?? null;
    if (!first) {
      return { kind: 'emptyCourse', course, basePath };
    }
    return {
      kind: 'redirect',
      to: `${basePath}/${course.slug}/${first.slug}`,
    };
  }

  const index = allLessons.findIndex((lesson) => lesson.slug === lessonSlug);
  if (index < 0) {
    return { kind: 'redirect', to: `${basePath}/${course.slug}` };
  }

  return {
    kind: 'lesson',
    course,
    lesson: allLessons[index],
    index,
    total: allLessons.length,
    basePath,
    prev: index > 0 ? allLessons[index - 1] : null,
    next: index < allLessons.length - 1 ? allLessons[index + 1] : null,
  };
}
