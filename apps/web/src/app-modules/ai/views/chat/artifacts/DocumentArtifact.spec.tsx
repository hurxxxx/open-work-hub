import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { DocumentArtifact } from './DocumentArtifact';

describe('DocumentArtifact', () => {
  it('renders GFM tables as real <table> elements', () => {
    const content = [
      '| 항목 | 값 |',
      '|---|---|',
      '| A | 100 |',
      '| B | 200 |',
    ].join('\n');
    render(<DocumentArtifact content={content} />);
    const table = screen.getByRole('table');
    expect(table).not.toBeNull();
    expect(screen.getByRole('columnheader', { name: '항목' })).not.toBeNull();
    expect(screen.getByRole('cell', { name: '200' })).not.toBeNull();
  });

  it('applies syntax highlight classes to fenced code blocks', () => {
    const { container } = render(
      <DocumentArtifact content={'```python\nprint("hi")\n```'} />,
    );
    const code = container.querySelector('pre code');
    expect(code).not.toBeNull();
    expect(code?.className).toMatch(/hljs/);
    expect(code?.className).toMatch(/language-python/);
  });

  it('peels a whole-body ```markdown fence so legacy Phase-C.2 artifacts recover', () => {
    // During the C.2 regression window some stored artifacts arrived
    // wrapped in ``` ```markdown ... ``` ```. The renderer must detect
    // that single-block wrapper and show the inner markdown as headings /
    // tables rather than a giant <pre>.
    const wrapped = '```markdown\n# 제목\n\n**굵게**\n```';
    render(<DocumentArtifact content={wrapped} />);
    expect(screen.getByRole('heading', { name: /제목/ })).not.toBeNull();
    expect(screen.getByText('굵게')).not.toBeNull();
  });

  it('leaves legitimate inner code blocks intact when peeling', () => {
    // Only the single-block wrapper is stripped. A document that happens
    // to contain a fenced code block as part of its normal body must
    // still render that block as code, not unwrap it.
    const content = '# 가이드\n\n예시:\n\n```js\nconst x = 1;\n```';
    const { container } = render(<DocumentArtifact content={content} />);
    expect(screen.getByRole('heading', { name: /가이드/ })).not.toBeNull();
    expect(container.querySelector('pre code.language-js')).not.toBeNull();
  });

  it('does not unwrap a document whose whole body is just a plain code fence', () => {
    const { container } = render(
      <DocumentArtifact content={'```\nconst answer = 42;\n```'} />,
    );
    const code = container.querySelector('pre code');
    expect(code).not.toBeNull();
    expect(code?.textContent).toContain('const answer = 42;');
  });
});
