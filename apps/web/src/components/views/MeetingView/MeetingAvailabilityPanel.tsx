import { useMemo, useState } from 'react';
import { CalendarDays, Loader2 } from 'lucide-react';

import type { MeetingUser } from '@/src/domains/meeting/meeting-api';

import { MeetingAvailabilityModal } from './MeetingAvailabilityModal';
import {
  addLocalDays,
  buildAvailabilityConflicts,
  formatAvailabilityBlockLabel,
  startOfAvailabilityWeek,
  useMeetingAvailabilityQuery,
} from './meetingAvailability';

interface MeetingAvailabilityPanelProps {
  workspaceSlug: string;
  attendeeUsers: MeetingUser[];
  meetingStart: Date | null;
  meetingEnd: Date | null;
}

function isValidMeetingWindow(start: Date | null, end: Date | null): start is Date {
  return Boolean(start && end && end > start);
}

export function MeetingAvailabilityPanel({
  workspaceSlug,
  attendeeUsers,
  meetingStart,
  meetingEnd,
}: MeetingAvailabilityPanelProps) {
  const [modalOpen, setModalOpen] = useState(false);
  const attendeeIds = useMemo(
    () => attendeeUsers.map((user) => user.id),
    [attendeeUsers],
  );
  const rangeStart = meetingStart ? startOfAvailabilityWeek(meetingStart) : null;
  const rangeEnd = rangeStart ? addLocalDays(rangeStart, 7) : null;
  const canQuery = isValidMeetingWindow(meetingStart, meetingEnd) && attendeeIds.length > 0;
  const { items, loading, error } = useMeetingAvailabilityQuery({
    workspaceSlug,
    userIds: attendeeIds,
    rangeStart,
    rangeEnd,
    enabled: canQuery,
  });

  const conflicts = useMemo(() => {
    if (!meetingStart || !meetingEnd || meetingEnd <= meetingStart) {
      return [];
    }
    return buildAvailabilityConflicts(items, meetingStart, meetingEnd);
  }, [items, meetingEnd, meetingStart]);

  return (
    <>
      <div className="space-y-2 rounded-md border border-app-border bg-app-surface px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="app-text-control-sm text-app-ink/70">참석자 일정</p>
            <p className="app-text-caption text-app-ink/45">
              선택된 참석자들의 같은 주 일정을 비교합니다.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setModalOpen(true)}
            disabled={!canQuery}
            className="app-text-control-sm inline-flex items-center gap-1.5 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-1.5 text-app-ink transition-colors hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-45"
          >
            <CalendarDays size={14} />
            <span>스케줄 보기</span>
          </button>
        </div>

        {!meetingStart || !meetingEnd || meetingEnd <= meetingStart ? (
          <p className="app-text-caption text-app-ink/50">
            시작/종료 시각을 먼저 올바르게 입력하세요.
          </p>
        ) : attendeeUsers.length === 0 ? (
          <p className="app-text-caption text-app-ink/50">
            참석자를 추가하면 일정 충돌을 확인할 수 있습니다.
          </p>
        ) : loading ? (
          <div className="flex items-center gap-2 text-app-ink/50">
            <Loader2 size={14} className="animate-spin" />
            <span className="app-text-caption">참석자 일정을 확인하는 중...</span>
          </div>
        ) : error ? (
          <p className="app-text-caption text-[var(--ui-color-warning)]">{error}</p>
        ) : conflicts.length === 0 ? (
          <p className="app-text-caption text-emerald-600">
            현재 선택된 시간과 겹치는 참석자 일정이 없습니다.
          </p>
        ) : (
          <div className="space-y-2">
            <p className="app-text-caption text-[var(--ui-color-warning)]">
              일정 충돌 {conflicts.length}건이 감지되었습니다.
            </p>
            <div className="space-y-1">
              {conflicts.map((item) => (
                <div
                  key={`${item.userId}-${item.block.id}`}
                  className="app-text-caption flex items-center justify-between gap-3 rounded-md border border-[var(--ui-color-warning)]/20 bg-[var(--ui-color-warning)]/10 px-3 py-2 text-app-ink"
                >
                  <span className="font-medium">{item.fullName}</span>
                  <span className="truncate text-app-ink/60">
                    {formatAvailabilityBlockLabel(item.block)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <MeetingAvailabilityModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        workspaceSlug={workspaceSlug}
        attendeeUsers={attendeeUsers}
        meetingStart={meetingStart}
        meetingEnd={meetingEnd}
      />
    </>
  );
}
