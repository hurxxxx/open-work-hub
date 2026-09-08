import { createElement, lazy, Suspense } from 'react';

import type {
  LinkedRecordingListProps,
  LinkedRecordingsForTargetProps,
} from './views/LinkedRecordingsList';
import type { TaskPickerModalProps } from './views/TaskPickerModal';

export {
  getRecordingRecoveryAction,
  planRecordingRecoverySession,
  runRecordingRecoveryAction,
} from './recorder/recording-recovery-session-plan';
export type {
  RecordingRecoveryAction,
  RecordingRecoveryActionKind,
  RecordingRecoveryContinueSessionInput,
  RecordingRecoveryPlan,
} from './recorder/recording-recovery-session-plan';
export type {
  RecordingSessionSource,
  RecordingSessionState,
  RecordingTargetRef,
} from './recorder/recording-session-db';
export { RecordingRecoveryBanner } from './recorder/RecordingRecoveryBanner';
export { useRecordingRecovery } from './recorder/useRecordingRecovery';
export type { RecoverySessionItem } from './recorder/useRecordingRecovery';
export {
  selectRecorderMimeType,
  useResilientRecorder,
} from './recorder/useResilientRecorder';
export type {
  LinkedRecordingListItem,
  LinkedRecordingListProps,
  LinkedRecordingsForTargetProps,
} from './views/LinkedRecordingsList';
export type { TaskPickerModalProps } from './views/TaskPickerModal';

const LazyTaskPickerModal = lazy(() =>
  import('./views/TaskPickerModal').then((module) => ({
    default: module.TaskPickerModal,
  })),
);

const LazyLinkedRecordingList = lazy(() =>
  import('./views/LinkedRecordingsList').then((module) => ({
    default: module.LinkedRecordingList,
  })),
);

const LazyLinkedRecordingsForTarget = lazy(() =>
  import('./views/LinkedRecordingsList').then((module) => ({
    default: module.LinkedRecordingsForTarget,
  })),
);

export function TaskPickerModal(props: TaskPickerModalProps) {
  return createElement(
    Suspense,
    { fallback: null },
    createElement(LazyTaskPickerModal, props),
  );
}

export function LinkedRecordingList(props: LinkedRecordingListProps) {
  return createElement(
    Suspense,
    { fallback: null },
    createElement(LazyLinkedRecordingList, props),
  );
}

export function LinkedRecordingsForTarget(
  props: LinkedRecordingsForTargetProps,
) {
  return createElement(
    Suspense,
    { fallback: null },
    createElement(LazyLinkedRecordingsForTarget, props),
  );
}
