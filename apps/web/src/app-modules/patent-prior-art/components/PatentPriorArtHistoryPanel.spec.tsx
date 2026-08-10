import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { i18n } from '@/src/platform/i18n';

import type { PatentPriorArtJob } from '../api/patent-prior-art-api';
import { PatentPriorArtHistoryPanel } from './PatentPriorArtHistoryPanel';

vi.mock('@/src/components/date/UserDateTime', () => ({
  UserDateTime: ({ value }: { value: string }) => <time>{value}</time>,
}));

describe('PatentPriorArtHistoryPanel', () => {
  it('shows a warning badge while automatic recovery is waiting', () => {
    const retryWaitingJob: PatentPriorArtJob = {
      automatic_restart_count: 1,
      can_cancel: true,
      created_at: '2026-07-22T01:00:00Z',
      execution_attempts: 1,
      id: 'job-1',
      next_attempt_at: '2026-07-22T01:02:00Z',
      progress_percent: 10,
      stage: 'retry_waiting',
      status: 'queued',
      title: 'Research',
      updated_at: '2026-07-22T01:01:00Z',
    };

    render(
      <PatentPriorArtHistoryPanel
        activeJobId={retryWaitingJob.id}
        busy={false}
        jobs={[retryWaitingJob]}
        onCancel={vi.fn()}
        onDelete={vi.fn()}
        onRefresh={vi.fn()}
        onSelect={vi.fn()}
      />,
    );

    const status = screen.getByText(
      i18n.t('ai.patentPriorArt.status.retry_waiting', { ns: 'apps' }),
    );
    expect(status.classList.contains('bg-app-warning-bg')).toBe(true);
  });
});
