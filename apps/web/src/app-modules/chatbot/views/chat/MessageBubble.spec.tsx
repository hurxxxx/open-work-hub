import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { MessageBubble } from './MessageBubble';
import type { ChatTurn } from './chat-turn';

function turn(overrides: Partial<ChatTurn>): ChatTurn {
  return {
    content: '',
    id: 'turn-1',
    role: 'assistant',
    ...overrides,
  };
}

describe('MessageBubble', () => {
  it('renders assistant messages as Markdown', () => {
    render(
      <MessageBubble
        turn={turn({
          content: '**중요**\n다음 줄\n\n- 근거 확인\n\n- [x] 검증 완료',
          role: 'assistant',
        })}
      />,
    );

    expect(screen.getByText('중요').tagName).toBe('STRONG');
    expect(document.querySelector('br')).not.toBeNull();
    expect(screen.getByText('근거 확인').closest('li')).not.toBeNull();
    expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(
      true,
    );
  });

  it('renders assistant math with KaTeX', () => {
    const { container } = render(
      <MessageBubble
        turn={turn({
          content:
            '인라인 수식 $a^2 + b^2 = c^2$ 입니다.\n\n$$\nx = {-b \\pm \\sqrt{b^2-4ac} \\over 2a}\n$$',
          role: 'assistant',
        })}
      />,
    );

    expect(container.querySelectorAll('.katex').length).toBeGreaterThan(0);
    expect(container.querySelector('.katex-display')).not.toBeNull();
  });

  it('renders percent signs in math without KaTeX comment warnings', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    try {
      const { container } = render(
        <MessageBubble
          turn={turn({
            content: '달성률은 $10%$ 입니다.',
            role: 'assistant',
          })}
        />,
      );

      expect(container.querySelectorAll('.katex').length).toBeGreaterThan(0);
      expect(warn.mock.calls.flat().join('\n')).not.toContain('commentAtEnd');
    } finally {
      warn.mockRestore();
    }
  });

  it('renders Korean text accidentally parsed as math without KaTeX strict warnings', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    try {
      const { container } = render(
        <MessageBubble
          turn={turn({
            content: '- **요약:** $10%는 목표 대비 실적입니다.$',
            role: 'assistant',
          })}
        />,
      );

      expect(container.querySelectorAll('.katex').length).toBeGreaterThan(0);
      expect(warn.mock.calls.flat().join('\n')).not.toContain(
        'unicodeTextInMathMode',
      );
    } finally {
      warn.mockRestore();
    }
  });

  it('renders common LaTeX bracket delimiters with KaTeX', () => {
    const { container } = render(
      <MessageBubble
        turn={turn({
          content:
            '인라인 \\(a^2 + b^2 = c^2\\)\n\n\\[\nx = \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}\n\\]',
          role: 'assistant',
        })}
      />,
    );

    expect(container.querySelectorAll('.katex').length).toBeGreaterThan(0);
    expect(container.querySelector('.katex-display')).not.toBeNull();
    expect(screen.queryByText('[')).toBeNull();
    expect(screen.queryByText(']')).toBeNull();
  });

  it('renders escaped emphasis delimiters outside code spans', () => {
    render(
      <MessageBubble
        turn={turn({
          content:
            '- 실무/일반적 사용: \\*\\*1번 (반복문)\\*\\*을 사용하세요.\n\n`\\*\\*literal\\*\\*`',
          role: 'assistant',
        })}
      />,
    );

    expect(screen.getByText('1번 (반복문)').tagName).toBe('STRONG');
    expect(screen.getByText('\\*\\*literal\\*\\*').tagName).toBe('CODE');
  });

  it('keeps HTML code blocks as source in chat messages', () => {
    const { container } = render(
      <MessageBubble
        turn={turn({
          content:
            '```html\n<button id="demo">Click</button><script>document.body.dataset.ready = "yes"</script>\n```',
          role: 'assistant',
        })}
      />,
    );

    expect(container.querySelector('iframe')).toBeNull();
    expect(container.querySelector('code.language-html')).not.toBeNull();
    expect(container.textContent).toContain('<button id="demo">Click</button>');
  });

  it('copies an individual assistant code block', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    });
    render(
      <MessageBubble
        turn={turn({
          content: '```ts\nconst answer = 42;\n```',
          role: 'assistant',
        })}
      />,
    );

    fireEvent.click(
      screen.getByRole('button', { name: /코드 복사|Copy code/ }),
    );

    expect(writeText).toHaveBeenCalledWith('const answer = 42;\n');
    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: /코드 복사됨|Code copied/ }),
      ).not.toBeNull();
    });
  });

  it('shows feedback after copying an assistant answer', async () => {
    const onCopy = vi.fn().mockResolvedValue(undefined);
    render(
      <MessageBubble
        turn={turn({
          content: '복사할 답변입니다.',
          role: 'assistant',
        })}
        onCopy={onCopy}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /복사|Copy/ }));

    expect(onCopy).toHaveBeenCalledWith(
      expect.objectContaining({ content: '복사할 답변입니다.' }),
    );
    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: /복사했습니다|Copied/ }),
      ).not.toBeNull();
    });
  });

  it('keeps retry visible on a failed persisted assistant response', () => {
    const onRetry = vi.fn();
    render(
      <MessageBubble
        turn={turn({
          content: '분석을 완료하지 못했습니다. 잠시 후 다시 시도해 주세요.',
          responseStatus: 'error',
        })}
        onRetry={onRetry}
      />,
    );

    const retry = screen.getByRole('button', { name: /재응답|Retry/ });
    expect(retry.textContent).toMatch(/재응답|Retry/);
    const actionBar = retry.closest('[data-message-actions]');
    expect(actionBar?.className).toContain('opacity-100');
    expect(actionBar?.className).not.toContain('opacity-0');

    fireEvent.click(retry);

    expect(onRetry).toHaveBeenCalledWith(
      expect.objectContaining({ responseStatus: 'error' }),
    );
  });

  it('keeps user messages as plain text', () => {
    render(
      <MessageBubble
        turn={turn({
          content: '**중요**',
          role: 'user',
        })}
      />,
    );

    expect(screen.getByText('**중요**')).not.toBeNull();
    expect(screen.queryByText('중요')).toBeNull();
  });

  it('does not expose internal routing metadata to users', () => {
    render(
      <MessageBubble
        turn={turn({
          chosenPool: 'local',
          content: '분석 범위를 확인해 주세요.',
          decisionReason: 'scope_direct_response',
          policy: 'scope_direct_response',
          role: 'assistant',
        })}
      />,
    );

    expect(screen.getByText('분석 범위를 확인해 주세요.')).not.toBeNull();
    expect(screen.queryByText(/scope_direct_response/)).toBeNull();
  });

  it('keeps source artifacts out of the top-level artifact cards', () => {
    render(
      <MessageBubble
        turn={turn({
          content: '보고서를 생성했습니다.',
          artifacts: [
            {
              id: 'report-1',
              type: 'document',
              title: '최종 보고서',
              content: '# 보고서',
              status: 'closed',
            },
            {
              id: 'analysis-1',
              type: 'legacy-issue-analysis',
              title: '정형 집계',
              content: '{"queries":[]}',
              status: 'closed',
            },
            {
              id: 'evidence-1',
              type: 'legacy-issue-evidence',
              title: '근거 데이터',
              content: '{"evidence":[]}',
              status: 'closed',
            },
          ],
        })}
        sourceArtifactTypes={['legacy-issue-analysis', 'legacy-issue-evidence']}
      />,
    );

    expect(screen.getByTestId('artifact-card-report-1')).toBeTruthy();
    expect(screen.queryByTestId('artifact-card-analysis-1')).toBeNull();
    expect(screen.queryByTestId('artifact-card-evidence-1')).toBeNull();
  });

  it('uses recovered artifact content for a persisted reference card', () => {
    const persistedReference = {
      id: 'report-1',
      type: 'document',
      title: '과거차 문제점 분석 보고서',
      content: '',
      status: 'closed' as const,
    };

    render(
      <MessageBubble
        turn={turn({
          content: '보고서를 생성했습니다.',
          artifacts: [persistedReference],
        })}
        resolvedArtifacts={[
          {
            ...persistedReference,
            content: '# 에바 동결 과거 이력 분석',
            kind: 'report',
          },
        ]}
      />,
    );

    expect(screen.getByText('에바 동결 과거 이력 분석')).toBeTruthy();
    expect(screen.queryByText(/0자/)).toBeNull();
  });

  it('uses a custom artifact preview instead of exposing serialized content', () => {
    const serializedContent =
      '{"version":1,"sources":[{"filename":"roadmap.pdf"}]}';
    render(
      <MessageBubble
        turn={turn({
          content: '근거를 확인했습니다.',
          artifacts: [
            {
              id: 'files-sources-1',
              type: 'files-rag-sources',
              title: '근거 문서',
              content: serializedContent,
              status: 'closed',
            },
          ],
        })}
        artifactRenderers={[
          {
            type: 'files-rag-sources',
            preview: () => 'roadmap.pdf',
            render: () => null,
          },
        ]}
      />,
    );

    expect(screen.getByText('roadmap.pdf')).toBeTruthy();
    expect(screen.queryByText(serializedContent)).toBeNull();
  });
});
