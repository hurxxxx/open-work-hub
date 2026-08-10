import { type ReactElement, type ReactNode, useState } from 'react';
import { Check, Copy } from 'lucide-react';
import ReactMarkdown, { type Components } from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import rehypeKatex from 'rehype-katex';
import remarkBreaks from 'remark-breaks';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import { useTranslation } from 'react-i18next';
import { Tooltip } from '@open-work-hub/ui';
import 'highlight.js/styles/github.css';
import 'katex/dist/katex.min.css';

type ReactMarkdownProps = Parameters<typeof ReactMarkdown>[0];

const REMARK_PLUGINS = [
  remarkGfm,
  remarkMath,
  remarkBreaks,
  remarkModelTextMarkup,
];
const REHYPE_PLUGINS: NonNullable<ReactMarkdownProps['rehypePlugins']> = [
  [rehypeKatex, { strict: false }],
  rehypeHighlight,
];
const DEFAULT_CLASS_NAME =
  'app-markdown artifact-markdown prose prose-sm max-w-none dark:prose-invert';
const UNWRAP_MARKDOWN_FENCE =
  /^\s*```(?:markdown|md)\s*\n([\s\S]*?)\n\s*```\s*$/i;
const DISPLAY_MATH_BRACKET_DELIMITER = /\\\[([\s\S]*?)\\\]/g;
const INLINE_MATH_PAREN_DELIMITER = /\\\(([\s\S]*?)\\\)/g;
const FENCED_CODE_BLOCK = /((?:^|\n)(?:```|~~~)[^\n]*\n[\s\S]*?\n(?:```|~~~)(?=\n|$))/g;
const INLINE_CODE_SPAN = /(`+)([^`]*?)\1/g;
const INLINE_TEXT_MARKUP = /(\*\*|__|~~)([^\n]+?)\1/g;

type MarkdownAstNode = {
  children?: MarkdownAstNode[];
  type?: string;
  value?: string;
};
const MARKDOWN_COMPONENTS: Components = {
  a({ children, href, title }) {
    const isPageAnchor = href?.startsWith('#');

    return (
      <a
        href={href}
        title={title}
        rel={isPageAnchor ? undefined : 'noopener noreferrer'}
        target={isPageAnchor ? undefined : '_blank'}
      >
        {children}
      </a>
    );
  },
  pre({ children }) {
    return <MarkdownCodeBlock>{children}</MarkdownCodeBlock>;
  },
};

function normalizeLatexMathDelimiters(content: string): string {
  const normalized = content
    .replace(DISPLAY_MATH_BRACKET_DELIMITER, (_, math: string) => {
      return `\n$$\n${math.trim()}\n$$\n`;
    })
    .replace(INLINE_MATH_PAREN_DELIMITER, (_, math: string) => {
      return `$${math.trim()}$`;
    });
  return transformOutsideCodeBlocks(normalized, escapeLatexPercentInMath);
}

function normalizeEscapedMarkdownDelimiters(content: string): string {
  return content
    .replace(/\\\*\\\*/g, '**')
    .replace(/\\_\\_/g, '__')
    .replace(/\\~\\~/g, '~~');
}

function transformOutsideInlineCode(
  content: string,
  transform: (value: string) => string,
): string {
  let output = '';
  let lastIndex = 0;

  for (const match of content.matchAll(INLINE_CODE_SPAN)) {
    const index = match.index ?? 0;
    output += transform(content.slice(lastIndex, index));
    output += match[0];
    lastIndex = index + match[0].length;
  }

  return output + transform(content.slice(lastIndex));
}

