import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { i18n } from '@/src/platform/i18n';

import type { PatentPriorArtJob } from '../api/patent-prior-art-api';
import { PatentPriorArtJobStatusNotice } from './PatentPriorArtJobStatusNotice';

vi.mock('@/src/components/date/UserDateTime', () => ({
  UserDateTime: ({ value }: { value: string }) => <time>{value}</time>,
}));

const baseJob: PatentPriorArtJob = {
  automatic_restart_count: 0,
  can_cancel: false,
  created_at: '2026-07-22T01:00:00Z',
  execution_attempts: 0,
  id: 'job-1',
  progress_percent: 100,
  stage: 'failed',
  status: 'failed',
  title: 'Research',
  updated_at: '2026-07-22T01:10:00Z',
};

describe('PatentPriorArtJobStatusNotice', () => {
  it('renders the automatic-recovery attempt and next-attempt time', () => {
    render(
      <PatentPriorArtJobStatusNotice
        job={{
          ...baseJob,
          automatic_restart_count: 1,
          can_cancel: true,
          execution_attempts: 2,
          next_attempt_at: '2026-07-22T01:11:00Z',
          progress_percent: 10,
          stage: 'retry_waiting',
          status: 'queued',
        }}
      />,
    );

    expect(
      screen.getByText(
        i18n.t('ai.patentPriorArt.job.retryWaiting', {
          attemptCount: 2,
          ns: 'apps',
          restartCount: 1,
        }),
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        i18n.t('ai.patentPriorArt.job.nextAttempt', { ns: 'apps' }),
      ),
    ).toBeTruthy();
    expect(screen.getByText('2026-07-22T01:11:00Z')).toBeTruthy();
  });

  it('renders only the safe message selected by the failure code', () => {
    render(
      <PatentPriorArtJobStatusNotice
        job={{ ...baseJob, failure_code: 'provider_timeout' }}
      />,
    );

    expect(
      screen.getByText(
        i18n.t('ai.patentPriorArt.job.failures.provider_timeout', {
          ns: 'apps',
        }),
      ),
    ).toBeTruthy();
    expect(screen.queryByText('provider_timeout')).toBeNull();
  });
});
