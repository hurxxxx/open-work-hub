import { useCallback, useEffect, useRef, useState } from 'react';

import { ApiRequestError } from '@/src/platform/api/client';
import type { LegacyIssueExcelExportJob } from '../api/legacy-issue-common-api';

export const LEGACY_ISSUE_EXCEL_EXPORT_POLL_INTERVAL_MS = 2_000;
const MAX_CONSECUTIVE_POLL_FAILURES = 5;
const STORAGE_PREFIX = 'ai-do.legacy-issues.excel-export-job.v1';

export type LegacyIssueExcelExportFailureReason =
  | 'create'
  | 'download'
  | 'expired'
  | 'failed'
  | 'poll';

export function legacyIssueExcelExportErrorKey(
  reason: LegacyIssueExcelExportFailureReason,
):
  | 'coreBusiness.excelExport.errors.create'
  | 'coreBusiness.excelExport.errors.download'
  | 'coreBusiness.excelExport.errors.expired'
  | 'coreBusiness.excelExport.errors.failed'
  | 'coreBusiness.excelExport.errors.poll' {
  return `coreBusiness.excelExport.errors.${reason}`;
}

export interface LegacyIssueExcelExportJobWorkflow {
  busy: boolean;
  job: LegacyIssueExcelExportJob | null;
  start: (includeAttachments?: boolean) => Promise<void>;
}

export function legacyIssueExcelExportStorageKey({
  sourceKey,
  userId,
  workspaceSlug,
}: {
  sourceKey: string;
  userId: string;
  workspaceSlug: string;
}): string {
  return [STORAGE_PREFIX, userId, workspaceSlug, sourceKey]
    .map((part) => encodeURIComponent(part))
    .join(':');
}