function transformOutsideCodeBlocks(
  content: string,
  transform: (value: string) => string,
): string {
  return content
    .split(FENCED_CODE_BLOCK)
    .map((segment) => {
      if (/^\n?(?:```|~~~)/.test(segment)) {
        return segment;
      }
      return transformOutsideInlineCode(segment, transform);
    })
    .join('');
}

function normalizeModelMarkdown(content: string): string {
  return transformOutsideCodeBlocks(content, (value) =>
    normalizeEscapedMarkdownDelimiters(value),
  );
}

function remarkModelTextMarkup() {
  return (tree: MarkdownAstNode) => {
    rewriteTextMarkupChildren(tree);
  };
}

function escapeUnescapedLatexPercent(value: string): string {
  let output = '';
  for (let index = 0; index < value.length; index += 1) {
    const character = value[index];
    if (character === '%' && value[index - 1] !== '\\') {
      output += '\\%';
      continue;
    }
    output += character;
  }
  return output;
}

function escapeLatexPercentInMath(content: string): string {
  let output = '';
  let index = 0;

  while (index < content.length) {
    if (content[index] !== '$' || content[index - 1] === '\\') {
      output += content[index] ?? '';
      index += 1;
      continue;
    }

    const delimiter = content[index + 1] === '$' ? '$$' : '$';
    const mathStart = index + delimiter.length;
    const mathEnd = findClosingMathDelimiter(content, mathStart, delimiter);
    if (mathEnd < 0) {
      output += content[index];
      index += 1;
      continue;
    }

    output += delimiter;
    output += escapeUnescapedLatexPercent(content.slice(mathStart, mathEnd));
    output += delimiter;
    index = mathEnd + delimiter.length;
  }

  return output;
}

function findClosingMathDelimiter(
  content: string,
  startIndex: number,
  delimiter: '$' | '$$',
): number {
  for (let index = startIndex; index < content.length; index += 1) {
    if (content[index] === '\\') {
      index += 1;
      continue;
    }
    if (content.startsWith(delimiter, index)) {
      return index;
    }
  }
  return -1;
}

function rewriteTextMarkupChildren(node: MarkdownAstNode): void {
  if (node.type === 'code' || node.type === 'inlineCode') {
    return;
  }
  if (!node.children) {
    return;
  }

  const nextChildren: MarkdownAstNode[] = [];
  for (const child of node.children) {
    if (child.type === 'text' && typeof child.value === 'string') {
      nextChildren.push(...splitInlineTextMarkup(child.value));
      continue;
    }
    rewriteTextMarkupChildren(child);
    nextChildren.push(child);
  }
  node.children = nextChildren;
}

function splitInlineTextMarkup(value: string): MarkdownAstNode[] {
  const nodes: MarkdownAstNode[] = [];
  let lastIndex = 0;

  for (const match of value.matchAll(INLINE_TEXT_MARKUP)) {
    const index = match.index ?? 0;
    if (index > lastIndex) {
      nodes.push({ type: 'text', value: value.slice(lastIndex, index) });
    }

    const delimiter = match[1];
    const body = match[2] ?? '';
    if (body.trim()) {
      nodes.push({
        type: delimiter === '~~' ? 'delete' : 'strong',
        children: [{ type: 'text', value: body }],
      });
    } else {
      nodes.push({ type: 'text', value: match[0] });
    }
    lastIndex = index + match[0].length;
  }

  if (lastIndex < value.length) {
    nodes.push({ type: 'text', value: value.slice(lastIndex) });
  }

  return nodes.length > 0 ? nodes : [{ type: 'text', value }];
}

export interface MarkdownContentProps {
  content: string;
  className?: string;
  unwrapMarkdownFence?: boolean;
}

export function MarkdownContent({
  content,
  className,
  unwrapMarkdownFence = false,
}: MarkdownContentProps) {
  const body = normalizeLatexMathDelimiters(
    normalizeModelMarkdown(
      unwrapMarkdownFence
        ? (UNWRAP_MARKDOWN_FENCE.exec(content)?.[1] ?? content)
        : content,
    ),
  );
  const classNames = className
    ? `${DEFAULT_CLASS_NAME} ${className}`
    : DEFAULT_CLASS_NAME;

  return (
    <div className={classNames}>
      <ReactMarkdown
        components={MARKDOWN_COMPONENTS}
        remarkPlugins={REMARK_PLUGINS}
        rehypePlugins={REHYPE_PLUGINS}
      >
        {body}
      </ReactMarkdown>
    </div>
  );
}

function MarkdownCodeBlock({ children }: { children?: ReactNode }) {
  const { t } = useTranslation('apps');
  const [copied, setCopied] = useState(false);
  const code = textFromReactNode(children);

  const handleCopy = async () => {
    if (!code) {
      return;
    }
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  const label = copied
    ? t('ai.markdown.codeCopied')
    : t('ai.markdown.copyCode');

  return (
    <div className="markdown-code-block not-prose group relative my-4 overflow-hidden rounded-md border border-app-border bg-app-surface-hover">
      <Tooltip content={label}>
        <button
          type="button"
          aria-label={label}
          disabled={!code}
          onClick={() => void handleCopy()}
          className="absolute right-2 top-2 z-10 flex size-7 items-center justify-center rounded-md border border-app-border bg-app-surface text-app-ink/55 opacity-100 shadow-sm transition-colors hover:bg-app-surface-hover hover:text-app-ink disabled:cursor-not-allowed disabled:opacity-40"
        >
          {copied ? <Check size={14} /> : <Copy size={14} />}
        </button>
      </Tooltip>
      <pre>{children}</pre>
    </div>
  );
}

function textFromReactNode(node: ReactNode): string {
  if (node === null || node === undefined || typeof node === 'boolean') {
    return '';
  }
  if (typeof node === 'string' || typeof node === 'number') {
    return String(node);
  }
  if (Array.isArray(node)) {
    return node.map(textFromReactNode).join('');
  }
  if (typeof node === 'object' && 'props' in node) {
    const element = node as ReactElement<{ children?: ReactNode }>;
    return textFromReactNode(element.props.children);
  }
  return '';
}
