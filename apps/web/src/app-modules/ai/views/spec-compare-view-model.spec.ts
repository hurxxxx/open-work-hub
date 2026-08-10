import { describe, expect, it } from 'vitest';

import type {
  SpecCompareJob,
  SpecCompareResult,
} from '../api/spec-compare-api';
import {
  INITIAL_SPEC_COMPARE_VIEW_STATE,
  specCompareViewReducer,
  type SpecCompareViewState,
} from './spec-compare-view-model';

function job(id: string, status: SpecCompareJob['status'] = 'succeeded'): SpecCompareJob {
  return {
    id,
    workspace_id: 'workspace-1',
    owner_id: 'user-1',
    title: `Job ${id}`,
    status,
    progress: status === 'succeeded' ? 100 : 40,
    status_message: status,
    failure_reason: null,
    base_file: { name: `base-${id}.pptx`, mime_type: 'application/pptx', size_bytes: 1 },
    target_file: { name: `target-${id}.pptx`, mime_type: 'application/pptx', size_bytes: 1 },
    result_summary: null,
    completed_at: status === 'succeeded' ? '2026-07-07T00:00:00Z' : null,
    created_at: '2026-07-07T00:00:00Z',
    updated_at: `2026-07-07T00:00:0${id.length}Z`,
  };
}

function result(forJob: SpecCompareJob): SpecCompareResult {
  return {
    job: forJob,
    report_markdown: `# ${forJob.title}`,
    comparison_rows: [],
    evidence_blocks: [],
    summary: {},
  };
}

function loadedState(selectedJob: SpecCompareJob, jobs: SpecCompareJob[]): SpecCompareViewState {
  return {
    ...INITIAL_SPEC_COMPARE_VIEW_STATE,
    jobs,
    selectedJob,
  };
}

describe('spec compare view model', () => {
  it('applies result load transitions only for the current selected job', () => {
    const first = job('job-1');
    const second = job('job-2');
    const state = loadedState(second, [first, second]);

    expect(
      specCompareViewReducer(state, { type: 'resultLoadStarted', jobId: first.id }),
    ).toBe(state);

    const staleSuccess = specCompareViewReducer(state, {
      type: 'resultLoadSucceeded',
      jobId: first.id,
      result: result(first),
    });
    expect(staleSuccess).toBe(state);

    const staleFailure = specCompareViewReducer(state, {
      type: 'resultLoadFailed',
      jobId: first.id,
      message: 'stale failure',
    });
    expect(staleFailure).toBe(state);

    const loading = specCompareViewReducer(state, {
      type: 'resultLoadStarted',
      jobId: second.id,
    });
    expect(loading.loadingResult).toBe(true);

    const loaded = specCompareViewReducer(loading, {
      type: 'resultLoadSucceeded',
      jobId: second.id,
      result: result(second),
    });
    expect(loaded.result?.job.id).toBe(second.id);
    expect(loaded.selectedJob?.id).toBe(second.id);
    expect(loaded.loadingResult).toBe(false);
  });

  it('ignores in-flight result responses after a selected job is deleted', () => {
    const selected = job('job-1');
    const loading = specCompareViewReducer(loadedState(selected, [selected]), {
      type: 'resultLoadStarted',
      jobId: selected.id,
    });
    expect(loading.loadingResult).toBe(true);

    const deleted = specCompareViewReducer(loading, {
      type: 'jobDeleted',
      jobId: selected.id,
    });
    expect(deleted.selectedJob).toBeNull();
    expect(deleted.result).toBeNull();
    expect(deleted.loadingResult).toBe(false);

    const staleSuccess = specCompareViewReducer(deleted, {
      type: 'resultLoadSucceeded',
      jobId: selected.id,
      result: result(selected),
    });
    expect(staleSuccess).toBe(deleted);
  });
});
