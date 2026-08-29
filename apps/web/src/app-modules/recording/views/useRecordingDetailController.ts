import { useCallback, useEffect, useMemo, useReducer, useRef } from 'react';

import {
  attachRecordingTarget,
  detachRecordingTarget,
  fetchRecordingPlaybackBlobUrl,
  getRecording,
  getRecordingPlaybackUrl,
  publishRecordingToDocs,
  retryRecording,
  updateRecording,
  type RecordingDetail,
  type RecordingPublication,
  type RecordingTarget,
  type RecordingPlaybackResponse,
} from '../api/recording-api';
import {
  groupRecordingTargets,
  isRecordingRetryable,
} from './recording-detail-model';

export type RecordingDetailDocPreviewTarget = {
  docId: string;
  label: string;
};

export interface RecordingDetailMessages {
  loadFailed: string;
  updateFailed: string;
  playbackFailed: string;
  retryFailed: string;
  publishFailed: string;
  detachFailed: string;
  detachConfirmTitle: string;
  detachConfirmDescription: string;
  detachConfirmLabel: string;
  detachCancelLabel: string;
}

export interface RecordingDetailConfirmOptions {
  title: string;
  description: string;
  confirmLabel: string;
  cancelLabel: string;
  variant: 'danger';
}

export type RecordingDetailConfirm = (
  options: RecordingDetailConfirmOptions,
) => Promise<boolean>;

export interface RecordingDetailClient {
  getRecording(
    token: string,
    workspaceSlug: string,
    recordingId: string,
  ): Promise<RecordingDetail>;
  updateRecording(
    token: string,
    workspaceSlug: string,
    recordingId: string,
    payload: { title?: string | null },
  ): Promise<RecordingDetail>;
  getPlaybackUrl(
    token: string,
    workspaceSlug: string,
    recordingId: string,
  ): Promise<RecordingPlaybackResponse>;
  fetchPlaybackBlobUrl(token: string, playbackUrl: string): Promise<string>;
  retryRecording(
    token: string,
    workspaceSlug: string,
    recordingId: string,
  ): Promise<RecordingDetail>;
  attachTarget(
    token: string,
    workspaceSlug: string,
    recordingId: string,
    payload: {
      target_app: string;
      target_type: string;
      target_id: string;
      is_primary?: boolean;
      sort_order?: number;
    },
  ): Promise<RecordingDetail>;
  detachTarget(
    token: string,
    workspaceSlug: string,
    recordingId: string,
    targetId: string,
  ): Promise<RecordingDetail>;
  publishToDocs(
    token: string,
    workspaceSlug: string,
    recordingId: string,
  ): Promise<RecordingPublication>;
}

export interface RecordingDetailBrowserAdapter {
  revokeObjectUrl(url: string): void;
  setTimeout(callback: VoidFunction, ms: number): number;
}

export interface RecordingDetailState {
  recording: RecordingDetail | null;
  titleDraft: string;
  titleDirty: boolean;
  playbackUrl: string | null;
  loading: boolean;
  busy: string | null;
  error: string | null;
  titleStatus: 'idle' | 'saving' | 'saved';
  meetingPickerOpen: boolean;
  taskPickerOpen: boolean;
  docPreview: RecordingDetailDocPreviewTarget | null;
}

type RecordingDetailAction =
  | { type: 'load:start' }
  | {
      type: 'load:success';
      recording: RecordingDetail;
      preserveTitleDraft: boolean;
    }
  | { type: 'load:fail'; message: string }
  | { type: 'title-draft:set'; value: string; dirty: boolean }
  | { type: 'title:save-start' }
  | { type: 'title:save-success'; recording: RecordingDetail }
  | { type: 'title:save-fail'; message: string }
  | { type: 'title-status:idle' }
  | { type: 'playback:start' }
  | { type: 'playback:success'; url: string }
  | { type: 'playback:fail'; message: string }
  | { type: 'retry:start' }
  | { type: 'retry:success'; recording: RecordingDetail }
  | { type: 'retry:fail'; message: string }
  | { type: 'publish:start' }
  | { type: 'publish:success'; publication: RecordingPublication }
  | { type: 'publish:fail'; message: string }
  | { type: 'recording:set'; recording: RecordingDetail }
  | { type: 'recording:set-fail'; message: string }
  | { type: 'target-detach:start'; targetId: string }
  | { type: 'target-detach:success'; recording: RecordingDetail }
  | { type: 'target-detach:fail'; message: string }
  | { type: 'meeting-picker:set'; open: boolean }
  | { type: 'task-picker:set'; open: boolean }
  | { type: 'doc-preview:set'; target: RecordingDetailDocPreviewTarget | null };

