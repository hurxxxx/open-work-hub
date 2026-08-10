import { useCallback, useEffect, useMemo, useReducer, useRef } from 'react';

import {
  createSpecCompareJob,
  deleteSpecCompareJob,
  getSpecCompareJob,
  getSpecCompareResult,
  listSpecCompareJobs,
  type SpecCompareJob,
  type SpecCompareResult,
} from '../api/spec-compare-api';
import {
  INITIAL_SPEC_COMPARE_VIEW_STATE,
  canSubmitSpecCompareJob,
  getActiveSpecCompareJob,
  shouldClearSpecCompareResult,
  shouldLoadSpecCompareResult,
  specCompareViewReducer,
  type ResultTab,
  type SpecCompareViewState,
} from './spec-compare-view-model';

export const SPEC_COMPARE_JOB_POLL_INTERVAL_MS = 2500;

export interface SpecCompareJobWorkflowClient {
  createJob(args: {
    baseFile: File;
    targetFile: File;
    title: string;
    token: string;
    workspaceSlug: string | null;
  }): Promise<SpecCompareJob>;
  getJob(args: {
    jobId: string;
    token: string;
    workspaceSlug: string | null;
  }): Promise<SpecCompareJob>;
  getResult(args: {
    jobId: string;
    token: string;
    workspaceSlug: string | null;
  }): Promise<SpecCompareResult>;
  listJobs(args: {
    limit: number;
    token: string;
    workspaceSlug: string | null;
  }): Promise<{ items: SpecCompareJob[] }>;
  deleteJob(args: {
    jobId: string;
    token: string;
    workspaceSlug: string | null;
  }): Promise<{ id: string; deleted: boolean }>;
}

export interface SpecCompareJobWorkflowMessages {
  createFailed: string;
  loadJobsFailed: string;
  loadResultFailed: string;
  pollFailed: string;
  deleteFailed: string;
}

export interface SpecCompareJobWorkflowOptions {
  client?: SpecCompareJobWorkflowClient;
  messages: SpecCompareJobWorkflowMessages;
  pollIntervalMs?: number;
  token: string | null | undefined;
  workspaceSlug: string | null | undefined;
}

export interface SpecCompareJobWorkflowActions {
  refreshJobs(): Promise<void>;
  selectJob(job: SpecCompareJob): void;
  setBaseFile(file: File | null): void;
  setResultTab(tab: ResultTab): void;
  setTargetFile(file: File | null): void;
  submit(): Promise<void>;
  deleteJob(jobId: string): Promise<void>;
  reset(): void;
}

export interface SpecCompareJobWorkflow {
  actions: SpecCompareJobWorkflowActions;
  activeJob: SpecCompareJob | null;
  canSubmit: boolean;
  state: SpecCompareViewState;
}

const defaultClient: SpecCompareJobWorkflowClient = {
  createJob: createSpecCompareJob,
  getJob: getSpecCompareJob,
  getResult: getSpecCompareResult,
  listJobs: listSpecCompareJobs,
  deleteJob: deleteSpecCompareJob,
};

