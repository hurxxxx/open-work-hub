import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ToolCallCard } from './ToolCallCard';

describe('ToolCallCard', () => {
  it('renders running state with args preview', () => {
    render(
      <ToolCallCard
        call={{
          call_id: 'call-running',
          name: 'pms.search_issues',
          args_preview: '{"q":"bug"',
          argsBuffer: '{"q":"bug"}',
          startedAtMs: 100,
          completedAtMs: null,
          status: 'running',
          result: null,
        }}
      />,
    );

    expect(screen.getByText('pms.search_issues')).not.toBeNull();
    expect(screen.getByText('running')).not.toBeNull();
    expect(screen.getByText('{"q":"bug"')).not.toBeNull();
  });

  it('renders ok result and duration when expanded', () => {
    render(
      <ToolCallCard
        call={{
          call_id: 'call-ok',
          name: 'docs.read_page',
          args_preview: null,
          argsBuffer: '{"page_id":"p1"}',
          startedAtMs: 100,
          completedAtMs: 245,
          status: 'ok',
          result: {
            status: 'ok',
            preview: '문서 내용 요약',
            error: null,
          },
        }}
      />,
    );

    fireEvent.click(screen.getByRole('button'));

    expect(screen.getByText('ok')).not.toBeNull();
    expect(screen.getByText('145ms')).not.toBeNull();
    expect(screen.getByText('문서 내용 요약')).not.toBeNull();
    expect(screen.getAllByText('{"page_id":"p1"}')).toHaveLength(2);
  });

  it('renders error state details', () => {
    render(
      <ToolCallCard
        call={{
          call_id: 'call-error',
          name: 'meeting.find_availability',
          args_preview: null,
          argsBuffer: '{"user_ids":[]}',
          startedAtMs: 10,
          completedAtMs: 30,
          status: 'error',
          result: {
            status: 'error',
            preview: null,
            error: 'availability lookup failed',
          },
        }}
      />,
    );

    fireEvent.click(screen.getByRole('button'));

    expect(screen.getByText('error')).not.toBeNull();
    expect(screen.getByText('availability lookup failed')).not.toBeNull();
  });
});
