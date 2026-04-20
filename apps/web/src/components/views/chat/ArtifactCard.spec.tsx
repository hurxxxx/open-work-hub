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

  it('strips bold / italic / code / link markers out of the preview line', () => {
    // Smoke-test finding: first non-empty line was "**제목:**" and leaked
    // the asterisks into the tiny subtitle. Preview must strip those.
    render(
      <ArtifactCard
        artifact={buildArtifact({
          content:
            '**제목:** [보고] 이번 주 ~~임시~~ 계획 (`2026-04-20`)',
        })}
        isActive={false}
        onOpen={vi.fn()}
      />,
    );
    expect(
      screen.getByText('제목: [보고] 이번 주 임시 계획 (2026-04-20)'),
    ).not.toBeNull();
  });

  it('skips table-separator rows and collapses header pipes into a readable preview', () => {
    // The first non-empty line may be a GFM table row. Raw pipes look
    // broken — collapse them into middots and skip the `|---|` separator.
    render(
      <ArtifactCard
        artifact={buildArtifact({
          content: '| 항목 | 진행률 |\n|---|---|\n| 설계 | 100% |',
        })}
        isActive={false}
        onOpen={vi.fn()}
      />,
    );
    expect(screen.getByText('항목 · 진행률')).not.toBeNull();
  });

  it('skips a fenced code fence opener so the first prose line wins', () => {
    render(
      <ArtifactCard
        artifact={buildArtifact({
          content: '```html\n<!doctype html>\n<html>...</html>\n```',
        })}
        isActive={false}
        onOpen={vi.fn()}
      />,
    );
    expect(screen.getByText('<!doctype html>')).not.toBeNull();
  });

  it('shows the <title> tag for an html artifact instead of markdown strip', () => {
    render(
      <ArtifactCard
        artifact={buildArtifact({
          type: 'html',
          title: '랜딩 페이지',
          content:
            '<!doctype html><html><head><title>Welcome · Doowon</title></head><body>...</body></html>',
        })}
        isActive={false}
        onOpen={vi.fn()}
      />,
    );
    expect(screen.getByText(/HTML · Welcome · Doowon/)).not.toBeNull();
  });

  it('shows language + line count for a code artifact', () => {
    const code = ['def add(a, b):', '    return a + b', '', 'print(add(1, 2))'].join('\n');
    render(
      <ArtifactCard
        artifact={buildArtifact({
          type: 'code',
          language: 'python',
          title: 'add helper',
          content: code,
        })}
        isActive={false}
        onOpen={vi.fn()}
      />,
    );
    expect(screen.getByText('python · 4줄')).not.toBeNull();
  });

  it('falls back to type-specific placeholder when the title is missing', () => {
    render(
      <ArtifactCard
        artifact={buildArtifact({ type: 'code', title: null, language: 'js' })}
        isActive={false}
        onOpen={vi.fn()}
      />,
    );
    expect(screen.getByText('(제목 없는 코드)')).not.toBeNull();
  });
});
