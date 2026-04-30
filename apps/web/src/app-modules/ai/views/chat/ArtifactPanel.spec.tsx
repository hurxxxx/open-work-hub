import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { ArtifactBuffer } from '../../api/agent-events';

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

  it('renders GFM tables as real <table> elements', () => {
    // remark-gfm turns `| col1 | col2 |` into a proper table; without the
    // plugin the pipes would leak through as raw text.
    const content = [
      '| 항목 | 진행률 |',
      '|---|---|',
      '| 설계 | 100% |',
      '| 개발 | 60% |',
    ].join('\n');
    render(
      <ArtifactPanel
        artifact={buildArtifact({ content })}
        onClose={vi.fn()}
      />,
    );
    const table = screen.getByRole('table');
    expect(table).not.toBeNull();
    expect(screen.getByRole('columnheader', { name: '항목' })).not.toBeNull();
    expect(screen.getByRole('cell', { name: '설계' })).not.toBeNull();
    expect(screen.getByRole('cell', { name: '60%' })).not.toBeNull();
  });

  it('applies syntax-highlight classes to fenced code blocks', () => {
    // rehype-highlight adds `hljs` + `language-*` classes so the panel's
    // CSS theme can style tokens. We don't assert specific color spans —
    // that's the library's responsibility — only that it wired up.
    const content = [
      '```html',
      '<!doctype html>',
      '<html><body>hi</body></html>',
      '```',
    ].join('\n');
    const { container } = render(
      <ArtifactPanel
        artifact={buildArtifact({ content })}
        onClose={vi.fn()}
      />,
    );
    const code = container.querySelector('pre code');
    expect(code).not.toBeNull();
    expect(code?.className).toMatch(/hljs/);
    expect(code?.className).toMatch(/language-html/);
  });

  it('dispatches html artifacts to the Preview/Source tab renderer', () => {
    const { container } = render(
      <ArtifactPanel
        artifact={buildArtifact({
          type: 'html',
          content: '<!doctype html><title>demo</title><body>hi</body>',
        })}
        onClose={vi.fn()}
      />,
    );
    // Preview-first → iframe should be mounted with srcDoc.
    const iframe = container.querySelector('iframe');
    expect(iframe).not.toBeNull();
    expect(iframe?.getAttribute('sandbox')).toBe('allow-scripts');
  });

  it('resets html artifacts back to the Preview tab when switching artifact ids', () => {
    const { container, rerender } = render(
      <ArtifactPanel
        artifact={buildArtifact({
          id: 'html-1',
          type: 'html',
          title: '첫 번째',
          content: '<!doctype html><title>one</title><body>1</body>',
        })}
        onClose={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('tab', { name: '소스' }));
    expect(container.querySelector('iframe')).toBeNull();

    rerender(
      <ArtifactPanel
        artifact={buildArtifact({
          id: 'html-2',
          type: 'html',
          title: '두 번째',
          content: '<!doctype html><title>two</title><body>2</body>',
        })}
        onClose={vi.fn()}
      />,
    );

    const iframe = container.querySelector('iframe');
    expect(iframe).not.toBeNull();
    expect(iframe?.getAttribute('srcdoc')).toContain('<title>two</title>');
    expect(
      screen.getByRole('tab', { name: '프리뷰' }).getAttribute('aria-selected'),
    ).toBe('true');
  });

  it('dispatches code artifacts to the pure syntax highlighter', () => {
    const { container } = render(
      <ArtifactPanel
        artifact={buildArtifact({
          type: 'code',
          language: 'python',
          content: 'print("hi")',
        })}
        onClose={vi.fn()}
      />,
    );
    const code = container.querySelector('pre code');
    expect(code?.className).toMatch(/language-python/);
    // The code renderer does not run the markdown pipeline, so no <h1> / tables.
    expect(container.querySelector('h1')).toBeNull();
  });

  it('dispatches svg artifacts to the sanitized SVG renderer', () => {
    const { container } = render(
      <ArtifactPanel
        artifact={buildArtifact({
          type: 'svg',
          content:
            '<svg viewBox="0 0 10 10"><circle cx="5" cy="5" r="4"/></svg>',
        })}
        onClose={vi.fn()}
      />,
    );
    expect(container.querySelector('svg')).not.toBeNull();
    expect(container.querySelector('circle')).not.toBeNull();
  });

  it('always opens at the wide layout — no narrow/maximize split', () => {
    // Phase C.3 iteration removed the maximize toggle: every artifact
    // needs room to breathe (tables, iframes, long code), so the panel
    // always ships at the wide width.
    render(<ArtifactPanel artifact={buildArtifact()} onClose={vi.fn()} />);
    const dialog = screen.getByRole('dialog');
    expect(dialog.className).toMatch(/w-\[min\(1200px,96vw\)\]/);
    expect(screen.queryByRole('button', { name: '패널 확대' })).toBeNull();
    expect(screen.queryByRole('button', { name: '패널 축소' })).toBeNull();
  });

  it('renders the type + language badge in the header', () => {
    render(
      <ArtifactPanel
        artifact={buildArtifact({ type: 'code', language: 'typescript' })}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText(/code · typescript/)).not.toBeNull();
  });
});
