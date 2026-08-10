import { LEARNING_COURSES, type LearningCourse } from './model/manifest';

export interface LearningPathState {
  workspaceSlug: string | null;
  courseSlug: string | null;
  lessonSlug: string | null;
}

export type LearningSidebarExpansionOverrides = Record<string, boolean>;

export interface LearningSidebarLessonNode {
  id: string;
  slug: string;
  title: string;
  href: string;
  positionLabel: string;
  isActive: boolean;
}

export interface LearningSidebarPartNode {
  slug: string;
  title: string;
  lessons: LearningSidebarLessonNode[];
}

export interface LearningSidebarCourseNode {
  slug: string;
  title: string;
  isActive: boolean;
  isExpanded: boolean;
  parts: LearningSidebarPartNode[];
}

export interface LearningSidebarTreeModel {
  activeWorkspaceSlug: string | null;
  activeCourseSlug: string | null;
  activeLessonSlug: string | null;
  courses: LearningSidebarCourseNode[];
}

export function parseLearningSidebarPathname(
  pathname: string,
): LearningPathState {
  const match = pathname.match(
    /^\/w\/([^/]+)\/learning(?:\/([^/]+)(?:\/([^/]+))?)?/,
  );
  return {
    workspaceSlug: match?.[1] ?? null,
    courseSlug: match?.[2] ?? null,
    lessonSlug: match?.[3] ?? null,
  };
}

export function getLearningSidebarExpandedCourses({
  activeCourseSlug,
  expansionOverrides,
}: {
  activeCourseSlug: string | null;
  expansionOverrides: LearningSidebarExpansionOverrides;
}): Set<string> {
  const expandedCourses = new Set<string>();
  if (activeCourseSlug) expandedCourses.add(activeCourseSlug);

  for (const [slug, expanded] of Object.entries(expansionOverrides)) {
    if (expanded) {
      expandedCourses.add(slug);
    } else {
      expandedCourses.delete(slug);
    }
  }

  return expandedCourses;
}

export function buildLearningLessonHref({
  workspaceSlug,
  courseSlug,
  lessonSlug,
}: {
  workspaceSlug: string | null;
  courseSlug: string;
  lessonSlug: string;
}): string {
  const encodedWorkspace = workspaceSlug
    ? encodeURIComponent(workspaceSlug)
    : '';
  return encodedWorkspace
    ? `/w/${encodedWorkspace}/learning/${courseSlug}/${lessonSlug}`
    : `/learning/${courseSlug}/${lessonSlug}`;
}

export function buildLearningSidebarTree({
  courses = LEARNING_COURSES,
  currentPathname,
  expansionOverrides,
}: {
  courses?: LearningCourse[];
  currentPathname: string;
  expansionOverrides: LearningSidebarExpansionOverrides;
}): LearningSidebarTreeModel {
  const {
    workspaceSlug: activeWorkspaceSlug,
    courseSlug: activeCourseSlug,
    lessonSlug: activeLessonSlug,
  } = parseLearningSidebarPathname(currentPathname);
  const expandedCourses = getLearningSidebarExpandedCourses({
    activeCourseSlug,
    expansionOverrides,
  });

  return {
    activeWorkspaceSlug,
    activeCourseSlug,
    activeLessonSlug,
    courses: courses.map((course) => {
      const isActiveCourse = course.slug === activeCourseSlug;
      return {
        slug: course.slug,
        title: course.title,
        isActive: isActiveCourse,
        isExpanded: expandedCourses.has(course.slug),
        parts: course.parts.map((part) => ({
          slug: part.slug,
          title: part.title,
          lessons: part.lessons.map((lesson, idx) => ({
            id: lesson.id,
            slug: lesson.slug,
            title: lesson.title,
            href: buildLearningLessonHref({
              workspaceSlug: activeWorkspaceSlug,
              courseSlug: course.slug,
              lessonSlug: lesson.slug,
            }),
            positionLabel: String(idx + 1).padStart(2, '0'),
            isActive: isActiveCourse && lesson.slug === activeLessonSlug,
          })),
        })),
      };
    }),
  };
}
