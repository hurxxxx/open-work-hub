import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { LearningView } from './LearningView';

type Lesson = { slug: string; title: string; file: string };
type Part = { slug: string; title: string; lessons: Lesson[] };
type Course = { slug: string; title: string; description: string; parts: Part[] };

const manifestHarness = vi.hoisted(() => ({
  courses: [] as Course[],
}));

vi.mock('../model/manifest', () => ({
  get LEARNING_COURSES() {
    return manifestHarness.courses;
  },
  getAllLessons: (course: Course) => course.parts.flatMap((part) => part.lessons),
}));

function renderView() {
  return render(
    <MemoryRouter initialEntries={['/w/hq/learning']}>
      <Routes>
        <Route path="/w/:workspaceSlug/learning" element={<LearningView />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('LearningView', () => {
  beforeEach(() => {
    manifestHarness.courses = [];
  });

  it('renders the empty state when no courses are available', () => {
    renderView();
    expect(
      screen.getByText('콘텐츠가 준비되는 대로 이 공간에 게시됩니다.'),
    ).toBeTruthy();
  });

  it('renders a card per course with a link into the first lesson', () => {
    manifestHarness.courses = [
      {
        slug: 'course-a',
        title: '코스 A',
        description: '첫 번째 코스',
        parts: [
          {
            slug: 'intro',
            title: '시작하기',
            lessons: [{ slug: 'lesson-1', title: '레슨 1', file: 'a-1.md' }],
          },
          {
            slug: 'main',
            title: '본편',
            lessons: [{ slug: 'lesson-2', title: '레슨 2', file: 'a-2.md' }],
          },
        ],
      },
      {
        slug: 'course-b',
        title: '코스 B',
        description: '두 번째 코스',
        parts: [
          {
            slug: 'only',
            title: '전체',
            lessons: [{ slug: 'only', title: '유일 레슨', file: 'b-1.md' }],
          },
        ],
      },
    ];

    renderView();

    const cardA = screen.getByTestId('learning-course-course-a');
    expect(cardA.textContent).toContain('코스 A');
    expect(cardA.textContent).toContain('2개 레슨');
    expect(cardA.getAttribute('href')).toBe('/w/hq/learning/course-a/lesson-1');

    const cardB = screen.getByTestId('learning-course-course-b');
    expect(cardB.getAttribute('href')).toBe('/w/hq/learning/course-b/only');
  });
});