export function useSpecCompareJobWorkflow({
  client = defaultClient,
  messages,
  pollIntervalMs = SPEC_COMPARE_JOB_POLL_INTERVAL_MS,
  token,
  workspaceSlug,
}: SpecCompareJobWorkflowOptions): SpecCompareJobWorkflow {
  const [state, dispatch] = useReducer(
    specCompareViewReducer,
    INITIAL_SPEC_COMPARE_VIEW_STATE,
  );
  const pollTimerRef = useRef<number | null>(null);
  const { baseFile, result, selectedJob, submitting, targetFile } = state;
  const canSubmit = canSubmitSpecCompareJob({
    token,
    workspaceSlug,
    baseFile,
    targetFile,
    submitting,
  });
  const activeJob = getActiveSpecCompareJob(selectedJob);

  const refreshJobs = useCallback(async () => {
    if (!token || !workspaceSlug) {
      return;
    }
    dispatch({ type: 'jobsLoadStarted' });
    try {
      const response = await client.listJobs({ token, workspaceSlug, limit: 20 });
      dispatch({ type: 'jobsLoadSucceeded', jobs: response.items });
    } catch (caughtError) {
      dispatch({
        type: 'jobsLoadFailed',
        message: caughtError instanceof Error ? caughtError.message : messages.loadJobsFailed,
      });
    }
  }, [client, messages.loadJobsFailed, token, workspaceSlug]);

  const loadResult = useCallback(async (job: SpecCompareJob) => {
    if (!token || !workspaceSlug || job.status !== 'succeeded') {
      return;
    }
    dispatch({ type: 'resultLoadStarted', jobId: job.id });
    try {
      const nextResult = await client.getResult({ token, workspaceSlug, jobId: job.id });
      dispatch({ type: 'resultLoadSucceeded', jobId: job.id, result: nextResult });
    } catch (caughtError) {
      dispatch({
        type: 'resultLoadFailed',
        jobId: job.id,
        message: caughtError instanceof Error ? caughtError.message : messages.loadResultFailed,
      });
    }
  }, [client, messages.loadResultFailed, token, workspaceSlug]);

  const submit = useCallback(async () => {
    if (!canSubmit || !token || !workspaceSlug || !baseFile || !targetFile) {
      return;
    }
    dispatch({ type: 'submitStarted' });
    try {
      const job = await client.createJob({
        token,
        workspaceSlug,
        baseFile,
        targetFile,
        title: `${baseFile.name} / ${targetFile.name}`,
      });
      dispatch({ type: 'submitSucceeded', job });
    } catch (caughtError) {
      dispatch({
        type: 'submitFailed',
        message: caughtError instanceof Error ? caughtError.message : messages.createFailed,
      });
    }
  }, [
    baseFile,
    canSubmit,
    client,
    messages.createFailed,
    targetFile,
    token,
    workspaceSlug,
  ]);

  const deleteJob = useCallback(async (jobId: string) => {
    if (!token || !workspaceSlug) {
      return;
    }
    try {
      await client.deleteJob({ token, workspaceSlug, jobId });
      dispatch({ type: 'jobDeleted', jobId });
    } catch (caughtError) {
      dispatch({
        type: 'deleteFailed',
        message: caughtError instanceof Error ? caughtError.message : messages.deleteFailed,
      });
    }
  }, [client, messages.deleteFailed, token, workspaceSlug]);

  useEffect(() => {
    void refreshJobs();
  }, [refreshJobs]);

  useEffect(() => {
    if (shouldClearSpecCompareResult({ selectedJob, result })) {
      dispatch({ type: 'resultCleared' });
      return;
    }
    if (!shouldLoadSpecCompareResult({ selectedJob, result }) || !selectedJob) {
      return;
    }
    void loadResult(selectedJob);
  }, [loadResult, result, selectedJob]);

  useEffect(() => {
    if (!token || !workspaceSlug || !activeJob) {
      if (pollTimerRef.current !== null) {
        window.clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
      return;
    }

    pollTimerRef.current = window.setTimeout(async () => {
      try {
        const nextJob = await client.getJob({ token, workspaceSlug, jobId: activeJob.id });
        dispatch({ type: 'pollSucceeded', job: nextJob });
      } catch (caughtError) {
        dispatch({
          type: 'pollFailed',
          jobId: activeJob.id,
          message: caughtError instanceof Error ? caughtError.message : messages.pollFailed,
        });
      }
    }, pollIntervalMs);

    return () => {
      if (pollTimerRef.current !== null) {
        window.clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [
    activeJob,
    client,
    messages.pollFailed,
    pollIntervalMs,
    token,
    workspaceSlug,
  ]);

  const actions = useMemo<SpecCompareJobWorkflowActions>(
    () => ({
      refreshJobs,
      selectJob: (job) => dispatch({ type: 'jobSelected', job }),
      setBaseFile: (file) => dispatch({ type: 'baseFileChanged', file }),
      setResultTab: (tab) => dispatch({ type: 'resultTabChanged', tab }),
      setTargetFile: (file) => dispatch({ type: 'targetFileChanged', file }),
      submit,
      deleteJob,
      reset: () => dispatch({ type: 'formReset' }),
    }),
    [deleteJob, refreshJobs, submit],
  );

  return {
    actions,
    activeJob,
    canSubmit,
    state,
  };
}
