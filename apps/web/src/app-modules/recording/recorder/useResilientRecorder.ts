import { useAuth } from '@/src/platform/auth/auth-provider';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  completeRecordingUpload,
  discardRecordingUpload,
  headRecordingTusUpload,
  importRecording,
  initRecordingUpload,
  uploadRecordingTusChunk,
  type Recording,
} from '../api/recording-api';
import {
  bindRecordingBackgroundSync,
  registerRecordingBackgroundSync,
} from './recording-background-sync';
import {
  RecordingRecorderRuntime,
  type RecordingRecorderRuntimeOptions,
} from './recording-recorder-runtime';
import type { RecordingRecoveryContinueSessionInput } from './recording-recovery-session-plan';
import {
  appendChunk,
  buildRecordingScopeKey,
  buildSessionBlob,
  clearSession,
  getChunks,
  getPendingChunks,
  getSession,
  listIncompleteSessions,
  markChunkUploaded,
  markSessionComplete,
  sessionTarget,
  updateSessionProgress,
  upsertSession,
  type RecordingSessionSource,
  type RecordingSessionState,
  type RecordingTargetRef,
} from './recording-session-db';
import {
  requestRecordingWakeLock,
  wakeLockSupported,
} from './recording-wake-lock';

type ContinueSessionInput = RecordingRecoveryContinueSessionInput;

interface StartRecordingInput {
  linkedTaskId?: string | null;
  title?: string | null;
}

interface ImportAudioInput extends StartRecordingInput {
  source?: 'quick_record' | 'manual_upload';
}

interface RecorderOptions {
  token: string | null;
  initialTarget?: RecordingTargetRef | null;
  source?: RecordingSessionSource;
  title?: string | null;
  onRecordingSaved?: (recording: Recording) => Promise<void> | void;
}

type RecorderState =
  | 'idle'
  | 'requesting'
  | 'recording'
  | 'stopping'
  | 'uploading'
  | 'saved';
type InputState = 'ready' | 'muted' | 'ended' | 'error';

const RECORDER_MIME_TYPES = [
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/mp4',
  'audio/ogg;codecs=opus',
] as const;

