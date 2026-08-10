import { formatByteSize } from '@/src/platform/format/byte-size';

import type {
  Recording,
  RecordingTarget,
  RecordingViewFilter,
} from '../api/recording-api';

export type RecordingCategoryFilter = 'all' | 'meeting' | 'task' | 'unlinked';
export type RecordingSort = 'latest' | 'oldest' | 'title';

export function formatElapsed(totalSec: number): string {
  const hours = Math.floor(totalSec / 3600);
  const minutes = Math.floor((totalSec % 3600) / 60);
  const seconds = totalSec % 60;
  return [hours, minutes, seconds]
    .map((value) => String(value).padStart(2, '0'))
    .join(':');
}

export function formatBytes(bytes: number): string {
  return formatByteSize(bytes);
}

export function titleFor(recording: Recording, fallback: string): string {
  return recording.title?.trim() || fallback;
}

export function hasFailedStage(recording: Recording): boolean {
  return [
    recording.audio_status,
    recording.transcript_status,
    recording.raw_transcript_doc_status,
    recording.minutes_doc_status,
    recording.meeting_insight_status,
  ].some((status) => status === 'failed');
}

export function normalizeViewFilter(value: string | null): RecordingViewFilter {
  if (
    value === 'needs_review' ||
    value === 'processing' ||
    value === 'failed' ||
    value === 'archived'
  ) {
    return value;
  }
  return 'mine';
}

export function normalizeCategoryFilter(
  value: string | null,
): RecordingCategoryFilter {
  return value === 'meeting' || value === 'task' || value === 'unlinked'
    ? value
    : 'all';
}

export function listTitleKey(
  view: RecordingViewFilter,
  category: RecordingCategoryFilter,
): string {
  if (view === 'processing') return 'apps:recording.views.processing';
  if (view === 'failed') return 'apps:recording.views.failed';
  if (view === 'archived') return 'apps:recording.views.archived';
  if (category === 'meeting') return 'apps:recording.views.meeting';
  if (category === 'task') return 'apps:recording.views.task';
  if (category === 'unlinked') return 'apps:recording.views.unlinked';
  return 'apps:recording.views.mine';
}

function recordingTargets(recording: Recording): RecordingTarget[] {
  return recording.targets ?? [];
}

function isMeetingTarget(target: RecordingTarget): boolean {
  return (
    target.target_app === 'meeting' &&
    target.target_type === 'meeting'
  );
}

function isTaskTarget(target: RecordingTarget): boolean {
  return target.target_app === 'pms' && target.target_type === 'task';
}

export function recordingMatchesCategory(
  recording: Recording,
  category: RecordingCategoryFilter,
): boolean {
  if (category === 'all') return true;
  const targets = recordingTargets(recording);
  if (category === 'meeting') return targets.some(isMeetingTarget);
  if (category === 'task') return targets.some(isTaskTarget);
  return !targets.some(
    (target) => isMeetingTarget(target) || isTaskTarget(target),
  );
}

export function searchableRecordingText(recording: Recording): string {
  return [
    recording.title,
    recording.mime_type,
    ...recordingTargets(recording).flatMap((target) => [
      target.target_title ?? '',
      target.target_app,
      target.target_type,
    ]),
  ].join(' ');
}

export function compareRecordings(
  left: Recording,
  right: Recording,
  sort: RecordingSort,
  locale: string,
): number {
  if (sort === 'title') {
    return titleFor(left, '').localeCompare(titleFor(right, ''), locale, {
      sensitivity: 'base',
    });
  }
  const leftTime = new Date(left.started_at).getTime();
  const rightTime = new Date(right.started_at).getTime();
  return sort === 'oldest' ? leftTime - rightTime : rightTime - leftTime;
}

export function connectionChips(recording: Recording): Array<{
  id: string;
  labelKey: string;
  title: string | null;
}> {
  const chips = [];
  for (const target of recordingTargets(recording)) {
    if (!isMeetingTarget(target) && !isTaskTarget(target)) {
      continue;
    }
    chips.push({
      id: target.id,
      labelKey: isMeetingTarget(target)
        ? 'apps:recording.filters.categories.meeting'
        : 'apps:recording.filters.categories.task',
      title: target.target_title ?? null,
    });
  }

  return chips.length > 0
    ? chips
    : [
        {
          id: 'unlinked',
          labelKey: 'apps:recording.filters.categories.unlinked',
          title: null,
        },
      ];
}