export const defaultRecordingDetailClient: RecordingDetailClient = {
  getRecording,
  updateRecording,
  getPlaybackUrl: getRecordingPlaybackUrl,
  fetchPlaybackBlobUrl: fetchRecordingPlaybackBlobUrl,
  retryRecording,
  publishToDocs: publishRecordingToDocs,
  attachTarget: attachRecordingTarget,
  detachTarget: detachRecordingTarget,
};

const defaultBrowserAdapter: RecordingDetailBrowserAdapter = {
  revokeObjectUrl: (url) => URL.revokeObjectURL(url),
  setTimeout: (callback, ms) => window.setTimeout(callback, ms),
};

const INITIAL_RECORDING_DETAIL_STATE: RecordingDetailState = {
  recording: null,
  titleDraft: '',
  titleDirty: false,
  playbackUrl: null,
  loading: false,
  busy: null,
  error: null,
  titleStatus: 'idle',
  meetingPickerOpen: false,
  taskPickerOpen: false,
  docPreview: null,
};

function recordingDetailReducer(
  state: RecordingDetailState,
  action: RecordingDetailAction,
): RecordingDetailState {
  switch (action.type) {
    case 'load:start':
      return { ...state, loading: true, error: null };
    case 'load:success':
      return {
        ...state,
        recording: action.recording,
        titleDraft:
          action.preserveTitleDraft && state.titleDirty
            ? state.titleDraft
            : (action.recording.title ?? ''),
        titleDirty: action.preserveTitleDraft ? state.titleDirty : false,
        loading: false,
      };
    case 'load:fail':
      return { ...state, loading: false, error: action.message };
    case 'title-draft:set':
      return { ...state, titleDraft: action.value, titleDirty: action.dirty };
    case 'title:save-start':
      return { ...state, titleStatus: 'saving', error: null };
    case 'title:save-success':
      return {
        ...state,
        recording: action.recording,
        titleDraft: action.recording.title ?? '',
        titleDirty: false,
        titleStatus: 'saved',
      };
    case 'title:save-fail':
      return { ...state, titleStatus: 'idle', error: action.message };
    case 'title-status:idle':
      return { ...state, titleStatus: 'idle' };
    case 'playback:start':
      return { ...state, busy: 'playback', error: null };
    case 'playback:success':
      return { ...state, playbackUrl: action.url, busy: null };
    case 'playback:fail':
      return { ...state, busy: null, error: action.message };
    case 'retry:start':
      return { ...state, busy: 'retry', error: null };
    case 'retry:success':
      return { ...state, recording: action.recording, busy: null };
    case 'retry:fail':
      return { ...state, busy: null, error: action.message };
    case 'publish:start':
      return { ...state, busy: 'publish', error: null };
    case 'publish:success':
      if (!state.recording) return { ...state, busy: null };
      return {
        ...state,
        busy: null,
        recording: {
          ...state.recording,
          publications: [
            ...(state.recording.publications ?? []).filter(
              (publication) => publication.id !== action.publication.id,
            ),
            action.publication,
          ],
        },
      };
    case 'publish:fail':
      return { ...state, busy: null, error: action.message };
    case 'recording:set':
      return { ...state, recording: action.recording, error: null };
    case 'recording:set-fail':
      return { ...state, error: action.message };
    case 'target-detach:start':
      return { ...state, busy: action.targetId, error: null };
    case 'target-detach:success':
      return { ...state, recording: action.recording, busy: null };
    case 'target-detach:fail':
      return { ...state, busy: null, error: action.message };
    case 'meeting-picker:set':
      return { ...state, meetingPickerOpen: action.open };
    case 'task-picker:set':
      return { ...state, taskPickerOpen: action.open };
    case 'doc-preview:set':
      return { ...state, docPreview: action.target };
    default:
      return state;
  }
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

export interface UseRecordingDetailControllerOptions {
  token: string | null | undefined;
  workspaceSlug: string | null | undefined;
  recordingId: string | null | undefined;
  messages: RecordingDetailMessages;
  confirm: RecordingDetailConfirm;
  client?: RecordingDetailClient;
  browser?: RecordingDetailBrowserAdapter;
}

export function useRecordingDetailController({
  token,
  workspaceSlug,
  recordingId,
  messages,
  confirm,
  client = defaultRecordingDetailClient,
  browser = defaultBrowserAdapter,
}: UseRecordingDetailControllerOptions) {
  const [state, dispatch] = useReducer(
    recordingDetailReducer,
    INITIAL_RECORDING_DETAIL_STATE,
  );
  const savedTitleRef = useRef('');
  const playbackObjectUrlRef = useRef<string | null>(null);
  const publishInFlightRef = useRef(false);

  const refresh = useCallback(
    async (options: { preserveTitleDraft?: boolean } = {}) => {
      if (!token || !workspaceSlug || !recordingId) return;
      dispatch({ type: 'load:start' });
      try {
        const next = await client.getRecording(
          token,
          workspaceSlug,
          recordingId,
        );
        savedTitleRef.current = next.title ?? '';
        dispatch({
          type: 'load:success',
          recording: next,
          preserveTitleDraft: options.preserveTitleDraft ?? true,
        });
      } catch (err) {
        dispatch({
          type: 'load:fail',
          message: errorMessage(err, messages.loadFailed),
        });
      }
    },
    [client, messages.loadFailed, recordingId, token, workspaceSlug],
  );

  useEffect(() => {
    void refresh({ preserveTitleDraft: false });
  }, [refresh]);

  useEffect(() => {
    const recording = state.recording;
    if (!recording) {
      return;
    }
    const statuses = [
      recording.audio_status,
      recording.transcript_status,
      recording.summary_status,
    ];
    const processing = statuses.some((status) =>
      [
        'uploading',
        'transcribing',
        'analyzing',
        'verifying',
        'pending',
      ].includes(status),
    );
    if (!processing || statuses.includes('failed')) {
      return;
    }
    const timer = window.setTimeout(() => void refresh(), 3000);
    return () => window.clearTimeout(timer);
  }, [refresh, state.recording]);

  useEffect(
    () => () => {
      if (playbackObjectUrlRef.current) {
        browser.revokeObjectUrl(playbackObjectUrlRef.current);
      }
    },
    [browser],
  );

  const setTitleDraft = useCallback((value: string) => {
    dispatch({
      type: 'title-draft:set',
      value,
      dirty: value.trim() !== savedTitleRef.current.trim(),
    });
  }, []);

  const saveTitle = useCallback(async () => {
    if (!token || !workspaceSlug || !state.recording) return;
    const trimmed = state.titleDraft.trim();
    if (trimmed === savedTitleRef.current.trim()) return;
    dispatch({ type: 'title:save-start' });
    try {
      const next = await client.updateRecording(
        token,
        workspaceSlug,
        state.recording.id,
        { title: trimmed || null },
      );
      savedTitleRef.current = next.title ?? '';
      dispatch({ type: 'title:save-success', recording: next });
      browser.setTimeout(() => dispatch({ type: 'title-status:idle' }), 1500);
    } catch (err) {
      dispatch({
        type: 'title:save-fail',
        message: errorMessage(err, messages.updateFailed),
      });
    }
  }, [
    browser,
    client,
    messages.updateFailed,
    state.recording,
    state.titleDraft,
    token,
    workspaceSlug,
  ]);

  const play = useCallback(async () => {
    if (!token || !workspaceSlug || !state.recording) return;
    dispatch({ type: 'playback:start' });
    try {
      const playback = await client.getPlaybackUrl(
        token,
        workspaceSlug,
        state.recording.id,
      );
      const nextUrl = await client.fetchPlaybackBlobUrl(token, playback.url);
      if (playbackObjectUrlRef.current) {
        browser.revokeObjectUrl(playbackObjectUrlRef.current);
      }
      playbackObjectUrlRef.current = nextUrl.startsWith('blob:')
        ? nextUrl
        : null;
      dispatch({ type: 'playback:success', url: nextUrl });
    } catch (err) {
      dispatch({
        type: 'playback:fail',
        message: errorMessage(err, messages.playbackFailed),
      });
    }
  }, [
    browser,
    client,
    messages.playbackFailed,
    state.recording,
    token,
    workspaceSlug,
  ]);

  const retry = useCallback(async () => {
    if (!token || !workspaceSlug || !state.recording) return;
    dispatch({ type: 'retry:start' });
    try {
      const next = await client.retryRecording(
        token,
        workspaceSlug,
        state.recording.id,
      );
      dispatch({ type: 'retry:success', recording: next });
    } catch (err) {
      dispatch({
        type: 'retry:fail',
        message: errorMessage(err, messages.retryFailed),
      });
    }
  }, [client, messages.retryFailed, state.recording, token, workspaceSlug]);

  const publish = useCallback(async () => {
    if (
      !token ||
      !workspaceSlug ||
      !state.recording ||
      state.busy ||
      publishInFlightRef.current
    ) {
      return;
    }
    publishInFlightRef.current = true;
    dispatch({ type: 'publish:start' });
    try {
      const publication = await client.publishToDocs(
        token,
        workspaceSlug,
        state.recording.id,
      );
      dispatch({ type: 'publish:success', publication });
    } catch (err) {
      dispatch({
        type: 'publish:fail',
        message: errorMessage(err, messages.publishFailed),
      });
    } finally {
      publishInFlightRef.current = false;
    }
  }, [
    client,
    messages.publishFailed,
    state.busy,
    state.recording,
    token,
    workspaceSlug,
  ]);

  const attachTarget = useCallback(
    async (payload: {
      target_app: string;
      target_type: string;
      target_id: string;
      is_primary?: boolean;
      sort_order?: number;
    }) => {
      if (!token || !workspaceSlug || !state.recording) return;
      try {
        const next = await client.attachTarget(
          token,
          workspaceSlug,
          state.recording.id,
          payload,
        );
        dispatch({ type: 'recording:set', recording: next });
      } catch (err) {
        dispatch({
          type: 'recording:set-fail',
          message: errorMessage(err, messages.updateFailed),
        });
      }
    },
    [client, messages.updateFailed, state.recording, token, workspaceSlug],
  );

  const attachMeeting = useCallback(
    async (meetingId: string) =>
      attachTarget({
        target_app: 'meeting',
        target_type: 'meeting',
        target_id: meetingId,
      }),
    [attachTarget],
  );

  const attachTask = useCallback(
    async (taskId: string) =>
      attachTarget({
        target_app: 'pms',
        target_type: 'task',
        target_id: taskId,
      }),
    [attachTarget],
  );

  const detachTarget = useCallback(
    async (target: RecordingTarget) => {
      if (!token || !workspaceSlug || !state.recording) return;
      const ok = await confirm({
        title: messages.detachConfirmTitle,
        description: messages.detachConfirmDescription,
        confirmLabel: messages.detachConfirmLabel,
        cancelLabel: messages.detachCancelLabel,
        variant: 'danger',
      });
      if (!ok) return;
      dispatch({
        type: 'target-detach:start',
        targetId: target.id,
      });
      try {
        const next = await client.detachTarget(
          token,
          workspaceSlug,
          state.recording.id,
          target.id,
        );
        dispatch({ type: 'target-detach:success', recording: next });
      } catch (err) {
        dispatch({
          type: 'target-detach:fail',
          message: errorMessage(err, messages.detachFailed),
        });
      }
    },
    [
      client,
      confirm,
      messages.detachCancelLabel,
      messages.detachConfirmDescription,
      messages.detachConfirmLabel,
      messages.detachConfirmTitle,
      messages.detachFailed,
      state.recording,
      token,
      workspaceSlug,
    ],
  );

  const setMeetingPickerOpen = useCallback((open: boolean) => {
    dispatch({ type: 'meeting-picker:set', open });
  }, []);

  const setTaskPickerOpen = useCallback((open: boolean) => {
    dispatch({ type: 'task-picker:set', open });
  }, []);

  const setDocPreview = useCallback(
    (target: RecordingDetailDocPreviewTarget | null) => {
      dispatch({ type: 'doc-preview:set', target });
    },
    [],
  );

  const targetGroups = useMemo(
    () => groupRecordingTargets(state.recording?.targets),
    [state.recording?.targets],
  );

  const retryable = state.recording
    ? isRecordingRetryable(state.recording)
    : false;

  return {
    state,
    derived: {
      ...targetGroups,
      retryable,
    },
    actions: {
      refresh,
      setTitleDraft,
      saveTitle,
      play,
      retry,
      publish,
      attachMeeting,
      attachTask,
      detachTarget,
      setMeetingPickerOpen,
      setTaskPickerOpen,
      setDocPreview,
    },
  };
}
