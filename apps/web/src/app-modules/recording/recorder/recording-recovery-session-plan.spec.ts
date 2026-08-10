import { describe, expect, it, vi } from 'vitest';

import type { RecordingUpload } from '../api/recording-api';
import type { RecordingSessionState } from './recording-session-db';
import {
  getRecordingRecoveryAction,
  planRecordingRecoverySession,
  runRecordingRecoveryAction,
  type RecordingRecoveryAction,
  type RecordingRecoveryActionKind,
  type RecordingRecoveryActionRunner,
} from './recording-recovery-session-plan';
import type { RecoverySessionItem } from './useRecordingRecovery';

function localSession(overrides: Partial<RecordingSessionState> = {}): RecordingSessionState {
  return {
    stagingId: 'staging-1',
    workspaceSlug: 'hq',
    scopeKey: 'hq:recording:unlinked',
    idempotencyKey: 'idem-1',
    mimeType: 'audio/webm',
    title: null,
    source: 'quick_record',
    initialTargetApp: null,
    initialTargetType: null,
    initialTargetId: null,
    linkedTaskId: null,
    startedAt: 1_700_000_000_000,
    completedAt: null,
    finalizeRequestedAt: null,
    lastChunkSeq: 2,
    lastUploadedSeq: 1,
    uploadCompletedAt: null,
    interruptedAt: null,
    interruptionReason: null,
    meetingId: null,
    ...overrides,
  };
}

function remoteUpload(overrides: Partial<RecordingUpload> = {}): RecordingUpload {
  return {
    id: 'staging-1',
    workspace_id: 'workspace-1',
    user_id: 'user-1',
    idempotency_key: 'idem-1',
    mime_type: 'audio/webm',
    status: 'uploading',
    bytes_received: 4096,
    highest_seq: 4,
    started_at: '2026-05-30T00:00:00Z',
    updated_at: '2026-05-30T00:00:00Z',
    expires_at: '2026-05-31T00:00:00Z',
    initial_target_app: null,
    initial_target_type: null,
    initial_target_id: null,
    linked_task_id: null,
    ...overrides,
  } as RecordingUpload;
}

function recoveryItem(overrides: Partial<RecoverySessionItem> = {}): RecoverySessionItem {
  return {
    stagingId: 'staging-1',
    localSession: null,
    remoteStaging: null,
    localBlob: null,
    previewUrl: null,
    localBytes: 0,
    uploadedLocalBytes: 0,
    ...overrides,
  };
}

function createRunner(): RecordingRecoveryActionRunner & {
  resumeUpload: ReturnType<typeof vi.fn>;
  continueRecording: ReturnType<typeof vi.fn>;
  downloadOriginal: ReturnType<typeof vi.fn>;
  importOriginal: ReturnType<typeof vi.fn>;
  finalizeUploaded: ReturnType<typeof vi.fn>;
  discard: ReturnType<typeof vi.fn>;
} {
  return {
    resumeUpload: vi.fn(async () => undefined),
    continueRecording: vi.fn(async () => undefined),
    downloadOriginal: vi.fn(async () => undefined),
    importOriginal: vi.fn(async () => undefined),
    finalizeUploaded: vi.fn(async () => undefined),
    discard: vi.fn(async () => undefined),
  };
}

function requireAction(
  plan: ReturnType<typeof planRecordingRecoverySession>,
  kind: RecordingRecoveryActionKind,
): RecordingRecoveryAction {
  const action = getRecordingRecoveryAction(plan, kind);
  expect(action).toBeDefined();
  return action as RecordingRecoveryAction;
}

describe('recording recovery session plan', () => {
  it('plans local and remote recovery with resume and continue actions', async () => {
    const item = recoveryItem({
      localSession: localSession({
        idempotencyKey: 'idem-local',
        linkedTaskId: 'task-1',
        lastChunkSeq: 7,
      }),
      remoteStaging: remoteUpload({ highest_seq: 9, bytes_received: 12_000 }),
      previewUrl: 'blob:preview',
      localBytes: 16_000,
    });

    const plan = planRecordingRecoverySession(item);

    expect(plan).toMatchObject({
      hasLocal: true,
      hasRemote: true,
      previewUrl: 'blob:preview',
      localBytes: 16_000,
      remoteBytes: 12_000,
    });
    expect(plan.actions.map((action) => action.kind)).toEqual([
      'resume-upload',
      'continue-recording',
      'download-original',
      'discard',
    ]);

    const continueAction = getRecordingRecoveryAction(plan, 'continue-recording');
    expect(continueAction).toMatchObject({
      kind: 'continue-recording',
      continueSession: {
        stagingId: 'staging-1',
        idempotencyKey: 'idem-local',
        mimeType: 'audio/webm',
        linkedTaskId: 'task-1',
        highestSeq: 9,
      },
    });

    const runner = createRunner();
    const refresh = vi.fn(async () => undefined);
    await runRecordingRecoveryAction(requireAction(plan, 'resume-upload'), runner, refresh);
    expect(runner.resumeUpload).toHaveBeenCalledWith('staging-1');
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it('plans local-only recovery for original download, import, and discard', async () => {
    const plan = planRecordingRecoverySession(
      recoveryItem({
        localSession: localSession(),
        localBytes: 2048,
      }),
    );

    expect(plan.actions.map((action) => action.kind)).toEqual([
      'download-original',
      'import-original',
      'discard',
    ]);

    const runner = createRunner();
    const refresh = vi.fn(async () => undefined);
    await runRecordingRecoveryAction(requireAction(plan, 'import-original'), runner, refresh);
    expect(runner.importOriginal).toHaveBeenCalledWith('staging-1');
    expect(refresh).toHaveBeenCalledTimes(1);

    await runRecordingRecoveryAction(requireAction(plan, 'download-original'), runner, refresh);
    expect(runner.downloadOriginal).toHaveBeenCalledWith('staging-1');
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it('plans remote-only recovery for finalize and remote discard', async () => {
    const plan = planRecordingRecoverySession(
      recoveryItem({
        remoteStaging: remoteUpload({ bytes_received: 5120 }),
      }),
    );

    expect(plan.actions.map((action) => action.kind)).toEqual([
      'finalize-uploaded',
      'discard',
    ]);
    expect(plan.remoteBytes).toBe(5120);

    const discardAction = getRecordingRecoveryAction(plan, 'discard');
    expect(discardAction).toMatchObject({
      kind: 'discard',
      discardRemote: true,
    });

    const runner = createRunner();
    const refresh = vi.fn(async () => undefined);
    await runRecordingRecoveryAction(requireAction(plan, 'discard'), runner, refresh);
    expect(runner.discard).toHaveBeenCalledWith('staging-1', true);
    expect(refresh).toHaveBeenCalledTimes(1);
  });
});
