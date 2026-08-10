import type { RecoverySessionItem } from './useRecordingRecovery';

export interface RecordingRecoveryContinueSessionInput {
  stagingId: string;
  idempotencyKey: string;
  mimeType: string;
  linkedTaskId: string | null;
  highestSeq: number;
}

export type RecordingRecoveryActionKind =
  | 'resume-upload'
  | 'continue-recording'
  | 'download-original'
  | 'import-original'
  | 'finalize-uploaded'
  | 'discard';

interface BaseRecordingRecoveryAction {
  kind: RecordingRecoveryActionKind;
  stagingId: string;
  refreshAfter: boolean;
}

export interface ResumeRecordingUploadAction extends BaseRecordingRecoveryAction {
  kind: 'resume-upload';
}

export interface ContinueRecoveredRecordingAction extends BaseRecordingRecoveryAction {
  kind: 'continue-recording';
  continueSession: RecordingRecoveryContinueSessionInput;
}

export interface DownloadRecoveredRecordingAction extends BaseRecordingRecoveryAction {
  kind: 'download-original';
}

export interface ImportRecoveredRecordingAction extends BaseRecordingRecoveryAction {
  kind: 'import-original';
}

export interface FinalizeUploadedRecordingAction extends BaseRecordingRecoveryAction {
  kind: 'finalize-uploaded';
}

export interface DiscardRecoveredRecordingAction extends BaseRecordingRecoveryAction {
  kind: 'discard';
  discardRemote: boolean;
}

export type RecordingRecoveryAction =
  | ResumeRecordingUploadAction
  | ContinueRecoveredRecordingAction
  | DownloadRecoveredRecordingAction
  | ImportRecoveredRecordingAction
  | FinalizeUploadedRecordingAction
  | DiscardRecoveredRecordingAction;

export interface RecordingRecoveryPlan {
  stagingId: string;
  hasLocal: boolean;
  hasRemote: boolean;
  previewUrl: string | null;
  localBytes: number;
  remoteBytes: number;
  actions: RecordingRecoveryAction[];
}

export interface RecordingRecoveryActionRunner {
  resumeUpload: (stagingId: string) => Promise<unknown> | unknown;
  continueRecording: (session: RecordingRecoveryContinueSessionInput) => Promise<unknown> | unknown;
  downloadOriginal: (stagingId: string) => Promise<unknown> | unknown;
  importOriginal: (stagingId: string) => Promise<unknown> | unknown;
  finalizeUploaded: (stagingId: string) => Promise<unknown> | unknown;
  discard: (stagingId: string, discardRemote: boolean) => Promise<unknown> | unknown;
}

export function planRecordingRecoverySession(item: RecoverySessionItem): RecordingRecoveryPlan {
  const localSession = item.localSession;
  const remoteStaging = item.remoteStaging;
  const hasLocal = localSession != null;
  const hasRemote = remoteStaging != null;
  const actions: RecordingRecoveryAction[] = [];

  if (localSession && remoteStaging) {
    actions.push({
      kind: 'resume-upload',
      stagingId: item.stagingId,
      refreshAfter: true,
    });
    actions.push({
      kind: 'continue-recording',
      stagingId: item.stagingId,
      refreshAfter: false,
      continueSession: {
        stagingId: item.stagingId,
        idempotencyKey: localSession.idempotencyKey,
        mimeType: localSession.mimeType,
        linkedTaskId: localSession.linkedTaskId,
        highestSeq: Math.max(localSession.lastChunkSeq, remoteStaging.highest_seq),
      },
    });
  }

  if (localSession) {
    actions.push({
      kind: 'download-original',
      stagingId: item.stagingId,
      refreshAfter: false,
    });
  }

  if (localSession && !remoteStaging) {
    actions.push({
      kind: 'import-original',
      stagingId: item.stagingId,
      refreshAfter: true,
    });
  }

  if (!localSession && remoteStaging) {
    actions.push({
      kind: 'finalize-uploaded',
      stagingId: item.stagingId,
      refreshAfter: true,
    });
  }

  actions.push({
    kind: 'discard',
    stagingId: item.stagingId,
    refreshAfter: true,
    discardRemote: hasRemote,
  });

  return {
    stagingId: item.stagingId,
    hasLocal,
    hasRemote,
    previewUrl: item.previewUrl,
    localBytes: item.localBytes,
    remoteBytes: remoteStaging?.bytes_received ?? 0,
    actions,
  };
}

export function getRecordingRecoveryAction(
  plan: RecordingRecoveryPlan,
  kind: RecordingRecoveryActionKind,
): RecordingRecoveryAction | undefined {
  return plan.actions.find((action) => action.kind === kind);
}

export async function runRecordingRecoveryAction(
  action: RecordingRecoveryAction,
  runner: RecordingRecoveryActionRunner,
  refresh: () => Promise<unknown> | unknown,
): Promise<void> {
  switch (action.kind) {
    case 'resume-upload':
      await runner.resumeUpload(action.stagingId);
      break;
    case 'continue-recording':
      await runner.continueRecording(action.continueSession);
      break;
    case 'download-original':
      await runner.downloadOriginal(action.stagingId);
      break;
    case 'import-original':
      await runner.importOriginal(action.stagingId);
      break;
    case 'finalize-uploaded':
      await runner.finalizeUploaded(action.stagingId);
      break;
    case 'discard':
      await runner.discard(action.stagingId, action.discardRemote);
      break;
  }

  if (action.refreshAfter) {
    await refresh();
  }
}
