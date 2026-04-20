import { useEffect, useRef } from 'react';
import hljs from 'highlight.js';

export interface CodeArtifactProps {
  content: string;
  language: string | null;
}

// Pure syntax-highlighted source view. Unlike DocumentArtifact this does
// not run the markdown pipeline — the artifact body IS the code, not
// markdown prose around it. We call hljs.highlightElement imperatively
// so we get the same tokenization that rehype-highlight uses inside
// DocumentArtifact without re-routing through react-markdown just to
// wrap the body in a single fence.
export function CodeArtifact({ content, language }: CodeArtifactProps) {
  const codeRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!codeRef.current) return;
    // hljs stamps a `data-highlighted` attribute to prevent re-highlighting;
    // clear it so subsequent content changes (streaming deltas on a live
    // artifact) re-tokenize rather than silently dropping.
    codeRef.current.removeAttribute('data-highlighted');
    try {
      hljs.highlightElement(codeRef.current);
    } catch {
      // Unknown language falls back to plain text — better than a crash
      // on a typo'd `language="c++17"` from the model.
    }
  }, [content, language]);

  const className = language
    ? `language-${language.toLowerCase()}`
    : undefined;

  return (
    <div className="artifact-code h-full">
      <pre>
        <code ref={codeRef} className={className}>
          {content}
        </code>
      </pre>
    </div>
  );
}
