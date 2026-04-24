import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { LearningCourseView } from './LearningCourseView';

type Lesson = { id: string; slug: string; title: string; file: string };
type Part = { slug: string; title: string; lessons: Lesson[] };
type Course = { slug: string; title: string; description: string; parts: Part[] };

vi.mock('@/src/domains/auth/auth-provider', () => ({
  useAuth: () => ({ token: null, user: null, status: 'authenticated' }),
}));

vi.mock('./learning-notes/LearningPageNotesPanel', () => ({
  LearningPageNotesPanel: ({ lessonId }: { lessonId: string }) => (
    <div data-testid={`learning-page-notes-panel-${lessonId}`} />
  ),
}));

vi.mock('./learning-toc/LearningTocPopover', () => ({
  LearningTocPopover: ({
    lessonSlug,
    progressLabel,
  }: {
    lessonSlug: string;
    progressLabel?: string;
  }) => (
    <div data-testid={`learning-toc-trigger-${lessonSlug}`}>{progressLabel}</div>
  ),
}));

const manifestHarness = vi.hoisted(() => ({
  courses: [] as Course[],
}));

const contentHarness = vi.hoisted(() => ({
  bodies: {} as Record<string, string>,
}));

vi.mock('@/src/domains/learning/manifest', async () => {
  const actual = await vi.importActual<typeof import('@/src/domains/learning/manifest')>(
    '@/src/domains/learning/manifest',
  );
  const flatten = (course: Course) => course.parts.flatMap((part) => part.lessons);
  return {
    ...actual,
    get LEARNING_COURSES() {
      return manifestHarness.courses;
    },
    findCourse(slug: string) {
      return manifestHarness.courses.find((course) => course.slug === slug) ?? null;
    },
    getAllLessons: flatten,
    findLesson(course: Course, lessonSlug: string) {
      const all = flatten(course);
      const index = all.findIndex((lesson) => lesson.slug === lessonSlug);
      if (index < 0) return null;
      return { lesson: all[index], index };
    },
  };
});

vi.mock('@/src/domains/learning/content', () => ({
  getLessonBody: (file: string) => contentHarness.bodies[file] ?? null,
  listAvailableLessonFiles: () => Object.keys(contentHarness.bodies),
}));

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="/w/:workspaceSlug/learning"
          element={<div data-testid="learning-root" />}
        />
        <Route
          path="/w/:workspaceSlug/learning/:courseSlug"
          element={<LearningCourseView />}
        />
        <Route
          path="/w/:workspaceSlug/learning/:courseSlug/:lessonSlug"
          element={<LearningCourseView />}
        />
      </Routes>
      <LocationProbe />
    </MemoryRouter>,
  );
}

describe('LearningCourseView', () => {
  beforeEach(() => {
    manifestHarness.courses = [
      {
        slug: 'course',
        title: '테스트 코스',
        description: '',
        parts: [
          {
            slug: 'intro',
            title: '시작하기',
            lessons: [{ id: 'tc-001', slug: 'first', title: '첫 레슨', file: 'f.md' }],
          },
          {
            slug: 'main',
            title: '본편',
            lessons: [
              { id: 'tc-002', slug: 'second', title: '두 번째 레슨', file: 's.md' },
              { id: 'tc-003', slug: 'third', title: '세 번째 레슨', file: 't.md' },
            ],
          },
        ],
      },
    ];
    contentHarness.bodies = {
      'f.md': '# 첫 레슨 본문\n\n내용 1.',
      's.md': '# 두 번째 레슨 본문\n\n내용 2.',
      't.md': '# 세 번째 레슨 본문\n\n내용 3.',
    };
  });

  it('renders the selected lesson body and wires prev/next across part boundaries', () => {
    renderAt('/w/hq/learning/course/second');

    const body = screen.getByTestId('learning-lesson-body-second');
    expect(body.textContent).toContain('두 번째 레슨 본문');

    // prev crosses a part boundary (intro → main)
    const prev = screen.getByTestId('learning-lesson-prev');
    expect(prev.getAttribute('href')).toBe('/w/hq/learning/course/first');
    const next = screen.getByTestId('learning-lesson-next');
    expect(next.getAttribute('href')).toBe('/w/hq/learning/course/third');
  });

  it('hides prev on the first lesson', () => {
    renderAt('/w/hq/learning/course/first');
    expect(screen.queryByTestId('learning-lesson-prev')).toBeNull();
    expect(screen.getByTestId('learning-lesson-next').getAttribute('href')).toBe(
      '/w/hq/learning/course/second',
    );
  });

  it('hides next on the last lesson', () => {
    renderAt('/w/hq/learning/course/third');
    expect(screen.getByTestId('learning-lesson-prev').getAttribute('href')).toBe(
      '/w/hq/learning/course/second',
    );
    expect(screen.queryByTestId('learning-lesson-next')).toBeNull();
  });

  it('redirects to the first lesson when the URL omits the lesson slug', () => {
    renderAt('/w/hq/learning/course');
    expect(screen.getByTestId('location').textContent).toBe(
      '/w/hq/learning/course/first',
    );
  });

  it('redirects to the course list when the course slug is unknown', () => {
    renderAt('/w/hq/learning/missing-course');
    expect(screen.getByTestId('learning-root')).toBeTruthy();
  });

  it('mounts the page notes panel with the lesson stable id', () => {
    renderAt('/w/hq/learning/course/second');
    expect(screen.getByTestId('learning-page-notes-panel-tc-002')).toBeTruthy();
  });

  // Course/part/lesson navigation has moved to the app sub-sidebar
  // (see SubSidebar.tsx → LearningSubSidebarSection). LearningCourseView
  // itself no longer renders part headers or lesson links, so those
  // assertions are covered by the sub-sidebar tests instead.
});