function createId(): string {
  if (
    typeof crypto !== 'undefined' &&
    typeof crypto.randomUUID === 'function'
  ) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

async function sha256Hex(blob: Blob): Promise<string | null> {
  if (!crypto.subtle) {
    return null;
  }
  const buffer = await blob.arrayBuffer();
  const hash = await crypto.subtle.digest('SHA-256', buffer);
  const bytes = Array.from(new Uint8Array(hash));
  return bytes.map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

export function selectRecorderMimeType(): string | undefined {
  if (typeof MediaRecorder === 'undefined') {
    return undefined;
  }
  return RECORDER_MIME_TYPES.find((mimeType) =>
    MediaRecorder.isTypeSupported(mimeType),
  );
}

function sessionSource(
  source: RecordingSessionSource | undefined,
  initialTarget: RecordingTargetRef | null | undefined,
): RecordingSessionSource {
  return (
    source ??
    (initialTarget?.app === 'meeting' ? 'live_recording' : 'quick_record')
  );
}

function sessionStartedAt(session: RecordingSessionState | null): Date | null {
  return session?.startedAt ? new Date(session.startedAt) : null;
}

export function useResilientRecorder({
  token,
  initialTarget = null,
  source,
  title,
  onRecordingSaved,
}: RecorderOptions) {
  const { t } = useTranslation('apps');
  const { user } = useAuth();
  const userId = user?.id ?? '';
  const [recorderState, setRecorderState] = useState<RecorderState>('idle');
  const [isBusy, setIsBusy] = useState(false);
  const [elapsedSec, setElapsedSec] = useState(0);
  const [queuedBytes, setQueuedBytes] = useState(0);
  const [uploadedBytes, setUploadedBytes] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [persistWarning, setPersistWarning] = useState<string | null>(null);
  const [wakeLockWarning, setWakeLockWarning] = useState<string | null>(null);
  const [inputState, setInputState] = useState<InputState>('ready');

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const wakeLockRef = useRef<{
    released: boolean;
    release: () => Promise<void>;
  } | null>(null);
  const flushRecorderRef = useRef<() => void>(() => undefined);
  const acquireWakeLockRef = useRef<() => void>(() => undefined);
  const resumeRecoverableUploadsRef = useRef<() => void>(() => undefined);
  const activeSessionIdRef = useRef<string | null>(null);
  const nextSeqRef = useRef(0);
  const startAtRef = useRef<number | null>(null);
  const stoppingRef = useRef<Set<string>>(new Set());
  const runtimeContextRef = useRef({
    token,
    userId,
    initialTarget,
    source,
    title,
    onRecordingSaved,
    t,
  });
  const runtimeRef = useRef<RecordingRecorderRuntime<Recording> | null>(null);
  const scopeKey = useMemo(
    () => buildRecordingScopeKey(userId, initialTarget),
    [initialTarget, userId],
  );
  runtimeContextRef.current = {
    token,
    userId,
    initialTarget,
    source,
    title,
    onRecordingSaved,
    t,
  };
  if (!runtimeRef.current) {
    const requireToken = () => {
      const currentToken = runtimeContextRef.current.token;
      if (!currentToken) {
        throw new Error(
          runtimeContextRef.current.t('recording.errors.chunkUploadFailed'),
        );
      }
      return currentToken;
    };
    const runtimeOptions: RecordingRecorderRuntimeOptions<Recording> = {
      store: {
        appendChunk,
        getChunks,
        getPendingChunks,
        markChunkUploaded,
        updateSessionProgress,
        getSession: async (id) => {
          const session = await getSession(id);
          return session?.userId === runtimeContextRef.current.userId
            ? session
            : null;
        },
        listIncompleteSessions: (options) =>
          listIncompleteSessions({
            ...options,
            userId: runtimeContextRef.current.userId,
          }),
        markSessionComplete,
        clearSession,
      },
      client: {
        headUpload: (stagingId) =>
          headRecordingTusUpload(requireToken(), stagingId),
        uploadChunk: (stagingId, offset, blob, sha256) =>
          uploadRecordingTusChunk(
            requireToken(),
            stagingId,
            offset,
            blob,
            sha256,
          ),
        completeUpload: (stagingId, payload) =>
          completeRecordingUpload(requireToken(), stagingId, payload),
      },
      environment: {
        now: () => Date.now(),
        digestBlob: sha256Hex,
        registerBackgroundSync: async () => {
          await registerRecordingBackgroundSync();
        },
        setTimeout: (callback, delayMs) => window.setTimeout(callback, delayMs),
        clearTimeout: (timer) => window.clearTimeout(timer),
      },
      defaults: {
        title: () => runtimeContextRef.current.title ?? null,
        source: () =>
          sessionSource(
            runtimeContextRef.current.source,
            runtimeContextRef.current.initialTarget,
          ),
      },
      messages: {
        tusOffsetConflict: () =>
          runtimeContextRef.current.t('recording.errors.tusOffsetConflict'),
      },
      callbacks: {
        onStatsChanged: (_stagingId, stats) => {
          setQueuedBytes(stats.queuedBytes);
          setUploadedBytes(stats.uploadedBytes);
        },
        onChunkWriteFailed: (_stagingId, err) => {
          setError(
            err instanceof Error
              ? err.message
              : runtimeContextRef.current.t('recording.errors.saveFailed'),
          );
        },
        onPumpFailed: (_stagingId, err) => {
          setError(
            err instanceof Error
              ? err.message
              : runtimeContextRef.current.t(
                  'recording.errors.chunkUploadFailed',
                ),
          );
        },
        onFinalizeStarted: () => {
          setIsBusy(true);
          setRecorderState('uploading');
        },
        onFinalizeFailed: (_stagingId, err) => {
          setRecorderState('idle');
          setError(
            err instanceof Error
              ? err.message
              : runtimeContextRef.current.t('recording.errors.finalizeFailed'),
          );
        },
        onFinalizeFinished: () => {
          setIsBusy(false);
        },
        onUploadSaved: async (_stagingId, recording) => {
          activeSessionIdRef.current = null;
          setQueuedBytes(0);
          setUploadedBytes(0);
          setElapsedSec(0);
          setRecorderState('saved');
          await runtimeContextRef.current.onRecordingSaved?.(recording);
          window.setTimeout(() => setRecorderState('idle'), 1200);
        },
      },
      canUpload: () => runtimeContextRef.current.token != null,
    };
    runtimeRef.current = new RecordingRecorderRuntime(runtimeOptions);
  }
  const recorderRuntime = runtimeRef.current;

  const browserSupported =
    typeof window !== 'undefined' &&
    typeof MediaRecorder !== 'undefined' &&
    typeof navigator !== 'undefined' &&
    typeof navigator.mediaDevices?.getUserMedia === 'function' &&
    selectRecorderMimeType() != null;
  const isRecording = recorderState === 'recording';
  const inputWarning =
    inputState === 'muted'
      ? t('recording.recorderWarnings.inputPaused')
      : inputState === 'ended'
        ? t('recording.recorderWarnings.inputEnded')
        : inputState === 'error'
          ? t('recording.recorderWarnings.inputFailed')
          : null;

  async function requestPersistentStorage() {
    try {
      if (!navigator.storage?.persist) {
        return;
      }
      const persisted = await navigator.storage.persist();
      if (!persisted) {
        setPersistWarning(t('recording.errors.persistMayExpire'));
      } else {
        setPersistWarning(null);
      }
    } catch {
      setPersistWarning(t('recording.errors.persistCheckFailed'));
    }
  }

  async function acquireWakeLock() {
    if (!wakeLockSupported() || document.visibilityState !== 'visible') {
      return;
    }
    try {
      if (wakeLockRef.current && !wakeLockRef.current.released) {
        return;
      }
      wakeLockRef.current = await requestRecordingWakeLock();
      setWakeLockWarning(null);
    } catch {
      setWakeLockWarning(t('recording.errors.wakeLockFailed'));
    }
  }

  async function releaseWakeLock() {
    const wakeLock = wakeLockRef.current;
    wakeLockRef.current = null;
    if (!wakeLock || wakeLock.released) {
      return;
    }
    try {
      await wakeLock.release();
    } catch {
      return;
    }
  }

  async function emitSaved(recording: Recording) {
    await onRecordingSaved?.(recording);
  }

  async function pumpUploads(stagingId: string): Promise<void> {
    await recorderRuntime.pumpUploads(stagingId);
  }

  function queueChunkWrite(stagingId: string, seq: number, blob: Blob) {
    void recorderRuntime.queueChunkWrite(stagingId, seq, blob);
  }

  function stopMediaStream() {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }

  function flushRecorder() {
    const recorder = mediaRecorderRef.current;
    if (!recorder || recorder.state !== 'recording') {
      return;
    }
    try {
      recorder.requestData();
    } catch {
      // Browser lifecycle events are best-effort only.
    }
  }

  async function handleRecorderStopped(stagingId: string) {
    if (stoppingRef.current.has(stagingId)) {
      return;
    }
    stoppingRef.current.add(stagingId);
    setRecorderState('stopping');
    try {
      await recorderRuntime.prepareFinalize(stagingId);
      stopMediaStream();
      await releaseWakeLock();
      mediaRecorderRef.current = null;
      await pumpUploads(stagingId);
    } finally {
      stoppingRef.current.delete(stagingId);
    }
  }

  function bindTrackEvents(stream: MediaStream, stagingId: string) {
    for (const track of stream.getAudioTracks()) {
      track.addEventListener('mute', () => {
        setInputState('muted');
        void updateSessionProgress(stagingId, {
          interruptedAt: Date.now(),
          interruptionReason: 'audio_muted',
        });
        flushRecorder();
      });
      track.addEventListener('unmute', () => {
        setInputState('ready');
      });
      track.addEventListener('ended', () => {
        setInputState('ended');
        void updateSessionProgress(stagingId, {
          interruptedAt: Date.now(),
          interruptionReason: 'audio_ended',
        });
        flushRecorder();
        const recorder = mediaRecorderRef.current;
        if (recorder && recorder.state !== 'inactive') {
          try {
            recorder.stop();
          } catch {
            void handleRecorderStopped(stagingId);
          }
        }
      });
    }
  }

  function bindRecorder(
    recorder: MediaRecorder,
    stream: MediaStream,
    stagingId: string,
  ) {
    bindTrackEvents(stream, stagingId);
    recorder.ondataavailable = (event) => {
      if (event.data.size === 0) {
        return;
      }
      const seq = nextSeqRef.current++;
      queueChunkWrite(stagingId, seq, event.data);
    };
    recorder.onerror = () => {
      setInputState('error');
      setError(t('recording.errors.recordingFailed'));
      void updateSessionProgress(stagingId, {
        interruptedAt: Date.now(),
        interruptionReason: 'recorder_error',
      });
      flushRecorder();
      if (recorder.state !== 'inactive') {
        try {
          recorder.stop();
        } catch {
          void handleRecorderStopped(stagingId);
        }
      }
    };
    recorder.onstop = () => {
      void handleRecorderStopped(stagingId);
    };
  }

  async function startMediaRecorder(
    session: ContinueSessionInput,
    existingStream?: MediaStream,
  ) {
    if (!browserSupported) {
      throw new Error(t('recording.errors.browserUnsupported'));
    }
    await requestPersistentStorage();
    const selectedMimeType = selectRecorderMimeType();
    const stream =
      existingStream ??
      (await navigator.mediaDevices.getUserMedia({ audio: true }));
    streamRef.current = stream;
    const recorder = new MediaRecorder(
      stream,
      selectedMimeType ? { mimeType: selectedMimeType } : undefined,
    );
    mediaRecorderRef.current = recorder;
    activeSessionIdRef.current = session.stagingId;
    nextSeqRef.current = session.highestSeq + 1;
    startAtRef.current = Date.now();
    setElapsedSec(0);
    setInputState('ready');
    bindRecorder(recorder, stream, session.stagingId);
    await acquireWakeLock();
    recorder.start(1000);
    setRecorderState('recording');
  }

  async function startRecording(input: StartRecordingInput = {}) {
    if (!token) return;
    if (!browserSupported) {
      setError(t('recording.errors.browserUnsupported'));
      return;
    }
    setError(null);
    setIsBusy(true);
    setRecorderState('requesting');
    let stream: MediaStream | null = null;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const selectedMimeType = selectRecorderMimeType();
      if (!selectedMimeType) {
        throw new Error(t('recording.errors.browserUnsupported'));
      }
      const idempotencyKey = createId();
      const effectiveTitle = input.title ?? title ?? null;
      const staging = await initRecordingUpload(token, {
        idempotency_key: idempotencyKey,
        mime_type: selectedMimeType,
        title: effectiveTitle,
        initial_target_app: initialTarget?.app ?? null,
        initial_target_type: initialTarget?.type ?? null,
        initial_target_id: initialTarget?.id ?? null,
        linked_task_id: input.linkedTaskId ?? null,
      });
      const sessionState: RecordingSessionState = {
        stagingId: staging.id,
        userId,
        scopeKey,
        idempotencyKey,
        mimeType: selectedMimeType,
        title: effectiveTitle,
        source: sessionSource(source, initialTarget),
        initialTargetApp: initialTarget?.app ?? null,
        initialTargetType: initialTarget?.type ?? null,
        initialTargetId: initialTarget?.id ?? null,
        linkedTaskId: input.linkedTaskId ?? null,
        startedAt: Date.now(),
        completedAt: null,
        finalizeRequestedAt: null,
        lastChunkSeq: -1,
        lastUploadedSeq: -1,
        uploadCompletedAt: null,
        interruptedAt: null,
        interruptionReason: null,
      };
      await upsertSession(sessionState);
      await startMediaRecorder(
        {
          stagingId: staging.id,
          idempotencyKey,
          mimeType: selectedMimeType,
          linkedTaskId: input.linkedTaskId ?? null,
          highestSeq: staging.highest_seq,
        },
        stream,
      );
      stream = null;
    } catch (err) {
      stream?.getTracks().forEach((track) => track.stop());
      setRecorderState('idle');
      setError(
        err instanceof Error ? err.message : t('recording.errors.startFailed'),
      );
    } finally {
      setIsBusy(false);
    }
  }

  async function continueRecording(session: ContinueSessionInput) {
    setError(null);
    setIsBusy(true);
    setRecorderState('requesting');
    try {
      await updateSessionProgress(session.stagingId, {
        finalizeRequestedAt: null,
      });
      recorderRuntime.clearPendingFinalize(session.stagingId);
      await startMediaRecorder(session);
    } catch (err) {
      setRecorderState('idle');
      setError(
        err instanceof Error
          ? err.message
          : t('recording.errors.continueFailed'),
      );
    } finally {
      setIsBusy(false);
    }
  }

  function stopRecording() {
    const recorder = mediaRecorderRef.current;
    if (!recorder || recorder.state === 'inactive') {
      return;
    }
    setRecorderState('stopping');
    flushRecorder();
    try {
      recorder.stop();
    } catch {
      setRecorderState('idle');
      if (activeSessionIdRef.current) {
        void updateSessionProgress(activeSessionIdRef.current, {
          interruptedAt: Date.now(),
          interruptionReason: 'stop_failed',
        });
      }
      stopMediaStream();
      void releaseWakeLock();
    }
  }

  async function resumeUpload(stagingId: string) {
    setError(null);
    await recorderRuntime.refreshStats(stagingId);
    await pumpUploads(stagingId);
  }

  async function finalizeUploadedOnly(stagingId: string) {
    if (!token) return;
    setIsBusy(true);
    setRecorderState('uploading');
    try {
      const recording =
        await recorderRuntime.finalizeUploadedSession(stagingId);
      setRecorderState('saved');
      await emitSaved(recording);
      window.setTimeout(() => setRecorderState('idle'), 1200);
    } catch (err) {
      setRecorderState('idle');
      setError(
        err instanceof Error
          ? err.message
          : t('recording.errors.finalizeUploadedFailed'),
      );
    } finally {
      setIsBusy(false);
    }
  }

  async function importRecoveredSession(stagingId: string) {
    if (!token) return;
    setIsBusy(true);
    setRecorderState('uploading');
    try {
      const [blob, session] = await Promise.all([
        buildSessionBlob(stagingId),
        getSession(stagingId),
      ]);
      if (!blob) {
        throw new Error(t('recording.errors.noLocalRecordingToRecover'));
      }
      const target = session ? sessionTarget(session) : initialTarget;
      const startedAt = sessionStartedAt(session);
      const recording = await importRecording(token, blob, {
        title: session?.title ?? title ?? null,
        startedAt,
        durationSec: session?.startedAt
          ? Math.max(0, Math.round((Date.now() - session.startedAt) / 1000))
          : undefined,
        source: 'manual_upload',
        initialTarget: target,
        linkedTaskId: session?.linkedTaskId ?? null,
      });
      await clearSession(stagingId);
      setRecorderState('saved');
      await emitSaved(recording);
      window.setTimeout(() => setRecorderState('idle'), 1200);
    } catch (err) {
      setRecorderState('idle');
      setError(
        err instanceof Error
          ? err.message
          : t('recording.errors.originalUploadFailed'),
      );
    } finally {
      setIsBusy(false);
    }
  }

  async function importAudioFile(file: File, input: ImportAudioInput = {}) {
    if (!token) return;
    setIsBusy(true);
    setRecorderState('uploading');
    try {
      const startedAt = new Date();
      const recording = await importRecording(token, file, {
        title: input.title ?? title ?? file.name,
        startedAt,
        source: input.source ?? 'manual_upload',
        initialTarget,
        linkedTaskId: input.linkedTaskId ?? null,
      });
      setRecorderState('saved');
      await emitSaved(recording);
      window.setTimeout(() => setRecorderState('idle'), 1200);
    } catch (err) {
      setRecorderState('idle');
      setError(
        err instanceof Error
          ? err.message
          : t('recording.errors.audioUploadFailed'),
      );
    } finally {
      setIsBusy(false);
    }
  }

  async function discardSession(stagingId: string, remoteExists: boolean) {
    if (!token) {
      await clearSession(stagingId);
      return;
    }
    setIsBusy(true);
    try {
      if (remoteExists) {
        await discardRecordingUpload(token, stagingId);
      }
      await clearSession(stagingId);
      if (activeSessionIdRef.current === stagingId) {
        activeSessionIdRef.current = null;
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : t('recording.errors.discardFailed'),
      );
    } finally {
      setIsBusy(false);
    }
  }

  async function downloadRecoveredSession(stagingId: string): Promise<void> {
    const blob = await buildSessionBlob(stagingId);
    if (!blob) {
      throw new Error(t('recording.errors.noLocalRecordingToDownload'));
    }
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${stagingId}.webm`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  async function resumeRecoverableUploads() {
    if (!token) return;
    await recorderRuntime.resumeRecoverableUploads({ scopeKey });
  }

  acquireWakeLockRef.current = () => {
    void acquireWakeLock();
  };
  flushRecorderRef.current = flushRecorder;
  resumeRecoverableUploadsRef.current = () => {
    void resumeRecoverableUploads();
  };

  useEffect(() => {
    if (!isRecording) {
      return;
    }
    const timer = window.setInterval(() => {
      if (startAtRef.current != null) {
        setElapsedSec(
          Math.max(0, Math.floor((Date.now() - startAtRef.current) / 1000)),
        );
      }
    }, 1000);
    return () => window.clearInterval(timer);
  }, [isRecording]);

  useEffect(() => {
    const onVisibility = () => {
      if (document.visibilityState === 'hidden') {
        flushRecorderRef.current();
      } else if (mediaRecorderRef.current?.state === 'recording') {
        acquireWakeLockRef.current();
      }
    };
    const onPageHide = () => flushRecorderRef.current();
    const onFreeze = () => flushRecorderRef.current();
    const onResume = () => {
      resumeRecoverableUploadsRef.current();
    };
    document.addEventListener('visibilitychange', onVisibility);
    document.addEventListener('freeze', onFreeze as EventListener);
    document.addEventListener('resume', onResume as EventListener);
    window.addEventListener('pagehide', onPageHide);
    window.addEventListener('pageshow', onResume);
    window.addEventListener('online', onResume);
    const unbindBackgroundSync = bindRecordingBackgroundSync(onResume);
    return () => {
      document.removeEventListener('visibilitychange', onVisibility);
      document.removeEventListener('freeze', onFreeze as EventListener);
      document.removeEventListener('resume', onResume as EventListener);
      window.removeEventListener('pagehide', onPageHide);
      window.removeEventListener('pageshow', onResume);
      window.removeEventListener('online', onResume);
      unbindBackgroundSync();
    };
  }, []);

  useEffect(
    () => () => {
      recorderRuntime.cleanup();
      stopMediaStream();
      void releaseWakeLock();
    },
    [recorderRuntime],
  );

  return {
    browserSupported,
    error,
    persistWarning,
    wakeLockWarning,
    inputWarning,
    recorderState,
    isRecording,
    isBusy,
    elapsedSec,
    queuedBytes,
    uploadedBytes,
    startRecording,
    continueRecording,
    stopRecording,
    resumeUpload,
    finalizeUploadedOnly,
    importRecoveredSession,
    importAudioFile,
    discardSession,
    downloadRecoveredSession,
  };
}
