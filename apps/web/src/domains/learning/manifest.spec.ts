import { describe, expect, it } from 'vitest';

import { LEARNING_COURSES, findCourse, findLesson } from './manifest';
import { getLessonBody, listAvailableLessonFiles } from './content';

describe('LEARNING_COURSES manifest', () => {
  it('has at least one course and matches the shipped content', () => {
    expect(LEARNING_COURSES.length).toBeGreaterThan(0);
  });

  it('each lesson.file resolves to a non-empty markdown body', () => {
    const availableFiles = new Set(listAvailableLessonFiles());
    for (const course of LEARNING_COURSES) {
      for (const lesson of course.lessons) {
        expect(availableFiles, `missing file in content map: ${lesson.file}`).toContain(
          lesson.file,
        );
        const body = getLessonBody(lesson.file);
        expect(body, `empty body for ${lesson.file}`).toBeTruthy();
        expect(body!.length).toBeGreaterThan(0);
      }
    }
  });

  it('has unique slugs per course and per lesson within a course', () => {
    const courseSlugs = new Set<string>();
    for (const course of LEARNING_COURSES) {
      expect(courseSlugs.has(course.slug)).toBe(false);
      courseSlugs.add(course.slug);

      const lessonSlugs = new Set<string>();
      for (const lesson of course.lessons) {
        expect(lessonSlugs.has(lesson.slug)).toBe(false);
        lessonSlugs.add(lesson.slug);
      }
    }
  });

  it('findCourse + findLesson roundtrip', () => {
    const course = LEARNING_COURSES[0];
    const resolved = findCourse(course.slug);
    expect(resolved?.slug).toBe(course.slug);
    const first = course.lessons[0];
    const located = findLesson(course, first.slug);
    expect(located?.lesson.slug).toBe(first.slug);
    expect(located?.index).toBe(0);
    expect(findLesson(course, 'no-such-lesson')).toBeNull();
  });
});
