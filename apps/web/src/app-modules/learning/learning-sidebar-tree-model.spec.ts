import { describe, expect, it } from 'vitest';

import type { LearningCourse, LearningLesson } from './model/manifest';
import {
  buildLearningLessonHref,
  buildLearningSidebarTree,
  getLearningSidebarExpandedCourses,
  parseLearningSidebarPathname,
} from './learning-sidebar-tree-model';

function lesson(id: string, slug: string, title = slug): LearningLesson {
  return {
    id,
    slug,
    title,
    file: `${slug}.md`,
  };
}

const firstLesson = lesson('lesson-1', 'first', 'First lesson');
const secondLesson = lesson('lesson-2', 'second', 'Second lesson');
const otherSecondLesson = lesson('lesson-3', 'second', 'Other second lesson');

const courses: LearningCourse[] = [
  {
    slug: 'course-one',
    title: 'Course One',
    description: '',
    parts: [
      {
        slug: 'intro',
        title: 'Intro',
        lessons: [firstLesson, secondLesson],
      },
      {
        slug: 'next',
        title: 'Next',
        lessons: [lesson('lesson-4', 'third')],
      },
    ],
  },
  {
    slug: 'course-two',
    title: 'Course Two',
    description: '',
    parts: [
      {
        slug: 'main',
        title: 'Main',
        lessons: [otherSecondLesson],
      },
    ],
  },
];

describe('learning sidebar tree model', () => {
  it('parses workspace learning path segments', () => {
    expect(
      parseLearningSidebarPathname('/w/team/learning/course-one/second'),
    ).toEqual({
      workspaceSlug: 'team',
      courseSlug: 'course-one',
      lessonSlug: 'second',
    });
    expect(parseLearningSidebarPathname('/w/team/learning')).toEqual({
      workspaceSlug: 'team',
      courseSlug: null,
      lessonSlug: null,
    });
  });

  it('leaves non-workspace learning routes inactive', () => {
    expect(parseLearningSidebarPathname('/learning/course-one/second')).toEqual(
      {
        workspaceSlug: null,
        courseSlug: null,
        lessonSlug: null,
      },
    );
  });

  it('expands the active course and applies explicit overrides last', () => {
    expect(
      Array.from(
        getLearningSidebarExpandedCourses({
          activeCourseSlug: 'course-one',
          expansionOverrides: {
            'course-one': false,
            'course-two': true,
          },
        }),
      ),
    ).toEqual(['course-two']);
  });

  it('projects active course, active lesson, hrefs, and per-part labels', () => {
    const tree = buildLearningSidebarTree({
      courses,
      currentPathname: '/w/team/learning/course-one/second',
      expansionOverrides: {},
    });

    expect(tree).toMatchObject({
      activeWorkspaceSlug: 'team',
      activeCourseSlug: 'course-one',
      activeLessonSlug: 'second',
    });
    expect(
      tree.courses.map((course) => ({
        slug: course.slug,
        isActive: course.isActive,
        isExpanded: course.isExpanded,
      })),
    ).toEqual([
      { slug: 'course-one', isActive: true, isExpanded: true },
      { slug: 'course-two', isActive: false, isExpanded: false },
    ]);
    expect(tree.courses[0].parts[0].lessons).toMatchObject([
      {
        id: firstLesson.id,
        href: '/w/team/learning/course-one/first',
        positionLabel: '01',
        isActive: false,
      },
      {
        id: secondLesson.id,
        href: '/w/team/learning/course-one/second',
        positionLabel: '02',
        isActive: true,
      },
    ]);
    expect(tree.courses[0].parts[1].lessons[0].positionLabel).toBe('01');
    expect(tree.courses[1].parts[0].lessons[0].isActive).toBe(false);
  });

  it('lets expansion overrides collapse an active course', () => {
    const tree = buildLearningSidebarTree({
      courses,
      currentPathname: '/w/team/learning/course-one/second',
      expansionOverrides: {
        'course-one': false,
      },
    });

    expect(tree.courses[0]).toMatchObject({
      slug: 'course-one',
      isActive: true,
      isExpanded: false,
    });
  });

  it('builds bare learning hrefs when there is no workspace', () => {
    expect(
      buildLearningSidebarTree({
        courses,
        currentPathname: '/settings',
        expansionOverrides: {},
      }).courses[0].parts[0].lessons[0].href,
    ).toBe('/learning/course-one/first');
  });

  it('encodes workspace slugs when building lesson hrefs', () => {
    expect(
      buildLearningLessonHref({
        workspaceSlug: 'team space',
        courseSlug: 'course-one',
        lessonSlug: 'first',
      }),
    ).toBe('/w/team%20space/learning/course-one/first');
  });
});
