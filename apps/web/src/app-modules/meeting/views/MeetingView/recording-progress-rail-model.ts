import type { MeetingRecordingStatus } from '../../api/meeting-api';

export const RECORDING_PROGRESS_STAGES = [
  { key: 'pending' },
  { key: 'transcribing' },
  { key: 'summarizing' },
  { key: 'extracting_insights' },
  { key: 'generating_doc' },
  { key: 'done' },
] as const satisfies ReadonlyArray<{ key: MeetingRecordingStatus }>;

export type RecordingProgressStageKey =
  (typeof RECORDING_PROGRESS_STAGES)[number]['key'];

export type RecordingProgressStageState = 'complete' | 'current' | 'upcoming';

export type RecordingProgressStageView = {
  key: RecordingProgressStageKey;
  state: RecordingProgressStageState;
  done: boolean;
  current: boolean;
  marker: number;
};

const FAILED_STAGE_INDEX = RECORDING_PROGRESS_STAGES.findIndex(
  (stage) => stage.key === 'generating_doc',
);

export function projectRecordingProgressStages(
  status: MeetingRecordingStatus,
): RecordingProgressStageView[] {
  const currentIndex = recordingStageIndex(status);
  const active = status !== 'failed' && status !== 'done';
  return RECORDING_PROGRESS_STAGES.map((stage, index) => {
    const done = index < currentIndex || status === 'done';
    const current = index === currentIndex && active;
    return {
      key: stage.key,
      state: done ? 'complete' : current ? 'current' : 'upcoming',
      done,
      current,
      marker: index + 1,
    };
  });
}

export function recordingStageIndex(status: MeetingRecordingStatus): number {
  const index = RECORDING_PROGRESS_STAGES.findIndex(
    (stage) => stage.key === status,
  );
  if (index >= 0) return index;
  if (status === 'failed') return FAILED_STAGE_INDEX;
  return 0;
}
