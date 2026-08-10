import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useToast } from '@ai-do/ui';

import {
  fetchDeterminations,
  fetchPriorExamStatus,
  fetchSettings,
  fetchSettingsHistory,
  fetchSourceStatus,
  HealthCheckupApiError,
  refreshDeterminations,
  updateSettings,
  uploadPriorExam,
  type HealthCheckupDeterminationList,
  type HealthCheckupPriorExamStatus,
  type HealthCheckupPriorExamUpload,
  type HealthCheckupSettings,
  type HealthCheckupSettingsUpdate,
  type HealthCheckupSourceStatus,
  type SettingsHistoryItem,
} from '../api/health-checkup-api';

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}

export interface HealthCheckupController {
  determinations: HealthCheckupDeterminationList | null;
  fatalAccessDenied: boolean;
  history: SettingsHistoryItem[];
  loadingDeterminations: boolean;
  loadingSettings: boolean;
  loadingSource: boolean;
  priorStatus: HealthCheckupPriorExamStatus | null;
  refreshingSource: boolean;
  refreshSourceAndDeterminations: () => Promise<void>;
  saveSettings: (payload: HealthCheckupSettingsUpdate) => Promise<void>;
  savingSettings: boolean;
  settings: HealthCheckupSettings | null;
  sourceStatus: HealthCheckupSourceStatus | null;
  uploadPriorExamFile: (file: File) => Promise<void>;
  uploadResult: HealthCheckupPriorExamUpload | null;
  uploading: boolean;
}

