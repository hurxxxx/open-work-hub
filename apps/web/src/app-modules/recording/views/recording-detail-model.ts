import { buildAppHref } from '@open-work-hub/contracts/app-routes';

import type { Recording, RecordingTarget } from '../api/recording-api';

export type RecordingStageState = 'done' | 'inProgress' | 'pending' | 'failed';
export type RecordingStageKey = 'audio' | 'transcript' | 'summary';

export interface RecordingStage {
  key: RecordingStageKey;
  state: RecordingStageState;
}

export interface RecordingStageSummary {
  stages: RecordingStage[];
  failedStage: RecordingStage | null;
  activeStage: RecordingStage | null;
  allDone: boolean;
}

export interface RecordingTargetGroups {
  meetingTargets: RecordingTarget[];
  taskTargets: RecordingTarget[];
  otherTargets: RecordingTarget[];
}

export function recordingPipelineState(value: string): RecordingStageState {
  if (value === 'done' || value === 'saved') return 'done';
  if (value === 'failed') return 'failed';
  if (
    value === 'uploading' ||
    value === 'creating' ||
    value === 'transcribing' ||
    value === 'analyzing' ||
    value === 'verifying'
  ) {
    return 'inProgress';
  }
  return 'pending';
}

export function deriveRecordingStages(recording: Recording): RecordingStage[] {
  return [
    { key: 'audio', state: recordingPipelineState(recording.audio_status) },
    {
      key: 'transcript',
      state: recordingPipelineState(recording.transcript_status),
    },
    {
      key: 'summary',
      state: recordingPipelineState(recording.summary_status),
    },
  ];
}

export function summarizeRecordingStages(
  recording: Recording,
): RecordingStageSummary {
  const stages = deriveRecordingStages(recording);
  const failedStage = stages.find((stage) => stage.state === 'failed') ?? null;
  const activeStage = failedStage
    ? null
    : (stages.find((stage) => stage.state === 'inProgress') ?? null);

  return {
    stages,
    failedStage,
    activeStage,
    allDone: stages.every((stage) => stage.state === 'done'),
  };
}

export function isRecordingRetryable(recording: Recording): boolean {
  return [
    recording.audio_status,
    recording.transcript_status,
    recording.summary_status,
  ].some((status) => status === 'failed');
}

export function groupRecordingTargets(
  targets: RecordingTarget[] | null | undefined,
): RecordingTargetGroups {
  const groups: RecordingTargetGroups = {
    meetingTargets: [],
    taskTargets: [],
    otherTargets: [],
  };

  for (const target of targets ?? []) {
    if (target.target_app === 'meeting') {
      groups.meetingTargets.push(target);
    } else if (target.target_app === 'pms') {
      groups.taskTargets.push(target);
    } else {
      groups.otherTargets.push(target);
    }
  }

  return groups;
}

export function recordingTargetHref(
  workspaceSlug: string,
  target: RecordingTarget,
): string | null {
  if (target.target_app === 'meeting') {
    return buildAppHref({
      routeId: 'meeting.detail',
      workspaceSlug,
      pathParams: { meetingId: target.target_id },
    });
  }
  if (target.target_app === 'pms') {
    return buildAppHref({
      routeId: 'pms.root',
      workspaceSlug,
      queryParams: { task: target.target_id },
    });
  }
  if (target.target_app === 'docs') {
    return buildAppHref({
      routeId: 'docs.document',
      workspaceSlug,
      pathParams: { docId: target.target_id },
    });
  }
  return null;
}
