import { useEffect, useRef, useState } from 'react';

import {
  completeRecordingStaging,
  discardRecordingStaging,
  importMeetingRecording,
  initRecordingStaging,
  uploadRecordingChunk,
  type MeetingDetail,
} from '../../api/meeting-api';
import {
  appendChunk,
  buildSessionBlob,
  clearSession,
  getChunks,
  getPendingChunks,
  getSession,
  markChunkUploaded,
  markSessionComplete,
  updateSessionProgress,
  upsertSession,
  type RecordingSessionState,
} from '../../api/recording-db';

interface ContinueSessionInput {
  stagingId: string;
  idempotencyKey: string;
  mimeType: string;
  linkedTaskId: string | null;
  highestSeq: number;
}

interface RecorderOptions {
  workspaceSlug: string;
  meetingId: string;
  token: string | null;
  onMeetingUpdated: (meeting: MeetingDetail) => void;
}

const RECORDER_MIME = 'audio/webm;codecs=opus';

function bytesToNumber(blobs: Blob[]): number {
  return blobs.reduce((total, blob) => total + blob.size, 0);
}

function createId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

async function sha256Hex(blob: Blob): Promise<string> {
  const buffer = await blob.arrayBuffer();
  const hash = await crypto.subtle.digest('SHA-256', buffer);
  const bytes = Array.from(new Uint8Array(hash));
  return bytes.map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

export function useChunkedRecorder({
  workspaceSlug,
  meetingId,
  token,
  onMeetingUpdated,
}: RecorderOptions) {
  const [isRecording, setIsRecording] = useState(false);
  const [isBusy, setIsBusy] = useState(false);
  const [elapsedSec, setElapsedSec] = useState(0);
  const [queuedBytes, setQueuedBytes] = useState(0);
  const [uploadedBytes, setUploadedBytes] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [persistWarning, setPersistWarning] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const activeSessionIdRef = useRef<string | null>(null);
  const activeLinkedTaskIdRef = useRef<string | null>(null);
  const nextSeqRef = useRef(0);
  const startAtRef = useRef<number | null>(null);
  const pendingFinalizeRef = useRef<string | null>(null);
  const pumpingRef = useRef<Set<string>>(new Set());
  const retryTimersRef = useRef<Map<string, number>>(new Map());

  const browserSupported =
    typeof window !== 'undefined' &&
    typeof MediaRecorder !== 'undefined' &&
    typeof navigator !== 'undefined' &&
    typeof navigator.mediaDevices?.getUserMedia === 'function' &&
    MediaRecorder.isTypeSupported(RECORDER_MIME);

  async function refreshStats(stagingId: string) {
    const chunks = await getChunks(stagingId);
    setQueuedBytes(bytesToNumber(chunks.map((chunk) => chunk.blob)));
    setUploadedBytes(
      bytesToNumber(chunks.filter((chunk) => chunk.uploadedAt != null).map((chunk) => chunk.blob)),
    );
  }

  async function requestPersistentStorage() {
    try {
      if (!navigator.storage?.persist) {
        return;
      }
      const persisted = await navigator.storage.persist();
      if (!persisted) {
        setPersistWarning('브라우저 저장공간 정책에 따라 복구 가능 기간이 짧아질 수 있습니다.');
      } else {
        setPersistWarning(null);
      }
    } catch {
      setPersistWarning('브라우저 저장공간 보호 상태를 확인하지 못했습니다.');
    }
  }

  function clearRetryTimer(stagingId: string) {
    const timer = retryTimersRef.current.get(stagingId);
    if (timer != null) {
      window.clearTimeout(timer);
      retryTimersRef.current.delete(stagingId);
    }
  }

  async function finalizeIfReady(stagingId: string) {
    if (!token || pendingFinalizeRef.current !== stagingId) {
      return;
    }
    const pending = await getPendingChunks(stagingId);
    if (pending.length > 0) {
      return;
    }
    const session = await getSession(stagingId);
    setIsBusy(true);
    try {
      const updated = await completeRecordingStaging(
        token,
        workspaceSlug,
        meetingId,
        stagingId,
        {
        duration_sec_estimate: session?.startedAt ? Math.max(0, Math.round((Date.now() - session.startedAt) / 1000)) : undefined,
        },
      );
      pendingFinalizeRef.current = null;
      await markSessionComplete(stagingId);
      await clearSession(stagingId);
      activeSessionIdRef.current = null;
      setQueuedBytes(0);
      setUploadedBytes(0);
      onMeetingUpdated(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : '녹음 마무리에 실패했습니다.');
    } finally {
      setIsBusy(false);
    }
  }

  async function pumpUploads(stagingId: string): Promise<void> {
    if (!token || pumpingRef.current.has(stagingId)) {
      return;
    }
    pumpingRef.current.add(stagingId);
    clearRetryTimer(stagingId);
    try {
      while (true) {
        const pending = await getPendingChunks(stagingId);
        if (pending.length === 0) {
          break;
        }
        const chunk = pending[0];
        const ack = await uploadRecordingChunk(
          token,
          workspaceSlug,
          meetingId,
          stagingId,
          chunk.seq,
          chunk.blob,
          chunk.sha256,
        );
        await markChunkUploaded(stagingId, chunk.seq);
        await updateSessionProgress(stagingId, {
          lastUploadedSeq: Math.max(ack.highest_seq, chunk.seq),
        });
        await refreshStats(stagingId);
      }
      await finalizeIfReady(stagingId);
    } catch (err) {
      setError(err instanceof Error ? err.message : '녹음 청크 업로드에 실패했습니다.');
      const timer = window.setTimeout(() => {
        void pumpUploads(stagingId);
      }, 3000);
      retryTimersRef.current.set(stagingId, timer);
    } finally {
      pumpingRef.current.delete(stagingId);
    }
  }

  async function attachChunk(stagingId: string, seq: number, blob: Blob) {
    const digest = await sha256Hex(blob);
    await appendChunk({
      stagingId,
      seq,
      blob,
      sha256: digest,
      uploadedAt: null,
      createdAt: Date.now(),
    });
    await updateSessionProgress(stagingId, { lastChunkSeq: seq });
    await refreshStats(stagingId);
    void pumpUploads(stagingId);
  }

  function stopMediaStream() {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }

  function bindRecorder(recorder: MediaRecorder, stagingId: string) {
    recorder.ondataavailable = (event) => {
      if (event.data.size === 0) {
        return;
      }
      const seq = nextSeqRef.current++;
      void attachChunk(stagingId, seq, event.data);
    };
    recorder.onstop = () => {
      setIsRecording(false);
      stopMediaStream();
      pendingFinalizeRef.current = stagingId;
      void pumpUploads(stagingId);
    };
  }

  async function startMediaRecorder(session: ContinueSessionInput) {
    if (!browserSupported) {
      throw new Error('이 브라우저에서는 라이브 녹음을 지원하지 않습니다.');
    }
    await requestPersistentStorage();
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    streamRef.current = stream;
    const recorder = new MediaRecorder(stream, { mimeType: RECORDER_MIME });
    mediaRecorderRef.current = recorder;
    activeSessionIdRef.current = session.stagingId;
    activeLinkedTaskIdRef.current = session.linkedTaskId;
    nextSeqRef.current = session.highestSeq + 1;
    startAtRef.current = Date.now();
    setElapsedSec(0);
    bindRecorder(recorder, session.stagingId);
    recorder.start(2000);
    setIsRecording(true);
  }

  async function startRecording(linkedTaskId: string | null) {
    if (!token) return;
    setError(null);
    setIsBusy(true);
    try {
      const idempotencyKey = createId();
      const staging = await initRecordingStaging(token, workspaceSlug, meetingId, {
        idempotency_key: idempotencyKey,
        mime_type: 'audio/webm',
        linked_task_id: linkedTaskId,
      });
      const sessionState: RecordingSessionState = {
        stagingId: staging.id,
        meetingId,
        idempotencyKey,
        mimeType: staging.mime_type,
        linkedTaskId: linkedTaskId ?? null,
        startedAt: Date.now(),
        completedAt: null,
        lastChunkSeq: -1,
        lastUploadedSeq: -1,
        uploadCompletedAt: null,
      };
      await upsertSession(sessionState);
      await startMediaRecorder({
        stagingId: staging.id,
        idempotencyKey,
        mimeType: staging.mime_type,
        linkedTaskId: linkedTaskId ?? null,
        highestSeq: staging.highest_seq,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : '녹음을 시작할 수 없습니다.');
    } finally {
      setIsBusy(false);
    }
  }

  async function continueRecording(session: ContinueSessionInput) {
    setError(null);
    setIsBusy(true);
    try {
      await startMediaRecorder(session);
    } catch (err) {
      setError(err instanceof Error ? err.message : '복구 후 녹음을 시작할 수 없습니다.');
    } finally {
      setIsBusy(false);
    }
  }

  function flushRecorder() {
    const recorder = mediaRecorderRef.current;
    if (!recorder || recorder.state !== 'recording') {
      return;
    }
    try {
      recorder.requestData();
    } catch {
      // Best effort only.
    }
  }

  function stopRecording() {
    const recorder = mediaRecorderRef.current;
    if (!recorder) {
      return;
    }
    flushRecorder();
    try {
      recorder.stop();
    } catch {
      setIsRecording(false);
      stopMediaStream();
    }
  }

  async function resumeUpload(stagingId: string) {
    setError(null);
    await refreshStats(stagingId);
    await pumpUploads(stagingId);
  }

  async function finalizeUploadedOnly(stagingId: string) {
    if (!token) return;
    setIsBusy(true);
    try {
      const updated = await completeRecordingStaging(
        token,
        workspaceSlug,
        meetingId,
        stagingId,
        {},
      );
      await clearSession(stagingId);
      onMeetingUpdated(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : '업로드 분량 확정에 실패했습니다.');
    } finally {
      setIsBusy(false);
    }
  }

  async function importRecoveredSession(stagingId: string, linkedTaskId: string | null) {
    if (!token) return;
    setIsBusy(true);
    try {
      const blob = await buildSessionBlob(stagingId);
      if (!blob) {
        throw new Error('복구할 로컬 녹음이 없습니다.');
      }
      const updated = await importMeetingRecording(
        token,
        workspaceSlug,
        meetingId,
        blob,
        linkedTaskId,
      );
      await clearSession(stagingId);
      onMeetingUpdated(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : '원본 파일 업로드에 실패했습니다.');
    } finally {
      setIsBusy(false);
    }
  }

  async function importAudioFile(file: File, linkedTaskId: string | null) {
    if (!token) return;
    setIsBusy(true);
    try {
      const updated = await importMeetingRecording(
        token,
        workspaceSlug,
        meetingId,
        file,
        linkedTaskId,
      );
      onMeetingUpdated(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : '음성 파일 업로드에 실패했습니다.');
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
        await discardRecordingStaging(token, workspaceSlug, meetingId, stagingId);
      }
      await clearSession(stagingId);
      if (activeSessionIdRef.current === stagingId) {
        activeSessionIdRef.current = null;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '복구 세션을 폐기할 수 없습니다.');
    } finally {
      setIsBusy(false);
    }
  }

  async function downloadRecoveredSession(stagingId: string): Promise<void> {
    const blob = await buildSessionBlob(stagingId);
    if (!blob) {
      throw new Error('다운로드할 로컬 녹음이 없습니다.');
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

  useEffect(() => {
    if (!isRecording) {
      return;
    }
    const timer = window.setInterval(() => {
      if (startAtRef.current != null) {
        setElapsedSec(Math.max(0, Math.floor((Date.now() - startAtRef.current) / 1000)));
      }
    }, 1000);
    return () => window.clearInterval(timer);
  }, [isRecording]);

  useEffect(() => {
    const onVisibility = () => {
      if (document.visibilityState === 'hidden') {
        flushRecorder();
      }
    };
    const onPageHide = () => flushRecorder();
    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('pagehide', onPageHide);
    return () => {
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('pagehide', onPageHide);
    };
  }, []);

  useEffect(() => () => {
    retryTimersRef.current.forEach((timer) => window.clearTimeout(timer));
    stopMediaStream();
  }, []);

  return {
    browserSupported,
    error,
    persistWarning,
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
