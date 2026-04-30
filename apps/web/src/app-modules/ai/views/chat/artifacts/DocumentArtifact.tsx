import ReactMarkdown from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import remarkGfm from 'remark-gfm';

// Plugin instances are module-level constants so react-markdown doesn't
// remount its pipeline on every parent re-render (identity-based array
// comparison).
const REMARK_PLUGINS = [remarkGfm];
const REHYPE_PLUGINS = [rehypeHighlight];

// Safety net for a Phase C.2 regression window: some saved artifacts came
// in with their entire body wrapped in a ```markdown ... ``` fence because
// the earlier system prompt was ambiguous. Detect that single-block
// wrapper and peel it so existing conversations render correctly. Anything
// else — including legitimate ``` blocks inside a larger document — is
// passed through untouched.
const UNWRAP_MARKDOWN_FENCE = /^\s*```(?:markdown|md)\s*\n([\s\S]*?)\n\s*```\s*$/i;

export interface DocumentArtifactProps {
  content: string;
}

export function DocumentArtifact({ content }: DocumentArtifactProps) {
  const body = UNWRAP_MARKDOWN_FENCE.exec(content)?.[1] ?? content;
  return (
    <div className="app-markdown artifact-markdown prose prose-sm max-w-none dark:prose-invert">
      <ReactMarkdown
        remarkPlugins={REMARK_PLUGINS}
        rehypePlugins={REHYPE_PLUGINS}
      >
        {body}
      </ReactMarkdown>
    </div>
  );
}
