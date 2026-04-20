import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { ArtifactBuffer } from '@/src/domains/ai/agent-events';

import { ArtifactCard } from './ArtifactCard';

function buildArtifact(
  overrides: Partial<ArtifactBuffer> = {},
): ArtifactBuffer {
  return {
    id: 'a-1',
    type: 'document',
    title: '제안서 초안',
    content: '# 초안\n본문 내용입니다',
    status: 'closed',
    ...overrides,
  };
}

describe('ArtifactCard', () => {
  it('renders title and first-line preview for a closed artifact', () => {
    render(
      <ArtifactCard
        artifact={buildArtifact()}
        isActive={false}
        onOpen={vi.fn()}
      />,
    );
    expect(screen.getByText('제안서 초안')).not.toBeNull();
    // Preview strips the leading markdown token and uses the first real line.
    expect(screen.getByText('초안')).not.toBeNull();
    expect(screen.getByText('열기')).not.toBeNull();
  });

  it('shows a streaming label while the artifact is still open', () => {
    render(
      <ArtifactCard
        artifact={buildArtifact({ status: 'open', content: 'partial…' })}
        isActive={false}
        onOpen={vi.fn()}
      />,
    );
    expect(screen.getByText('생성 중…')).not.toBeNull();
  });

  it('falls back to a placeholder title when the model omitted one', () => {
    render(
      <ArtifactCard
        artifact={buildArtifact({ title: null })}
        isActive={false}
        onOpen={vi.fn()}
      />,
    );
    expect(screen.getByText('(제목 없는 문서)')).not.toBeNull();
  });

  it('invokes onOpen with the artifact id when clicked', () => {
    const onOpen = vi.fn();
    render(
      <ArtifactCard
        artifact={buildArtifact()}
        isActive={false}
        onOpen={onOpen}
      />,
    );
    fireEvent.click(screen.getByTestId('artifact-card-a-1'));
    expect(onOpen).toHaveBeenCalledWith('a-1');
  });

  it('marks the active artifact visibly with a pressed attribute and accent border', () => {
    render(
      <ArtifactCard
        artifact={buildArtifact()}
        isActive
        onOpen={vi.fn()}
      />,
    );
    const button = screen.getByTestId('artifact-card-a-1');
    expect(button.getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByText('열림')).not.toBeNull();
  });
});
