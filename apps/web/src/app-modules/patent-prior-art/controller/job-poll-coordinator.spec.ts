import { describe, expect, it, vi } from 'vitest';

import type { PatentPriorArtJob } from '../api/patent-prior-art-api';
import { PatentPriorArtJobPollCoordinator } from './job-poll-coordinator';

function job(
  status: PatentPriorArtJob['status'],
  overrides: Partial<PatentPriorArtJob> = {},
): PatentPriorArtJob {
  return {
    automatic_restart_count: 0,
    can_cancel: status === 'queued' || status === 'running',
    created_at: '2026-07-22T01:00:00Z',
    execution_attempts: 0,
    id: 'job-1',
    progress_percent: status === 'succeeded' ? 100 : 25,
    stage: '',
    status,
    title: 'Research',
    updated_at: '2026-07-22T01:01:00Z',
    ...overrides,
  };
}

const noWait = () => Promise.resolve();

describe('PatentPriorArtJobPollCoordinator', () => {
  it('discards a late response after the poll session is reset', async () => {
    let resolveRequest: ((value: PatentPriorArtJob) => void) | undefined;
    const getJob = vi.fn(
      () =>
        new Promise<PatentPriorArtJob>((resolve) => {
          resolveRequest = resolve;
        }),
    );
    const onJob = vi.fn();
    const coordinator = new PatentPriorArtJobPollCoordinator(getJob, noWait);

    const run = coordinator.start('job-1', {
      onJob,
      onTransientError: vi.fn(),
    });
    run.stop();
    resolveRequest?.(job('succeeded'));

    await expect(run.done).resolves.toBeNull();
    expect(onJob).not.toHaveBeenCalled();
  });

  it('backs off after a transient error and recovers until terminal status', async () => {
    const delay = vi.fn(noWait);
    const getJob = vi
      .fn()
      .mockRejectedValueOnce(new Error('temporary'))
      .mockResolvedValueOnce(job('running'))
      .mockResolvedValueOnce(job('succeeded'));
    const onJob = vi.fn();
    const onTransientError = vi.fn();
    const coordinator = new PatentPriorArtJobPollCoordinator(
      getJob,
      delay,
      [100, 200],
    );

    const run = coordinator.start('job-1', { onJob, onTransientError });

    await expect(run.done).resolves.toMatchObject({ status: 'succeeded' });
    expect(onTransientError).toHaveBeenCalledTimes(1);
    expect(onJob.mock.calls.map(([nextJob]) => nextJob.status)).toEqual([
      'running',
      'succeeded',
    ]);
    expect(delay).toHaveBeenNthCalledWith(1, 100, expect.any(AbortSignal));
  });

  it('keeps polling while an automatic recovery is waiting', async () => {
    const getJob = vi
      .fn()
      .mockResolvedValueOnce(
        job('queued', {
          automatic_restart_count: 1,
          execution_attempts: 1,
          next_attempt_at: '2026-07-22T01:02:00Z',
          stage: 'retry_waiting',
        }),
      )
      .mockResolvedValueOnce(job('running', { stage: 'searching' }))
      .mockResolvedValueOnce(job('succeeded', { stage: 'completed' }));
    const onJob = vi.fn();
    const coordinator = new PatentPriorArtJobPollCoordinator(getJob, noWait);

    const run = coordinator.start('job-1', {
      onJob,
      onTransientError: vi.fn(),
    });

    await expect(run.done).resolves.toMatchObject({
      stage: 'completed',
      status: 'succeeded',
    });
    expect(
      onJob.mock.calls.map(([nextJob]) => [nextJob.status, nextJob.stage]),
    ).toEqual([
      ['queued', 'retry_waiting'],
      ['running', 'searching'],
      ['succeeded', 'completed'],
    ]);
  });

  it('aborts an in-flight request when cancelled', async () => {
    let requestSignal: AbortSignal | null = null;
    const getJob = vi.fn(
      ({ signal }: { signal: AbortSignal }) =>
        new Promise<PatentPriorArtJob>((_resolve, reject) => {
          requestSignal = signal;
          signal.addEventListener('abort', () => {
            reject(new DOMException('Aborted', 'AbortError'));
          });
        }),
    );
    const coordinator = new PatentPriorArtJobPollCoordinator(getJob, noWait);

    const run = coordinator.start('job-1', {
      onJob: vi.fn(),
      onTransientError: vi.fn(),
    });
    run.stop();

    await expect(run.done).resolves.toBeNull();
    expect((requestSignal as AbortSignal | null)?.aborted).toBe(true);
  });
});