export function useHealthCheckupController({
  settingsActive,
  token,
  workspaceSlug,
  year,
}: {
  settingsActive: boolean;
  token: string;
  workspaceSlug: string;
  year: number;
}): HealthCheckupController {
  const { t } = useTranslation('apps');
  const toast = useToast();
  const sourceAbortRef = useRef<AbortController | null>(null);
  const determinationAbortRef = useRef<AbortController | null>(null);
  const priorStatusAbortRef = useRef<AbortController | null>(null);
  const settingsAbortRef = useRef<AbortController | null>(null);
  const activeYearRef = useRef(year);
  activeYearRef.current = year;
  const sourceRequestRef = useRef(0);
  const determinationRequestRef = useRef(0);
  const priorStatusRequestRef = useRef(0);
  const settingsRequestRef = useRef(0);
  const uploadRequestRef = useRef(0);

  const [sourceStatus, setSourceStatus] =
    useState<HealthCheckupSourceStatus | null>(null);
  const [determinations, setDeterminations] =
    useState<HealthCheckupDeterminationList | null>(null);
  const [priorStatus, setPriorStatus] =
    useState<HealthCheckupPriorExamStatus | null>(null);
  const [settings, setSettings] = useState<HealthCheckupSettings | null>(null);
  const [history, setHistory] = useState<SettingsHistoryItem[]>([]);
  const [uploadResult, setUploadResult] =
    useState<HealthCheckupPriorExamUpload | null>(null);
  const [loadingSource, setLoadingSource] = useState(false);
  const [loadingDeterminations, setLoadingDeterminations] = useState(false);
  const [loadingSettings, setLoadingSettings] = useState(false);
  const [refreshingSource, setRefreshingSource] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [savingSettings, setSavingSettings] = useState(false);
  const [settingsLoaded, setSettingsLoaded] = useState(false);
  const [fatalAccessDenied, setFatalAccessDenied] = useState(false);

  const handleError = useCallback(
    (error: unknown, messageKey: string) => {
      if (isAbortError(error)) return;
      if (error instanceof HealthCheckupApiError && error.status === 403) {
        setFatalAccessDenied(true);
        return;
      }
      toast.error(t(messageKey));
    },
    [t, toast],
  );

  const loadSourceStatus = useCallback(async () => {
    sourceAbortRef.current?.abort();
    const controller = new AbortController();
    sourceAbortRef.current = controller;
    const requestId = ++sourceRequestRef.current;
    setLoadingSource(true);
    try {
      const next = await fetchSourceStatus({
        token,
        workspaceSlug,
        signal: controller.signal,
      });
      if (
        !controller.signal.aborted &&
        requestId === sourceRequestRef.current
      ) {
        setSourceStatus(next);
      }
    } catch (error) {
      if (requestId === sourceRequestRef.current) {
        handleError(error, 'healthCheckup.errors.sourceStatus');
      }
    } finally {
      if (requestId === sourceRequestRef.current) setLoadingSource(false);
    }
  }, [handleError, token, workspaceSlug]);

  const requestDeterminations = useCallback(
    async (recalculate: boolean, requestYear: number) => {
      if (activeYearRef.current !== requestYear) return;
      determinationAbortRef.current?.abort();
      const controller = new AbortController();
      determinationAbortRef.current = controller;
      const requestId = ++determinationRequestRef.current;
      setLoadingDeterminations(true);
      try {
        let next: HealthCheckupDeterminationList;
        if (recalculate) {
          next = await refreshDeterminations({
            token,
            workspaceSlug,
            year: requestYear,
            signal: controller.signal,
          });
        } else {
          try {
            next = await fetchDeterminations({
              token,
              workspaceSlug,
              year: requestYear,
              signal: controller.signal,
            });
          } catch (error) {
            if (
              !(error instanceof HealthCheckupApiError) ||
              error.status !== 404 ||
              controller.signal.aborted
            ) {
              throw error;
            }
            next = await refreshDeterminations({
              token,
              workspaceSlug,
              year: requestYear,
              signal: controller.signal,
            });
          }
        }
        if (
          !controller.signal.aborted &&
          requestId === determinationRequestRef.current &&
          activeYearRef.current === requestYear
        ) {
          setDeterminations(next);
          setSourceStatus(next.source);
        }
      } catch (error) {
        if (requestId === determinationRequestRef.current) {
          handleError(error, 'healthCheckup.errors.load');
        }
      } finally {
        if (requestId === determinationRequestRef.current) {
          setLoadingDeterminations(false);
        }
      }
    },
    [handleError, token, workspaceSlug],
  );

  const loadDeterminations = useCallback(
    () => requestDeterminations(false, year),
    [requestDeterminations, year],
  );
  const recalculateDeterminations = useCallback(
    () => requestDeterminations(true, year),
    [requestDeterminations, year],
  );

  const loadPriorStatus = useCallback(async () => {
    priorStatusAbortRef.current?.abort();
    const controller = new AbortController();
    priorStatusAbortRef.current = controller;
    const requestId = ++priorStatusRequestRef.current;
    try {
      const next = await fetchPriorExamStatus({
        token,
        workspaceSlug,
        year,
        signal: controller.signal,
      });
      if (
        !controller.signal.aborted &&
        requestId === priorStatusRequestRef.current
      ) {
        setPriorStatus(next);
      }
    } catch (error) {
      if (requestId === priorStatusRequestRef.current) {
        handleError(error, 'healthCheckup.errors.priorExamStatus');
      }
    }
  }, [handleError, token, workspaceSlug, year]);

  const loadSettingsResources = useCallback(async () => {
    settingsAbortRef.current?.abort();
    const controller = new AbortController();
    settingsAbortRef.current = controller;
    const requestId = ++settingsRequestRef.current;
    setLoadingSettings(true);
    const [settingsResult, historyResult] = await Promise.allSettled([
      fetchSettings({ token, workspaceSlug, signal: controller.signal }),
      fetchSettingsHistory({
        token,
        workspaceSlug,
        signal: controller.signal,
      }),
    ]);
    if (controller.signal.aborted || requestId !== settingsRequestRef.current) {
      return;
    }
    if (settingsResult.status === 'fulfilled') {
      setSettings(settingsResult.value);
    } else {
      handleError(settingsResult.reason, 'healthCheckup.errors.loadSettings');
    }
    if (historyResult.status === 'fulfilled') {
      setHistory(historyResult.value.items);
    } else {
      handleError(historyResult.reason, 'healthCheckup.errors.loadHistory');
    }
    setSettingsLoaded(true);
    setLoadingSettings(false);
  }, [handleError, token, workspaceSlug]);

  useEffect(() => {
    determinationAbortRef.current?.abort();
    priorStatusAbortRef.current?.abort();
    determinationRequestRef.current += 1;
    priorStatusRequestRef.current += 1;
    uploadRequestRef.current += 1;
    setDeterminations(null);
    setPriorStatus(null);
    setUploadResult(null);
    setUploading(false);
    setLoadingDeterminations(true);
  }, [token, year]);

  useEffect(() => {
    void loadSourceStatus();
    return () => sourceAbortRef.current?.abort();
  }, [loadSourceStatus]);

  useEffect(() => {
    void loadDeterminations();
    return () => determinationAbortRef.current?.abort();
  }, [loadDeterminations]);

  useEffect(() => {
    void loadPriorStatus();
    return () => priorStatusAbortRef.current?.abort();
  }, [loadPriorStatus]);

  useEffect(() => {
    setSettingsLoaded(false);
    setSettings(null);
    setHistory([]);
    setLoadingSettings(false);
  }, [token]);

  useEffect(() => {
    if (!settingsActive || settingsLoaded || loadingSettings) return;
    void loadSettingsResources();
  }, [loadSettingsResources, loadingSettings, settingsActive, settingsLoaded]);

  useEffect(
    () => () => {
      sourceAbortRef.current?.abort();
      determinationAbortRef.current?.abort();
      priorStatusAbortRef.current?.abort();
      settingsAbortRef.current?.abort();
    },
    [],
  );

  const refreshSourceAndDeterminations = useCallback(async () => {
    setRefreshingSource(true);
    try {
      await Promise.all([
        loadSourceStatus(),
        recalculateDeterminations(),
        loadPriorStatus(),
      ]);
    } finally {
      setRefreshingSource(false);
    }
  }, [loadPriorStatus, loadSourceStatus, recalculateDeterminations]);

  const uploadPriorExamFile = useCallback(
    async (file: File) => {
      const requestId = ++uploadRequestRef.current;
      setUploading(true);
      try {
        const result = await uploadPriorExam({
          token,
          workspaceSlug,
          year,
          file,
        });
        if (
          requestId !== uploadRequestRef.current ||
          activeYearRef.current !== year
        ) {
          return;
        }
        setUploadResult(result);
        toast.success(
          t('healthCheckup.toasts.uploaded', {
            matched: result.matched_count,
            total: result.total_rows,
          }),
        );
        await Promise.all([recalculateDeterminations(), loadPriorStatus()]);
      } catch (error) {
        if (requestId === uploadRequestRef.current) {
          handleError(error, 'healthCheckup.errors.upload');
        }
      } finally {
        if (requestId === uploadRequestRef.current) {
          setUploading(false);
        }
      }
    },
    [
      handleError,
      loadPriorStatus,
      recalculateDeterminations,
      t,
      toast,
      token,
      workspaceSlug,
      year,
    ],
  );

  const saveSettings = useCallback(
    async (payload: HealthCheckupSettingsUpdate) => {
      setSavingSettings(true);
      try {
        const updated = await updateSettings({ token, workspaceSlug, payload });
        setSettings(updated);
        toast.success(t('healthCheckup.toasts.saved'));
        await Promise.all([
          loadSettingsResources(),
          requestDeterminations(true, activeYearRef.current),
        ]);
      } catch (error) {
        handleError(error, 'healthCheckup.errors.save');
      } finally {
        setSavingSettings(false);
      }
    },
    [
      handleError,
      loadSettingsResources,
      requestDeterminations,
      t,
      toast,
      token,
      workspaceSlug,
    ],
  );

  return {
    determinations:
      determinations?.target_year === year ? determinations : null,
    fatalAccessDenied,
    history,
    loadingDeterminations,
    loadingSettings,
    loadingSource,
    priorStatus: priorStatus?.exam_year === year - 1 ? priorStatus : null,
    refreshingSource,
    refreshSourceAndDeterminations,
    saveSettings,
    savingSettings,
    settings,
    sourceStatus,
    uploadPriorExamFile,
    uploadResult: uploadResult?.target_year === year ? uploadResult : null,
    uploading,
  };
}
