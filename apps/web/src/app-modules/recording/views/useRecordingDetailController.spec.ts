import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type {
  RecordingDetail,
  RecordingPublication,
  RecordingTarget,
} from '../api/recording-api';
import {
  useRecordingDetailController,
  type RecordingDetailBrowserAdapter,
  type RecordingDetailClient,
  type RecordingDetailConfirm,
  type RecordingDetailMessages,
} from './useRecordingDetailController';

function target(overrides: Partial<RecordingTarget> = {}): RecordingTarget {
  return {
    id: 'target-1',
    recording_id: 'recording-1',
    target_app: 'meeting',
    target_type: 'meeting',
    target_id: 'meeting-1',
    target_title: 'Planning sync',
    is_primary: true,
    sort_order: 0,
    added_by_id: 'user-1',
    created_at: '2026-05-30T00:00:00Z',
    ...overrides,
  };
}

function recording(overrides: Partial<RecordingDetail> = {}): RecordingDetail {
  return {
    id: 'recording-1',
    owner_id: 'user-1',
    title: 'Daily Standup',
    started_at: '2026-05-30T09:00:00Z',
    ended_at: null,
    duration_sec: 65,
    source: 'quick_record',
    storage_key: null,
    file_size: 1536,
    mime_type: 'audio/webm',
    audio_status: 'saved',
    transcript_status: 'done',
    summary_status: 'done',
    meeting_insight_status: 'done',
    progress_pct: 100,
    failure_reason: null,
    transcribe_started_at: null,
    transcribe_completed_at: null,
    created_at: '2026-05-30T09:00:00Z',
    updated_at: '2026-05-30T09:00:00Z',
    trashed_at: null,
    targets: [],
    result: {
      transcript_text: 'Transcript',
      summary_text: 'Summary',
      verifier_note: null,
      version: 1,
      generated_at: '2026-05-30T09:02:00Z',
      updated_at: '2026-05-30T09:02:00Z',
    },
    publications: [],
    ...overrides,
  } as RecordingDetail;
}

function messages(): RecordingDetailMessages {
  return {
    loadFailed: 'load failed',
    updateFailed: 'update failed',
    playbackFailed: 'playback failed',
    retryFailed: 'retry failed',
    publishFailed: 'publish failed',
    detachFailed: 'detach failed',
    detachConfirmTitle: 'Detach?',
    detachConfirmDescription: 'Remove this link?',
    detachConfirmLabel: 'Detach',
    detachCancelLabel: 'Cancel',
  };
}

function client(overrides: Partial<RecordingDetailClient> = {}) {
  const current = recording();
  return {
    getRecording: vi.fn().mockResolvedValue(current),
    updateRecording: vi.fn().mockResolvedValue(current),
    getPlaybackUrl: vi.fn().mockResolvedValue({ url: '/playback' }),
    fetchPlaybackBlobUrl: vi.fn().mockResolvedValue('blob:audio-1'),
    retryRecording: vi.fn().mockResolvedValue(current),
    publishToDocs: vi.fn().mockResolvedValue(publication()),
    attachTarget: vi.fn().mockResolvedValue(current),
    detachTarget: vi.fn().mockResolvedValue(current),
    ...overrides,
  } satisfies RecordingDetailClient;
}

function publication(
  overrides: Partial<RecordingPublication> = {},
): RecordingPublication {
  return {
    id: 'publication-1',
    target_app: 'docs',
    target_resource_id: 'doc-1',
    target_title: 'Daily Standup (v1)',
    result_version: 1,
    published_by_id: 'user-1',
    created_at: '2026-05-30T09:03:00Z',
    ...overrides,
  };
}

function browser(overrides: Partial<RecordingDetailBrowserAdapter> = {}) {
  return {
    revokeObjectUrl: vi.fn(),
    setTimeout: vi
      .fn()
      .mockReturnValue(1 as unknown as ReturnType<typeof setTimeout>),
    ...overrides,
  } satisfies RecordingDetailBrowserAdapter;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((innerResolve, innerReject) => {
    resolve = innerResolve;
    reject = innerReject;
  });
  return { promise, resolve, reject };
}

