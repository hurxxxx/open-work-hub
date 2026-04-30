import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { CodeArtifact } from './CodeArtifact';

describe('CodeArtifact', () => {
  it('wraps the content in <pre><code> with the language class', () => {
    const { container } = render(
      <CodeArtifact content={'print("hi")'} language="python" />,
    );
    const code = container.querySelector('pre code');
    expect(code).not.toBeNull();
    expect(code?.className).toMatch(/language-python/);
  });

  it('lowercases the language class so hljs grammar lookups resolve', () => {
    const { container } = render(
      <CodeArtifact content={'SELECT 1;'} language="SQL" />,
    );
    const code = container.querySelector('pre code');
    expect(code?.className).toMatch(/language-sql/);
  });

  it('renders the content verbatim when no language is provided', () => {
    // Without an explicit language, hljs may auto-detect one; that's fine
    // — the contract we care about is that the original text survives
    // unchanged and the element still carries an hljs marker.
    const { container } = render(
      <CodeArtifact content={'hello world'} language={null} />,
    );
    const code = container.querySelector('pre code');
    expect(code).not.toBeNull();
    expect(code?.textContent).toBe('hello world');
    expect(code?.className).toMatch(/hljs/);
  });
});
