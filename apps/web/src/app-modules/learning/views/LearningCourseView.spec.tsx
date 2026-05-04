import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { LearningCourseView } from './LearningCourseView';

type Lesson = { id: string; slug: string; title: string; file: string };
type Part = { slug: string; title: string; lessons: Lesson[] };
type Course = { slug: string; title: string; description: string; parts: Part[] };

vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({ token: null, user: null, status: 'authenticated' }),
}));

vi.mock('./learning-notes/LearningPageNotesPanel', () => ({
  LearningPageNotesPanel: ({ lessonId }: { lessonId: string }) => (
    <div data-testid={`learning-page-notes-panel-${lessonId}`} />
  ),
}));

const manifestHarness = vi.hoisted(() => ({
  courses: [] as Course[],
}));

const contentHarness = vi.hoisted(() => ({
  bodies: {} as Record<string, string>,
  assets: {} as Record<string, string>,
}));

vi.mock('../model/manifest', async () => {
  const actual = await vi.importActual<typeof import('../model/manifest')>(
    '../model/manifest',
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

vi.mock('../model/content', () => ({
  loadLessonBody: async (file: string) => contentHarness.bodies[file] ?? null,
  listAvailableLessonFiles: () => Object.keys(contentHarness.bodies),
  resolveLessonAsset: (_lessonFile: string, src: string | undefined) =>
    src ? (contentHarness.assets[src] ?? src) : src,
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
    contentHarness.assets = {};
  });

  it('renders the selected lesson body and wires prev/next across part boundaries', async () => {
    renderAt('/w/hq/learning/course/second');

    const body = await screen.findByTestId('learning-lesson-body-second');
    expect(body.textContent).toContain('두 번째 레슨 본문');

    // prev crosses a part boundary (intro → main)
    const prev = screen.getByTestId('learning-lesson-prev');
    expect(prev.getAttribute('href')).toBe('/w/hq/learning/course/first');
    const next = screen.getByTestId('learning-lesson-next');
    expect(next.getAttribute('href')).toBe('/w/hq/learning/course/third');
  });

  it('hides prev on the first lesson', async () => {
    renderAt('/w/hq/learning/course/first');
    await screen.findByTestId('learning-lesson-body-first');

    expect(screen.queryByTestId('learning-lesson-prev')).toBeNull();
    expect(screen.getByTestId('learning-lesson-next').getAttribute('href')).toBe(
      '/w/hq/learning/course/second',
    );
  });

  it('hides next on the last lesson', async () => {
    renderAt('/w/hq/learning/course/third');
    await screen.findByTestId('learning-lesson-body-third');

    expect(screen.getByTestId('learning-lesson-prev').getAttribute('href')).toBe(
      '/w/hq/learning/course/second',
    );
    expect(screen.queryByTestId('learning-lesson-next')).toBeNull();
  });

  it('redirects to the first lesson when the URL omits the lesson slug', async () => {
    renderAt('/w/hq/learning/course');
    await screen.findByTestId('learning-lesson-body-first');

    expect(screen.getByTestId('location').textContent).toBe(
      '/w/hq/learning/course/first',
    );
  });

  it('redirects to the course list when the course slug is unknown', () => {
    renderAt('/w/hq/learning/missing-course');
    expect(screen.getByTestId('learning-root')).toBeTruthy();
  });

  it('mounts the page notes panel with the lesson stable id', async () => {
    renderAt('/w/hq/learning/course/second');
    await screen.findByTestId('learning-lesson-body-second');

    expect(screen.getByTestId('learning-page-notes-panel-tc-002')).toBeTruthy();
  });

  it('resolves relative markdown image assets and leaves external image URLs alone', async () => {
    contentHarness.bodies['s.md'] = [
      '# 이미지 레슨',
      '',
      '![상대 이미지](assets/diagram.png)',
      '![외부 이미지](https://example.com/logo.svg)',
    ].join('\n');
    contentHarness.assets['assets/diagram.png'] = '/assets/diagram.hashed.png';

    renderAt('/w/hq/learning/course/second');
    await screen.findByTestId('learning-lesson-body-second');

    expect(screen.getByAltText('상대 이미지').getAttribute('src')).toBe(
      '/assets/diagram.hashed.png',
    );
    expect(screen.getByAltText('상대 이미지').getAttribute('loading')).toBe('lazy');
    expect(screen.getByAltText('외부 이미지').getAttribute('src')).toBe(
      'https://example.com/logo.svg',
    );
  });

  it('opens markdown images in an in-place preview dialog', async () => {
    contentHarness.bodies['s.md'] = [
      '# 이미지 레슨',
      '',
      '![상대 이미지](assets/diagram.png)',
    ].join('\n');
    contentHarness.assets['assets/diagram.png'] = '/assets/diagram.hashed.png';

    renderAt('/w/hq/learning/course/second');
    await screen.findByTestId('learning-lesson-body-second');

    fireEvent.click(screen.getByAltText('상대 이미지'));

    const dialog = screen.getByRole('dialog', { name: '상대 이미지' });
    expect(within(dialog).getByAltText('상대 이미지').getAttribute('src')).toBe(
      '/assets/diagram.hashed.png',
    );
    expect(screen.getByTestId('location').textContent).toBe(
      '/w/hq/learning/course/second',
    );
  });

  // Course/part/lesson navigation has moved to the app sub-sidebar
  // (see SubSidebar.tsx → LearningSubSidebarSection). LearningCourseView
  // itself no longer renders part headers or lesson links, so those
  // assertions are covered by the sub-sidebar tests instead.
});
