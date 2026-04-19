import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { EmptyState } from './EmptyState';

function renderEmptyState(composer: React.ReactNode = <div data-testid="composer" />) {
  return render(
    <MemoryRouter>
      <EmptyState composer={composer} />
    </MemoryRouter>,
  );
}

describe('EmptyState', () => {
  it('renders the default Korean greeting', () => {
    renderEmptyState();
    expect(screen.getByText('안녕하세요, 업무를 도와드릴게요.')).not.toBeNull();
  });

  it('renders the composer slot in the center', () => {
    renderEmptyState(<div data-testid="custom-composer">composer here</div>);
    expect(screen.getByTestId('custom-composer')).not.toBeNull();
  });

  it('renders four suggestion cards linking to tool routes', () => {
    renderEmptyState();
    const suggestions = ['아이두 통합검색', 'FMEA 비교', '기안 초안', '문서 번역/요약'];
    for (const label of suggestions) {
      expect(screen.getByText(label)).not.toBeNull();
    }
    // All four suggestion anchors point to /tool/:id routes.
    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(4);
    for (const link of links) {
      expect(link.getAttribute('href')).toMatch(/^\/tool\//);
    }
  });

  it('allows overriding greeting and subline copy', () => {
    render(
      <MemoryRouter>
        <EmptyState
          composer={<div />}
          greeting="다시 오셨군요"
          subline="도와드릴 작업을 알려주세요"
        />
      </MemoryRouter>,
    );
    expect(screen.getByText('다시 오셨군요')).not.toBeNull();
    expect(screen.getByText('도와드릴 작업을 알려주세요')).not.toBeNull();
  });
});
