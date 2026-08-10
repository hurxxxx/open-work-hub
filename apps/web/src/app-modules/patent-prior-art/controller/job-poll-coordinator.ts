import type { PatentPriorArtJob } from '../api/patent-prior-art-api';
import { isTerminalPatentPriorArtJob } from '../model/patent-prior-art-view-model';

export interface PatentPriorArtPollContext {
  jobId: string;
  signal: AbortSignal;
}

export interface PatentPriorArtPollCallbacks {
  onJob: (job: PatentPriorArtJob) => void;
  onTransientError: (error: unknown, failureCount: number) => void;
}

export interface PatentPriorArtPollRun {
  done: Promise<PatentPriorArtJob | null>;
  stop: () => void;
}

type PollDelay = (milliseconds: number, signal: AbortSignal) => Promise<void>;

const DEFAULT_POLL_DELAYS = [1_500, 2_500, 4_000, 7_000, 12_000] as const;

function abortableDelay(
  milliseconds: number,
  signal: AbortSignal,
): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException('Aborted', 'AbortError'));
      return;
    }
    const timer = window.setTimeout(resolve, milliseconds);
    signal.addEventListener(
      'abort',
      () => {
        window.clearTimeout(timer);
        reject(new DOMException('Aborted', 'AbortError'));
      },
      { once: true },
    );
  });
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}

export class PatentPriorArtJobPollCoordinator {
  private activeController: AbortController | null = null;
  private generation = 0;

  constructor(
    private readonly getJob: (
      context: PatentPriorArtPollContext,
    ) => Promise<PatentPriorArtJob>,
    private readonly delay: PollDelay = abortableDelay,
    private readonly delays: readonly number[] = DEFAULT_POLL_DELAYS,
  ) {}

  start(
    jobId: string,
    callbacks: PatentPriorArtPollCallbacks,
  ): PatentPriorArtPollRun {
    this.stop();
    const generation = this.generation;
    const controller = new AbortController();
    this.activeController = controller;

    const done = this.run(jobId, generation, controller.signal, callbacks);
    return {
      done,
      stop: () => {
        if (this.generation === generation) {
          this.stop();
        }
      },
    };
  }

  stop(): void {
    this.generation += 1;
    this.activeController?.abort();
    this.activeController = null;
  }

  private isCurrent(generation: number, signal: AbortSignal): boolean {
    return this.generation === generation && !signal.aborted;
  }

  private async run(
    jobId: string,
    generation: number,
    signal: AbortSignal,
    callbacks: PatentPriorArtPollCallbacks,
  ): Promise<PatentPriorArtJob | null> {
    let failureCount = 0;

    while (this.isCurrent(generation, signal)) {
      try {
        const job = await this.getJob({ jobId, signal });
        if (!this.isCurrent(generation, signal)) {
          return null;
        }
        failureCount = 0;
        callbacks.onJob(job);
        if (isTerminalPatentPriorArtJob(job)) {
          return job;
        }
      } catch (error) {
        if (!this.isCurrent(generation, signal) || isAbortError(error)) {
          return null;
        }
        failureCount += 1;
        callbacks.onTransientError(error, failureCount);
      }

      const delayIndex = Math.min(
        Math.max(failureCount - 1, 0),
        this.delays.length - 1,
      );
      try {
        await this.delay(this.delays[delayIndex] ?? 12_000, signal);
      } catch (error) {
        if (isAbortError(error) || !this.isCurrent(generation, signal)) {
          return null;
        }
        throw error;
      }
    }

    return null;
  }
}
