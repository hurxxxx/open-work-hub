import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { ArtifactBuffer } from '@/src/domains/ai/agent-events';

import { ArtifactPanel } from './ArtifactPanel';

function buildArtifact(
  overrides: Partial<ArtifactBuffer> = {},
): ArtifactBuffer {
  return {
    id: 'a-1',
    type: 'document',
    title: 'Draft Email',
    content: '# Hello\n\nThis is the body with **bold** text.',
    status: 'closed',
    ...overrides,
  };
}

describe('ArtifactPanel', () => {
  it('renders the artifact title and markdown body when open', () => {
    render(
      <ArtifactPanel artifact={buildArtifact()} onClose={vi.fn()} />,
    );
    const dialog = screen.getByRole('dialog');
    expect(dialog.getAttribute('aria-hidden')).toBe('false');
    expect(screen.getByText('Draft Email')).not.toBeNull();
    // react-markdown expands `# Hello` into a heading.
    expect(screen.getByRole('heading', { name: /Hello/ })).not.toBeNull();
    // Bold text survives markdown rendering.
    expect(screen.getByText('bold')).not.toBeNull();
  });

  it('shows an empty-state message when the artifact has no body yet', () => {
    render(
      <ArtifactPanel
        artifact={buildArtifact({ content: '' })}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText('아직 내용이 없습니다.')).not.toBeNull();
  });

  it('falls back to the placeholder title when none was supplied', () => {
    render(
      <ArtifactPanel
        artifact={buildArtifact({ title: null })}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText('(제목 없는 문서)')).not.toBeNull();
  });

  it('fires onClose when the close button is clicked', () => {
    const onClose = vi.fn();
    render(
      <ArtifactPanel artifact={buildArtifact()} onClose={onClose} />,
    );
    fireEvent.click(screen.getByRole('button', { name: '패널 닫기' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('hides the dialog when artifact is null', () => {
    render(<ArtifactPanel artifact={null} onClose={vi.fn()} />);
    const dialog = screen.getByRole('dialog', { hidden: true });
    expect(dialog.getAttribute('aria-hidden')).toBe('true');
  });
});
