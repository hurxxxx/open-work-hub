import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import {
  patentPriorArtApi,
  type PatentPriorArtApi,
  type PatentPriorArtArtifact,
  type PatentPriorArtConfig,
  type PatentPriorArtFileParseResult,
  type PatentPriorArtJob,
  type PatentPriorArtPreview,
  type PatentPriorArtReportFormat,
  type PatentPriorArtSearchPlan,
} from '../api/patent-prior-art-api';
import { PatentPriorArtJobPollCoordinator } from './job-poll-coordinator';
import {
  addPlanValue,
  type EditablePlanField,
  removePlanValue,
  selectionDefaultsFromConfig,
  toggleSelectedValue,
  upsertJob,
} from '../model/patent-prior-art-view-model';

export type PatentPriorArtIssueKey =
  | 'cancel'
  | 'config'
  | 'create'
  | 'delete'
  | 'download'
  | 'history'
  | 'parse'
  | 'preview'
  | 'result';

export type PatentPriorArtBusyAction =
  | 'cancel'
  | 'create'
  | 'delete'
  | 'download'
  | 'history'
  | 'parse'
  | 'preview'
  | null;

export interface PatentPriorArtControllerOptions {
  api?: PatentPriorArtApi;
  token: string | null;
  workspaceSlug: string | null;
}

