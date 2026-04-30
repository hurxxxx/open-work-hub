import { describe, expect, it } from 'vitest';

import { LEARNING_COURSES, findCourse, findLesson, getAllLessons } from './manifest';
import { getLessonBody, listAvailableLessonFiles } from './content';

describe('LEARNING_COURSES manifest', () => {
  it('has at least one course and matches the shipped content', () => {
    expect(LEARNING_COURSES.length).toBeGreaterThan(0);
  });

  it('each lesson.file resolves to a non-empty markdown body', () => {
    const availableFiles = new Set(listAvailableLessonFiles());
    for (const course of LEARNING_COURSES) {
      for (const lesson of getAllLessons(course)) {
        expect(availableFiles, `missing file in content map: ${lesson.file}`).toContain(
          lesson.file,
        );
        const body = getLessonBody(lesson.file);
        expect(body, `empty body for ${lesson.file}`).toBeTruthy();
        if (!body) {
          throw new Error(`empty body for ${lesson.file}`);
        }
        expect(body.length).toBeGreaterThan(0);
      }
    }
  });

  it('has unique slugs per course and per lesson within a course', () => {
    const courseSlugs = new Set<string>();
    for (const course of LEARNING_COURSES) {
      expect(courseSlugs.has(course.slug)).toBe(false);
      courseSlugs.add(course.slug);

      const lessonSlugs = new Set<string>();
      for (const lesson of getAllLessons(course)) {
        expect(lessonSlugs.has(lesson.slug)).toBe(false);
        lessonSlugs.add(lesson.slug);
      }
    }
  });

  it('every lesson has a non-empty stable id', () => {
    for (const course of LEARNING_COURSES) {
      for (const lesson of getAllLessons(course)) {
        expect(lesson.id, `lesson "${lesson.slug}" is missing an id`).toBeTruthy();
        expect(typeof lesson.id).toBe('string');
        expect(lesson.id.length).toBeGreaterThan(0);
      }
    }
  });

  it('lesson ids are unique within each course', () => {
    for (const course of LEARNING_COURSES) {
      const ids = new Set<string>();
      for (const lesson of getAllLessons(course)) {
        expect(ids.has(lesson.id), `duplicate lesson id "${lesson.id}" in course "${course.slug}"`).toBe(
          false,
        );
        ids.add(lesson.id);
      }
    }
  });

  it('has unique part slugs per course and each part holds at least one lesson', () => {
    for (const course of LEARNING_COURSES) {
      expect(course.parts.length).toBeGreaterThan(0);
      const partSlugs = new Set<string>();
      for (const part of course.parts) {
        expect(partSlugs.has(part.slug)).toBe(false);
        partSlugs.add(part.slug);
        expect(part.lessons.length).toBeGreaterThan(0);
      }
    }
  });

  it('findCourse + findLesson roundtrip', () => {
    const course = LEARNING_COURSES[0];
    const resolved = findCourse(course.slug);
    expect(resolved?.slug).toBe(course.slug);
    const first = getAllLessons(course)[0];
    const located = findLesson(course, first.slug);
    expect(located?.lesson.slug).toBe(first.slug);
    expect(located?.index).toBe(0);
    expect(findLesson(course, 'no-such-lesson')).toBeNull();
  });

  it('findLesson returns the global flat index across part boundaries', () => {
    const course = LEARNING_COURSES[0];
    const all = getAllLessons(course);
    if (all.length < 2) return;
    const last = all[all.length - 1];
    const located = findLesson(course, last.slug);
    expect(located?.index).toBe(all.length - 1);
  });
});
