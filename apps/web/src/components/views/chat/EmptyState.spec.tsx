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

  it('does not render any tool suggestion cards', () => {
    // The chat empty state used to seed four legacy "tool" shortcuts
    // (search/FMEA/draft/translate). Those have been removed because the
    // chatbot is the entry point now — context selection happens in the
    // ChatTopBar scope picker, not via these cards.
    renderEmptyState();
    expect(screen.queryAllByRole('link')).toHaveLength(0);
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