function createIdempotencyKey(): string {
  if (typeof globalThis.crypto?.randomUUID === 'function') {
    return globalThis.crypto.randomUUID();
  }
  return `patent-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

export function usePatentPriorArtController({
  api = patentPriorArtApi,
  token,
  workspaceSlug,
}: PatentPriorArtControllerOptions) {
  const [config, setConfig] = useState<PatentPriorArtConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [title, setTitle] = useState('');
  const [inventionText, setInventionTextState] = useState('');
  const [categoryIds, setCategoryIds] = useState<string[]>([]);
  const [jurisdictionIds, setJurisdictionIds] = useState<string[]>([]);
  const [parsedFile, setParsedFile] =
    useState<PatentPriorArtFileParseResult | null>(null);
  const [preview, setPreview] = useState<PatentPriorArtPreview | null>(null);
  const [history, setHistory] = useState<PatentPriorArtJob[]>([]);
  const [activeJob, setActiveJob] = useState<PatentPriorArtJob | null>(null);
  const [result, setResult] = useState<Awaited<
    ReturnType<PatentPriorArtApi['getResult']>
  > | null>(null);
  const [issue, setIssue] = useState<PatentPriorArtIssueKey | null>(null);
  const [pollInterrupted, setPollInterrupted] = useState(false);
  const [busyAction, setBusyAction] = useState<PatentPriorArtBusyAction>(null);

  const sessionKey = `${workspaceSlug ?? ''}\u0000${token ?? ''}`;
  const currentSessionKeyRef = useRef(sessionKey);
  currentSessionKeyRef.current = sessionKey;
  const previewSequenceRef = useRef(0);
  const previewAbortControllerRef = useRef<AbortController | null>(null);
  const createSubmissionRef = useRef<{
    fingerprint: string;
    idempotencyKey: string;
  } | null>(null);
  const activeJobId = activeJob?.id ?? null;
  const activeJobStatus = activeJob?.status ?? null;

  const clearPreview = useCallback(() => {
    previewAbortControllerRef.current?.abort();
    previewAbortControllerRef.current = null;
    previewSequenceRef.current += 1;
    createSubmissionRef.current = null;
    setPreview(null);
    setBusyAction((current) => (current === 'preview' ? null : current));
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let current = true;

    previewAbortControllerRef.current?.abort();
    previewAbortControllerRef.current = null;
    previewSequenceRef.current += 1;
    createSubmissionRef.current = null;

    setConfig(null);
    setLoading(Boolean(token && workspaceSlug));
    setTitle('');
    setInventionTextState('');
    setCategoryIds([]);
    setJurisdictionIds([]);
    setParsedFile(null);
    setPreview(null);
    setHistory([]);
    setActiveJob(null);
    setResult(null);
    setIssue(null);
    setPollInterrupted(false);
    setBusyAction(null);

    if (!token || !workspaceSlug) {
      return () => controller.abort();
    }

    void Promise.allSettled([
      api.getConfig({ signal: controller.signal, token, workspaceSlug }),
      api.listJobs({
        limit: 50,
        signal: controller.signal,
        token,
        workspaceSlug,
      }),
    ])
      .then(([configResult, jobsResult]) => {
        if (!current || controller.signal.aborted) return;
        if (configResult.status === 'fulfilled') {
          const defaults = selectionDefaultsFromConfig(configResult.value);
          setConfig(configResult.value);
          setCategoryIds(defaults.categoryIds);
          setJurisdictionIds(defaults.jurisdictionIds);
        } else {
          setIssue('config');
        }
        if (jobsResult.status === 'fulfilled') {
          setHistory(jobsResult.value.items ?? []);
        } else if (configResult.status === 'fulfilled') {
          setIssue('history');
        }
      })
      .finally(() => {
        if (current && !controller.signal.aborted) setLoading(false);
      });

    return () => {
      current = false;
      controller.abort();
      previewAbortControllerRef.current?.abort();
      previewAbortControllerRef.current = null;
    };
  }, [api, sessionKey, token, workspaceSlug]);

  useEffect(() => {
    if (!activeJobId || !token || !workspaceSlug) {
      return;
    }
    if (
      activeJobStatus === 'succeeded' ||
      activeJobStatus === 'failed' ||
      activeJobStatus === 'cancelled'
    ) {
      return;
    }

    const coordinator = new PatentPriorArtJobPollCoordinator(
      ({ jobId, signal }) =>
        api.getJob({ jobId, signal, token, workspaceSlug }),
    );
    const run = coordinator.start(activeJobId, {
      onJob: (job) => {
        setPollInterrupted(false);
        setActiveJob(job);
        setHistory((items) => upsertJob(items, job));
      },
      onTransientError: () => setPollInterrupted(true),
    });
    void run.done;

    return run.stop;
  }, [activeJobId, activeJobStatus, api, token, workspaceSlug]);

  useEffect(() => {
    if (activeJob?.status !== 'succeeded' || !token || !workspaceSlug) {
      setResult(null);
      return;
    }

    const controller = new AbortController();
    let current = true;
    setIssue(null);
    void api
      .getResult({
        jobId: activeJob.id,
        signal: controller.signal,
        token,
        workspaceSlug,
      })
      .then((nextResult) => {
        if (current && !controller.signal.aborted) setResult(nextResult);
      })
      .catch((error: unknown) => {
        if (current && !controller.signal.aborted) setIssue('result');
        void error;
      });

    return () => {
      current = false;
      controller.abort();
    };
  }, [activeJob?.id, activeJob?.status, api, token, workspaceSlug]);

  const setInventionText = useCallback(
    (value: string) => {
      setInventionTextState(value);
      clearPreview();
      setParsedFile(null);
    },
    [clearPreview],
  );

  const toggleCategory = useCallback(
    (categoryId: string) => {
      setCategoryIds((values) => toggleSelectedValue(values, categoryId));
      clearPreview();
    },
    [clearPreview],
  );

  const toggleJurisdiction = useCallback(
    (jurisdictionId: string) => {
      setJurisdictionIds((values) =>
        toggleSelectedValue(values, jurisdictionId),
      );
      clearPreview();
    },
    [clearPreview],
  );

  const parseFile = useCallback(
    async (file: File) => {
      if (!token || !workspaceSlug) return;
      const requestSession = sessionKey;
      setBusyAction('parse');
      setIssue(null);
      try {
        const parsed = await api.parseFile({ file, token, workspaceSlug });
        if (currentSessionKeyRef.current !== requestSession) return;
        setParsedFile(parsed);
        setInventionTextState((current) =>
          current.trim()
            ? `${current.trim()}\n\n${parsed.extracted_text}`
            : parsed.extracted_text,
        );
        clearPreview();
      } catch (error) {
        if (currentSessionKeyRef.current === requestSession) setIssue('parse');
        void error;
      } finally {
        if (currentSessionKeyRef.current === requestSession)
          setBusyAction(null);
      }
    },
    [api, clearPreview, sessionKey, token, workspaceSlug],
  );

  const removeParsedFile = useCallback(() => {
    setParsedFile((currentFile) => {
      if (!currentFile) return null;
      setInventionTextState((currentText) => {
        const appendedText = `\n\n${currentFile.extracted_text}`;
        if (currentText === currentFile.extracted_text) return '';
        if (currentText.endsWith(appendedText)) {
          return currentText.slice(0, -appendedText.length);
        }
        return currentText;
      });
      clearPreview();
      return null;
    });
  }, [clearPreview]);

  const createPreview = useCallback(async () => {
    if (!token || !workspaceSlug) return;
    previewAbortControllerRef.current?.abort();
    const requestController = new AbortController();
    previewAbortControllerRef.current = requestController;
    const requestSequence = previewSequenceRef.current + 1;
    previewSequenceRef.current = requestSequence;
    const requestSession = sessionKey;
    setBusyAction('preview');
    setIssue(null);
    try {
      const nextPreview = await api.previewQuery({
        request: {
          category_ids: categoryIds,
          invention_text: inventionText,
          jurisdictions: jurisdictionIds,
        },
        signal: requestController.signal,
        token,
        workspaceSlug,
      });
      if (
        currentSessionKeyRef.current !== requestSession ||
        previewSequenceRef.current !== requestSequence
      ) {
        return;
      }
      setPreview(nextPreview);
    } catch (error) {
      if (
        currentSessionKeyRef.current === requestSession &&
        previewSequenceRef.current === requestSequence
      ) {
        setIssue('preview');
      }
      void error;
    } finally {
      if (
        currentSessionKeyRef.current === requestSession &&
        previewSequenceRef.current === requestSequence
      ) {
        if (previewAbortControllerRef.current === requestController) {
          previewAbortControllerRef.current = null;
        }
        setBusyAction(null);
      }
    }
  }, [
    api,
    categoryIds,
    inventionText,
    jurisdictionIds,
    sessionKey,
    token,
    workspaceSlug,
  ]);

  const updatePlan = useCallback(
    (updater: (plan: PatentPriorArtSearchPlan) => PatentPriorArtSearchPlan) => {
      setPreview((current) => {
        if (!current) return current;
        const nextPlan = updater(current.plan);
        if (nextPlan === current.plan) return current;
        return {
          ...current,
          plan: { ...nextPlan, display_query: '' },
          source_queries: [],
        };
      });
    },
    [],
  );

  const addValue = useCallback(
    (field: EditablePlanField, value: string) => {
      if (!config) return;
      updatePlan((plan) =>
        addPlanValue(plan, field, value, {
          maxValueChars: config.max_plan_value_chars,
          maxValuesPerField: config.max_plan_values_per_field,
        }),
      );
    },
    [config, updatePlan],
  );

  const removeValue = useCallback(
    (field: EditablePlanField, value: string) => {
      updatePlan((plan) => removePlanValue(plan, field, value));
    },
    [updatePlan],
  );

  const createJob = useCallback(async () => {
    if (!token || !workspaceSlug || !preview) return;
    const requestSession = sessionKey;
    setBusyAction('create');
    setIssue(null);
    const requestPayload = {
      invention_text: inventionText,
      jurisdictions: jurisdictionIds,
      search_plan: preview.plan,
      technology_summary: preview.technology_summary,
      title: title.trim(),
    };
    const fingerprint = JSON.stringify(requestPayload);
    const submission =
      createSubmissionRef.current?.fingerprint === fingerprint
        ? createSubmissionRef.current
        : { fingerprint, idempotencyKey: createIdempotencyKey() };
    createSubmissionRef.current = submission;
    try {
      const job = await api.createJob({
        request: {
          ...requestPayload,
          idempotency_key: submission.idempotencyKey,
        },
        token,
        workspaceSlug,
      });
      if (currentSessionKeyRef.current !== requestSession) return;
      setActiveJob(job);
      setResult(null);
      setHistory((items) => upsertJob(items, job));
      if (createSubmissionRef.current === submission) {
        createSubmissionRef.current = null;
      }
    } catch (error) {
      if (currentSessionKeyRef.current === requestSession) setIssue('create');
      void error;
    } finally {
      if (currentSessionKeyRef.current === requestSession) setBusyAction(null);
    }
  }, [
    api,
    inventionText,
    jurisdictionIds,
    preview,
    sessionKey,
    title,
    token,
    workspaceSlug,
  ]);

  const refreshHistory = useCallback(async () => {
    if (!token || !workspaceSlug) return;
    const requestSession = sessionKey;
    setBusyAction('history');
    setIssue(null);
    try {
      const jobs = await api.listJobs({ limit: 50, token, workspaceSlug });
      if (currentSessionKeyRef.current === requestSession) {
        setHistory(jobs.items ?? []);
      }
    } catch (error) {
      if (currentSessionKeyRef.current === requestSession) setIssue('history');
      void error;
    } finally {
      if (currentSessionKeyRef.current === requestSession) setBusyAction(null);
    }
  }, [api, sessionKey, token, workspaceSlug]);

  const selectJob = useCallback((job: PatentPriorArtJob) => {
    setActiveJob(job);
    setResult(null);
    setIssue(null);
  }, []);

  const cancelJob = useCallback(
    async (job: PatentPriorArtJob) => {
      if (!token || !workspaceSlug || !job.can_cancel) return;
      const requestSession = sessionKey;
      setBusyAction('cancel');
      setIssue(null);
      try {
        const cancelled = await api.cancelJob({
          jobId: job.id,
          token,
          workspaceSlug,
        });
        if (currentSessionKeyRef.current !== requestSession) return;
        setHistory((items) => upsertJob(items, cancelled));
        setActiveJob((current) =>
          current?.id === cancelled.id ? cancelled : current,
        );
      } catch (error) {
        if (currentSessionKeyRef.current === requestSession) setIssue('cancel');
        void error;
      } finally {
        if (currentSessionKeyRef.current === requestSession)
          setBusyAction(null);
      }
    },
    [api, sessionKey, token, workspaceSlug],
  );

  const deleteJob = useCallback(
    async (job: PatentPriorArtJob) => {
      if (!token || !workspaceSlug) return;
      const requestSession = sessionKey;
      setBusyAction('delete');
      setIssue(null);
      try {
        const deletion = await api.deleteJob({
          jobId: job.id,
          token,
          workspaceSlug,
        });
        if (currentSessionKeyRef.current !== requestSession) return;
        if (!deletion.deleted) {
          setIssue('delete');
          try {
            const retained = await api.getJob({
              jobId: job.id,
              token,
              workspaceSlug,
            });
            if (currentSessionKeyRef.current !== requestSession) return;
            setHistory((items) => upsertJob(items, retained));
            setActiveJob((current) =>
              current?.id === retained.id ? retained : current,
            );
          } catch {
            // Preserve the existing list item and delete issue so the owner can retry.
          }
          return;
        }
        setHistory((items) => items.filter((item) => item.id !== job.id));
        setActiveJob((current) => (current?.id === job.id ? null : current));
        setResult((current) => (current?.job.id === job.id ? null : current));
      } catch (error) {
        if (currentSessionKeyRef.current === requestSession) setIssue('delete');
        void error;
      } finally {
        if (currentSessionKeyRef.current === requestSession)
          setBusyAction(null);
      }
    },
    [api, sessionKey, token, workspaceSlug],
  );

  const downloadArtifact = useCallback(
    async (artifact: PatentPriorArtArtifact): Promise<Blob | null> => {
      if (!token || !workspaceSlug || !activeJob) return null;
      const requestSession = sessionKey;
      setBusyAction('download');
      setIssue(null);
      try {
        const blob = await api.downloadArtifact({
          artifactId: artifact.id,
          jobId: activeJob.id,
          token,
          workspaceSlug,
        });
        return currentSessionKeyRef.current === requestSession ? blob : null;
      } catch (error) {
        if (currentSessionKeyRef.current === requestSession)
          setIssue('download');
        void error;
        return null;
      } finally {
        if (currentSessionKeyRef.current === requestSession)
          setBusyAction(null);
      }
    },
    [activeJob, api, sessionKey, token, workspaceSlug],
  );

  const downloadReport = useCallback(
    async (reportFormat: PatentPriorArtReportFormat): Promise<Blob | null> => {
      if (!token || !workspaceSlug || !activeJob) return null;
      const requestSession = sessionKey;
      setBusyAction('download');
      setIssue(null);
      try {
        const blob = await api.downloadReport({
          jobId: activeJob.id,
          reportFormat,
          token,
          workspaceSlug,
        });
        return currentSessionKeyRef.current === requestSession ? blob : null;
      } catch (error) {
        if (currentSessionKeyRef.current === requestSession)
          setIssue('download');
        void error;
        return null;
      } finally {
        if (currentSessionKeyRef.current === requestSession)
          setBusyAction(null);
      }
    },
    [activeJob, api, sessionKey, token, workspaceSlug],
  );

  const canPreview = Boolean(
    config &&
      inventionText.trim().length >= config.min_invention_chars &&
      inventionText.length <= config.max_invention_chars &&
      jurisdictionIds.length > 0,
  );
  const canCreate = canPreview && Boolean(preview) && busyAction === null;

  return useMemo(
    () => ({
      activeJob,
      addPlanValue: addValue,
      busyAction,
      canCreate,
      canPreview,
      cancelJob,
      categoryIds,
      config,
      createJob,
      createPreview,
      deleteJob,
      downloadArtifact,
      downloadReport,
      history,
      inventionText,
      issue,
      jurisdictionIds,
      loading,
      parsedFile,
      pollInterrupted,
      preview,
      refreshHistory,
      removeParsedFile,
      removePlanValue: removeValue,
      result,
      selectJob,
      setInventionText,
      setTitle,
      title,
      toggleCategory,
      toggleJurisdiction,
      parseFile,
    }),
    [
      activeJob,
      addValue,
      busyAction,
      canCreate,
      canPreview,
      cancelJob,
      categoryIds,
      config,
      createJob,
      createPreview,
      deleteJob,
      downloadArtifact,
      downloadReport,
      history,
      inventionText,
      issue,
      jurisdictionIds,
      loading,
      parsedFile,
      pollInterrupted,
      preview,
      refreshHistory,
      removeParsedFile,
      removeValue,
      result,
      selectJob,
      setInventionText,
      title,
      toggleCategory,
      toggleJurisdiction,
      parseFile,
    ],
  );
}