export function useLegacyIssueExcelExportJob({
  createJob,
  fetchFile,
  fetchJob,
  fallbackFilename,
  onDownloaded,
  onFailed,
  onFile,
  pollIntervalMs = LEGACY_ISSUE_EXCEL_EXPORT_POLL_INTERVAL_MS,
  sourceKey,
  userId,
  workspaceSlug,
}: {
  createJob: (
    includeAttachments: boolean,
  ) => Promise<LegacyIssueExcelExportJob>;
  fetchFile: (jobId: string) => Promise<Blob>;
  fetchJob: (jobId: string) => Promise<LegacyIssueExcelExportJob>;
  fallbackFilename: string;
  onDownloaded?: (job: LegacyIssueExcelExportJob) => void;
  onFailed?: (
    reason: LegacyIssueExcelExportFailureReason,
    error?: unknown,
  ) => void;
  onFile: (
    blob: Blob,
    filename: string,
    job: LegacyIssueExcelExportJob,
  ) => void;
  pollIntervalMs?: number;
  sourceKey: string | null;
  userId: string | null | undefined;
  workspaceSlug: string;
}): LegacyIssueExcelExportJobWorkflow {
  const storageKey =
    sourceKey && userId && workspaceSlug
      ? legacyIssueExcelExportStorageKey({
          sourceKey,
          userId,
          workspaceSlug,
        })
      : null;
  const [creating, setCreating] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<LegacyIssueExcelExportJob | null>(null);
  const startInFlightRef = useRef(false);
  const storageKeyRef = useRef(storageKey);
  storageKeyRef.current = storageKey;
  const callbacksRef = useRef({
    createJob,
    fetchFile,
    fetchJob,
    fallbackFilename,
    onDownloaded,
    onFailed,
    onFile,
  });
  callbacksRef.current = {
    createJob,
    fetchFile,
    fetchJob,
    fallbackFilename,
    onDownloaded,
    onFailed,
    onFile,
  };

  useEffect(() => {
    setCreating(false);
    setJob(null);
    if (!storageKey) {
      setJobId(null);
      return;
    }
    setJobId(readStoredJobId(storageKey));
  }, [storageKey]);

  useEffect(() => {
    if (!jobId || !storageKey) return;
    let active = true;
    let pollTimer: number | null = null;
    let consecutivePollFailures = 0;

    const clearActiveJob = () => {
      removeStoredJobId(storageKey);
      setJobId((current) => (current === jobId ? null : current));
    };
    const schedulePoll = (delayMs = pollIntervalMs) => {
      pollTimer = window.setTimeout(() => void poll(), delayMs);
    };
    const poll = async () => {
      try {
        const nextJob = await callbacksRef.current.fetchJob(jobId);
        if (!active || storageKeyRef.current !== storageKey) return;
        consecutivePollFailures = 0;
        setJob(nextJob);
        if (nextJob.status === 'queued' || nextJob.status === 'running') {
          schedulePoll();
          return;
        }
        if (nextJob.status === 'failed' || nextJob.status === 'expired') {
          clearActiveJob();
          callbacksRef.current.onFailed?.(nextJob.status);
          return;
        }
        try {
          const blob = await callbacksRef.current.fetchFile(jobId);
          if (!active || storageKeyRef.current !== storageKey) return;
          callbacksRef.current.onFile(
            blob,
            nextJob.result_filename || callbacksRef.current.fallbackFilename,
            nextJob,
          );
          clearActiveJob();
          callbacksRef.current.onDownloaded?.(nextJob);
        } catch (error) {
          if (!active || storageKeyRef.current !== storageKey) return;
          callbacksRef.current.onFailed?.('download', error);
          schedulePoll(Math.max(pollIntervalMs, 10_000));
        }
      } catch (error) {
        if (!active || storageKeyRef.current !== storageKey) return;
        if (error instanceof ApiRequestError && error.status === 404) {
          clearActiveJob();
          callbacksRef.current.onFailed?.('poll', error);
          return;
        }
        consecutivePollFailures += 1;
        if (consecutivePollFailures >= MAX_CONSECUTIVE_POLL_FAILURES) {
          callbacksRef.current.onFailed?.('poll', error);
          consecutivePollFailures = 0;
          schedulePoll(Math.max(pollIntervalMs, 10_000));
          return;
        }
        schedulePoll();
      }
    };

    void poll();
    return () => {
      active = false;
      if (pollTimer !== null) window.clearTimeout(pollTimer);
    };
  }, [jobId, pollIntervalMs, storageKey]);

  const start = useCallback(
    async (includeAttachments = false) => {
      const activeStorageKey = storageKeyRef.current;
      if (!activeStorageKey || startInFlightRef.current || creating || jobId)
        return;
      startInFlightRef.current = true;
      setCreating(true);
      try {
        const nextJob =
          await callbacksRef.current.createJob(includeAttachments);
        if (storageKeyRef.current !== activeStorageKey) return;
        setJob(nextJob);
        writeStoredJobId(activeStorageKey, nextJob.id);
        setJobId(nextJob.id);
      } catch (error) {
        if (storageKeyRef.current === activeStorageKey) {
          callbacksRef.current.onFailed?.('create', error);
        }
      } finally {
        startInFlightRef.current = false;
        if (storageKeyRef.current === activeStorageKey) setCreating(false);
      }
    },
    [creating, jobId],
  );

  return { busy: creating || Boolean(jobId), job, start };
}

function readStoredJobId(storageKey: string): string | null {
  try {
    return window.localStorage.getItem(storageKey)?.trim() || null;
  } catch {
    return null;
  }
}

function writeStoredJobId(storageKey: string, jobId: string): void {
  try {
    window.localStorage.setItem(storageKey, jobId);
  } catch {
    // The export continues for this page even when browser storage is unavailable.
  }
}

function removeStoredJobId(storageKey: string): void {
  try {
    window.localStorage.removeItem(storageKey);
  } catch {
    // Storage may be disabled; there is nothing else to clean up client-side.
  }
}
