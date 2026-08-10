import { describe, expect, it } from 'vitest';

import {
  resolveLearningCourseRoute,
  type LearningCourseRouteModelDeps,
} from './learning-course-route-model';
import type { LearningCourse, LearningLesson } from '../model/manifest';

const firstLesson: LearningLesson = {
  id: 'tc-001',
  slug: 'first',
  title: 'First lesson',
  file: 'first.md',
};

const secondLesson: LearningLesson = {
  id: 'tc-002',
  slug: 'second',
  title: 'Second lesson',
  file: 'second.md',
};

const thirdLesson: LearningLesson = {
  id: 'tc-003',
  slug: 'third',
  title: 'Third lesson',
  file: 'third.md',
};

const course: LearningCourse = {
  slug: 'course',
  title: 'Course',
  description: '',
  parts: [
    {
      slug: 'intro',
      title: 'Intro',
      lessons: [firstLesson],
    },
    {
      slug: 'main',
      title: 'Main',
      lessons: [secondLesson, thirdLesson],
    },
  ],
};

const emptyCourse: LearningCourse = {
  slug: 'empty-course',
  title: 'Empty course',
  description: '',
  parts: [],
};

function createDeps(courses: LearningCourse[]): LearningCourseRouteModelDeps {
  return {
    findCourse: (slug) =>
      courses.find((candidate) => candidate.slug === slug) ?? null,
    getAllLessons: (selectedCourse) =>
      selectedCourse.parts.flatMap((part) => part.lessons),
  };
}

describe('learning course route model', () => {
  const deps = createDeps([course, emptyCourse]);

  it('redirects unknown courses to the learning root', () => {
    expect(
      resolveLearningCourseRoute(
        { workspaceSlug: 'hq', courseSlug: 'missing' },
        deps,
      ),
    ).toEqual({ kind: 'redirect', to: '/w/hq/learning' });
  });

  it('redirects course landing URLs to the first lesson', () => {
    expect(
      resolveLearningCourseRoute(
        { workspaceSlug: 'hq', courseSlug: 'course' },
        deps,
      ),
    ).toEqual({
      kind: 'redirect',
      to: '/w/hq/learning/course/first',
    });
  });

  it('returns the empty course layout model when a course has no lessons', () => {
    expect(
      resolveLearningCourseRoute(
        { workspaceSlug: 'hq', courseSlug: 'empty-course' },
        deps,
      ),
    ).toEqual({
      kind: 'emptyCourse',
      course: emptyCourse,
      basePath: '/w/hq/learning',
    });
  });

  it('redirects unknown lessons back to the course landing URL', () => {
    expect(
      resolveLearningCourseRoute(
        {
          workspaceSlug: 'hq',
          courseSlug: 'course',
          lessonSlug: 'missing',
        },
        deps,
      ),
    ).toEqual({
      kind: 'redirect',
      to: '/w/hq/learning/course',
    });
  });

  it('resolves the lesson layout model with prev and next lessons', () => {
    expect(
      resolveLearningCourseRoute(
        {
          workspaceSlug: 'hq',
          courseSlug: 'course',
          lessonSlug: 'second',
        },
        deps,
      ),
    ).toEqual({
      kind: 'lesson',
      course,
      lesson: secondLesson,
      index: 1,
      total: 3,
      basePath: '/w/hq/learning',
      prev: firstLesson,
      next: thirdLesson,
    });
  });

  it('resolves bare learning URLs without a workspace prefix', () => {
    expect(
      resolveLearningCourseRoute(
        { courseSlug: 'course', lessonSlug: 'first' },
        deps,
      ),
    ).toMatchObject({
      kind: 'lesson',
      basePath: '/learning',
      prev: null,
      next: secondLesson,
    });
  });
});