function renderController(
  options: {
    token?: string | null;

    recordingId?: string | null;
    client?: RecordingDetailClient;
    browser?: RecordingDetailBrowserAdapter;
    confirm?: RecordingDetailConfirm;
  } = {},
) {
  const testClient = options.client ?? client();
  const testBrowser = options.browser ?? browser();
  const confirm = options.confirm ?? vi.fn().mockResolvedValue(true);
  const rendered = renderHook(() =>
    useRecordingDetailController({
      token: options.token === undefined ? 'token-1' : options.token,
      recordingId:
        options.recordingId === undefined ? 'recording-1' : options.recordingId,
      messages: messages(),
      confirm,
      client: testClient,
      browser: testBrowser,
    }),
  );
  return { ...rendered, client: testClient, browser: testBrowser, confirm };
}

describe('useRecordingDetailController', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('loads the recording on mount and initializes the title draft', async () => {
    const current = recording({ title: 'Planning Review' });
    const testClient = client({
      getRecording: vi.fn().mockResolvedValue(current),
    });
    const { result } = renderController({ client: testClient });

    await waitFor(() => expect(result.current.state.loading).toBe(false));

    expect(testClient.getRecording).toHaveBeenCalledWith(
      'token-1',
      'recording-1',
    );
    expect(result.current.state.recording).toBe(current);
    expect(result.current.state.titleDraft).toBe('Planning Review');
  });

  it('treats missing token or recording id as a no-op', async () => {
    const cases = [
      { token: null, recordingId: 'recording-1' },
      { token: 'token-1', recordingId: null },
    ];

    for (const testCase of cases) {
      const testClient = client();
      const { result } = renderController({ ...testCase, client: testClient });

      await act(async () => {
        await result.current.actions.refresh();
        await result.current.actions.play();
        await result.current.actions.retry();
        await result.current.actions.publish();
        await result.current.actions.attachMeeting('meeting-1');
        await result.current.actions.detachTarget(target());
      });

      expect(testClient.getRecording).not.toHaveBeenCalled();
      expect(testClient.updateRecording).not.toHaveBeenCalled();
      expect(testClient.getPlaybackUrl).not.toHaveBeenCalled();
      expect(testClient.retryRecording).not.toHaveBeenCalled();
      expect(testClient.publishToDocs).not.toHaveBeenCalled();
      expect(testClient.attachTarget).not.toHaveBeenCalled();
      expect(testClient.detachTarget).not.toHaveBeenCalled();
    }
  });

  it('skips title save when the trimmed draft is unchanged', async () => {
    const testClient = client({
      getRecording: vi
        .fn()
        .mockResolvedValue(recording({ title: 'Daily Standup' })),
    });
    const { result } = renderController({ client: testClient });

    await waitFor(() => expect(result.current.state.recording).not.toBeNull());

    act(() => {
      result.current.actions.setTitleDraft('  Daily Standup  ');
    });
    await act(async () => {
      await result.current.actions.saveTitle();
    });

    expect(testClient.updateRecording).not.toHaveBeenCalled();
  });

  it('saves changed title drafts and updates the loaded recording', async () => {
    const updated = recording({ title: 'Customer Call' });
    const testClient = client({
      updateRecording: vi.fn().mockResolvedValue(updated),
    });
    const testBrowser = browser();
    const { result } = renderController({
      client: testClient,
      browser: testBrowser,
    });

    await waitFor(() => expect(result.current.state.recording).not.toBeNull());

    act(() => {
      result.current.actions.setTitleDraft(' Customer Call ');
    });
    await act(async () => {
      await result.current.actions.saveTitle();
    });

    expect(testClient.updateRecording).toHaveBeenCalledWith(
      'token-1',
      'recording-1',
      { title: 'Customer Call' },
    );
    expect(result.current.state.recording).toBe(updated);
    expect(result.current.state.titleDraft).toBe('Customer Call');
    expect(result.current.state.titleStatus).toBe('saved');
    expect(testBrowser.setTimeout).toHaveBeenCalledWith(
      expect.any(Function),
      1500,
    );
  });

  it('preserves a dirty title draft during a processing refresh', async () => {
    const processing = recording({
      title: 'Server title',
      summary_status: 'analyzing',
    });
    const refreshed = recording({
      title: 'Server title changed',
      summary_status: 'verifying',
    });
    const testClient = client({
      getRecording: vi
        .fn()
        .mockResolvedValueOnce(processing)
        .mockResolvedValueOnce(refreshed),
    });
    const { result } = renderController({ client: testClient });

    await waitFor(() =>
      expect(result.current.state.recording).toBe(processing),
    );
    act(() => result.current.actions.setTitleDraft('Unsaved local title'));
    await act(async () => {
      await result.current.actions.refresh();
    });

    expect(result.current.state.recording).toBe(refreshed);
    expect(result.current.state.titleDraft).toBe('Unsaved local title');
    expect(result.current.state.titleDirty).toBe(true);
  });

  it('creates playback blob URLs and revokes the previous object URL', async () => {
    const testClient = client({
      getPlaybackUrl: vi.fn().mockResolvedValue({ url: '/playback' }),
      fetchPlaybackBlobUrl: vi
        .fn()
        .mockResolvedValueOnce('blob:audio-1')
        .mockResolvedValueOnce('blob:audio-2'),
    });
    const testBrowser = browser();
    const { result, unmount } = renderController({
      client: testClient,
      browser: testBrowser,
    });

    await waitFor(() => expect(result.current.state.recording).not.toBeNull());

    await act(async () => {
      await result.current.actions.play();
    });
    expect(result.current.state.playbackUrl).toBe('blob:audio-1');

    await act(async () => {
      await result.current.actions.play();
    });

    expect(testClient.getPlaybackUrl).toHaveBeenCalledTimes(2);
    expect(testClient.fetchPlaybackBlobUrl).toHaveBeenCalledWith(
      'token-1',
      '/playback',
    );
    expect(testBrowser.revokeObjectUrl).toHaveBeenCalledWith('blob:audio-1');
    expect(result.current.state.playbackUrl).toBe('blob:audio-2');

    unmount();
    expect(testBrowser.revokeObjectUrl).toHaveBeenCalledWith('blob:audio-2');
  });

  it('tracks retry busy state and replaces the recording', async () => {
    const pendingRetry = deferred<RecordingDetail>();
    const updated = recording({ transcript_status: 'done' });
    const testClient = client({
      getRecording: vi
        .fn()
        .mockResolvedValue(recording({ transcript_status: 'failed' })),
      retryRecording: vi.fn().mockReturnValue(pendingRetry.promise),
    });
    const { result } = renderController({ client: testClient });

    await waitFor(() => expect(result.current.derived.retryable).toBe(true));

    let retryPromise!: Promise<void>;
    act(() => {
      retryPromise = result.current.actions.retry();
    });
    await waitFor(() => expect(result.current.state.busy).toBe('retry'));

    await act(async () => {
      pendingRetry.resolve(updated);
      await retryPromise;
    });

    expect(testClient.retryRecording).toHaveBeenCalledWith(
      'token-1',
      'recording-1',
    );
    expect(result.current.state.busy).toBeNull();
    expect(result.current.state.recording).toBe(updated);
  });

  it('publishes the current result once and appends the returned document', async () => {
    const pendingPublish = deferred<RecordingPublication>();
    const published = publication();
    const testClient = client({
      publishToDocs: vi.fn().mockReturnValue(pendingPublish.promise),
    });
    const { result } = renderController({ client: testClient });

    await waitFor(() => expect(result.current.state.recording).not.toBeNull());
    let first!: Promise<void>;
    act(() => {
      first = result.current.actions.publish();
      void result.current.actions.publish();
    });
    await waitFor(() => expect(result.current.state.busy).toBe('publish'));
    expect(testClient.publishToDocs).toHaveBeenCalledTimes(1);

    await act(async () => {
      pendingPublish.resolve(published);
      await first;
    });

    expect(result.current.state.busy).toBeNull();
    expect(result.current.state.recording?.publications).toEqual([published]);
  });

  it('surfaces publish failures without mutating publications', async () => {
    const testClient = client({
      publishToDocs: vi.fn().mockRejectedValue(new Error('publish denied')),
    });
    const { result } = renderController({ client: testClient });

    await waitFor(() => expect(result.current.state.recording).not.toBeNull());
    await act(async () => {
      await result.current.actions.publish();
    });

    expect(result.current.state.error).toBe('publish denied');
    expect(result.current.state.recording?.publications).toEqual([]);
  });

  it('attaches targets and detaches only after confirmation', async () => {
    const meeting = target({ id: 'meeting-target' });
    const task = target({
      id: 'task-target',
      target_app: 'pms',
      target_type: 'task',
      target_id: 'task-1',
    });
    const withBoth = recording({ targets: [meeting, task] });
    const withoutMeeting = recording({ targets: [task] });
    const confirm = vi
      .fn()
      .mockResolvedValueOnce(false)
      .mockResolvedValueOnce(true);
    const testClient = client({
      attachTarget: vi.fn().mockResolvedValue(withBoth),
      detachTarget: vi.fn().mockResolvedValue(withoutMeeting),
    });
    const { result } = renderController({ client: testClient, confirm });

    await waitFor(() => expect(result.current.state.recording).not.toBeNull());

    await act(async () => {
      await result.current.actions.attachTask('task-1');
    });

    expect(testClient.attachTarget).toHaveBeenCalledWith(
      'token-1',
      'recording-1',
      {
        target_app: 'pms',
        target_type: 'task',
        target_id: 'task-1',
      },
    );
    expect(result.current.state.recording).toBe(withBoth);
    expect(result.current.derived.taskTargets).toEqual([task]);

    await act(async () => {
      await result.current.actions.detachTarget(meeting);
    });
    expect(confirm).toHaveBeenCalledWith({
      title: 'Detach?',
      description: 'Remove this link?',
      confirmLabel: 'Detach',
      cancelLabel: 'Cancel',
      variant: 'danger',
    });
    expect(testClient.detachTarget).not.toHaveBeenCalled();

    act(() => {
      result.current.actions.setMeetingPickerOpen(true);
    });
    await act(async () => {
      await result.current.actions.detachTarget(meeting);
    });

    expect(testClient.detachTarget).toHaveBeenCalledWith(
      'token-1',
      'recording-1',
      'meeting-target',
    );
    expect(result.current.state.recording).toBe(withoutMeeting);
  });

  it('keeps picker and doc preview state local to the controller', async () => {
    const { result } = renderController();

    await waitFor(() => expect(result.current.state.recording).not.toBeNull());

    act(() => {
      result.current.actions.setMeetingPickerOpen(true);
      result.current.actions.setTaskPickerOpen(true);
      result.current.actions.setDocPreview({
        docId: 'doc-1',
        label: 'Minutes',
      });
    });

    expect(result.current.state.meetingPickerOpen).toBe(true);
    expect(result.current.state.taskPickerOpen).toBe(true);
    expect(result.current.state.docPreview).toEqual({
      docId: 'doc-1',
      label: 'Minutes',
    });

    act(() => {
      result.current.actions.setMeetingPickerOpen(false);
      result.current.actions.setTaskPickerOpen(false);
      result.current.actions.setDocPreview(null);
    });

    expect(result.current.state.meetingPickerOpen).toBe(false);
    expect(result.current.state.taskPickerOpen).toBe(false);
    expect(result.current.state.docPreview).toBeNull();
  });
});
