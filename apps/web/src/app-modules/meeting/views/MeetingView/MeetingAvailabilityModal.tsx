import { useEffect, useMemo, useState } from 'react';
import { Dialog } from '@ai-do/ui';
import { ChevronLeft, ChevronRight, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type {
  MeetingAvailabilityBlock,
  MeetingUser,
} from '../../api/meeting-api';

import {
  AVAILABILITY_NAME_COLUMN_PX,
  addLocalDays,
  formatAvailabilityBlockLabel,
  formatAvailabilityDayLabel,
  formatAvailabilityWeekLabel,
  parseAvailabilityBoundary,
  startOfAvailabilityWeek,
  useMeetingAvailabilityQuery,
} from './meetingAvailability';

interface MeetingAvailabilityModalProps {
  isOpen: boolean;
  onClose: () => void;
  workspaceSlug: string;
  attendeeUsers: MeetingUser[];
  meetingStart: Date | null;
  meetingEnd: Date | null;
  timeZone: string;
}

const HOURS = ['00', '03', '06', '09', '12', '15', '18', '21'];
const ROW_HEIGHT_PX = 96;
const EVENT_BLOCK_HEIGHT_PX = 72;

function getBlockColor(block: MeetingAvailabilityBlock): string {
  if (!block.masked && block.sourceType === 'planner_event') {
    return 'rgba(20, 184, 166, 0.22)';
  }
  return 'rgba(245, 158, 11, 0.2)';
}

function getBlockBorder(block: MeetingAvailabilityBlock): string {
  if (!block.masked && block.sourceType === 'planner_event') {
    return 'rgba(15, 118, 110, 0.9)';
  }
  return 'rgba(217, 119, 6, 0.9)';
}

function getBlockPositionPct(
  block: MeetingAvailabilityBlock,
  weekStart: Date,
  weekEnd: Date,
): { leftPct: number; widthPct: number } | null {
  const start = parseAvailabilityBoundary(block.start, block.allDay);
  const end = parseAvailabilityBoundary(block.end, block.allDay);
  const weekStartMs = weekStart.getTime();
  const weekEndMs = weekEnd.getTime();
  const clampedStart = Math.max(start.getTime(), weekStartMs);
  const clampedEnd = Math.min(end.getTime(), weekEndMs);
  if (clampedEnd <= clampedStart) {
    return null;
  }
  const weekMs = weekEndMs - weekStartMs;
  return {
    leftPct: ((clampedStart - weekStartMs) / weekMs) * 100,
    widthPct: ((clampedEnd - clampedStart) / weekMs) * 100,
  };
}

export function MeetingAvailabilityModal({
  isOpen,
  onClose,
  workspaceSlug,
  attendeeUsers,
  meetingStart,
  meetingEnd,
  timeZone,
}: MeetingAvailabilityModalProps) {
  const { t, i18n } = useTranslation('apps');
  const attendeeIds = useMemo(
    () => attendeeUsers.map((user) => user.id),
    [attendeeUsers],
  );
  const [weekStart, setWeekStart] = useState<Date | null>(
    meetingStart ? startOfAvailabilityWeek(meetingStart) : null,
  );
  const meetingStartTime = meetingStart?.getTime() ?? null;

  useEffect(() => {
    if (!isOpen || meetingStartTime === null) return;
    setWeekStart(startOfAvailabilityWeek(new Date(meetingStartTime)));
  }, [isOpen, meetingStartTime]);

  const weekEnd = weekStart ? addLocalDays(weekStart, 7) : null;
  const { items, loading, error } = useMeetingAvailabilityQuery({
    workspaceSlug,
    userIds: attendeeIds,
    rangeStart: weekStart,
    rangeEnd: weekEnd,
    enabled: isOpen && attendeeIds.length > 0,
  });

  const itemByUserId = useMemo(
    () => new Map(items.map((item) => [item.userId, item])),
    [items],
  );
  const meetingHighlight = useMemo(() => {
    if (!weekStart || !weekEnd || !meetingStart || !meetingEnd || meetingEnd <= meetingStart) {
      return null;
    }
    const highlightBlock: MeetingAvailabilityBlock = {
      id: 'current-meeting',
      start: meetingStart.toISOString(),
      end: meetingEnd.toISOString(),
      allDay: false,
      sourceType: 'meeting',
      masked: false,
      title: t('meeting.availabilityCurrentMeeting'),
      location: null,
    };
    return getBlockPositionPct(highlightBlock, weekStart, weekEnd);
  }, [meetingEnd, meetingStart, t, weekEnd, weekStart]);

  return (
    <Dialog
        closeLabel={t('common:actions.close')}
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={t('meeting.availabilityModalTitle')}
      description={t('meeting.availabilityModalDescription')}
      fullSize
      dismissOnInteractOutside={false}
    >
      <div className="flex h-full min-h-0 flex-col gap-4 text-app-ink">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="app-text-control text-app-ink">
              {weekStart
                ? formatAvailabilityWeekLabel(weekStart, timeZone, i18n.language)
                : t('meeting.availabilitySelectRange')}
            </p>
            <p className="app-text-caption text-app-ink/50">
              {t('meeting.availabilityPrivateBusy')}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => weekStart && setWeekStart(addLocalDays(weekStart, -7))}
              disabled={!weekStart}
              className="flex h-8 w-8 items-center justify-center rounded-md border border-app-border text-app-ink transition-colors hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-40"
              aria-label={t('meeting.availabilityPreviousWeek')}
            >
              <ChevronLeft size={16} />
            </button>
            <button
              type="button"
              onClick={() => weekStart && setWeekStart(addLocalDays(weekStart, 7))}
              disabled={!weekStart}
              className="flex h-8 w-8 items-center justify-center rounded-md border border-app-border text-app-ink transition-colors hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-40"
              aria-label={t('meeting.availabilityNextWeek')}
            >
              <ChevronRight size={16} />
            </button>
          </div>
        </div>

        {attendeeUsers.length === 0 ? (
          <div className="rounded-md border border-app-border bg-app-surface px-4 py-6 text-center text-app-ink/50">
            {t('meeting.availabilityNoAttendees')}
          </div>
        ) : error ? (
          <div className="rounded-md border border-[var(--ui-color-warning)]/40 bg-[var(--ui-color-warning)]/10 px-4 py-3 text-[var(--ui-color-warning)]">
            {error}
          </div>
        ) : loading && items.length === 0 ? (
          <div className="flex items-center justify-center py-10 text-app-ink/50">
            <Loader2 size={18} className="animate-spin" />
          </div>
        ) : (
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-app-border bg-app-surface">
            <div className="flex border-b border-app-border bg-app-surface">
              <div
                className="shrink-0 border-r border-app-border px-4 py-3"
                style={{ width: AVAILABILITY_NAME_COLUMN_PX }}
              >
                <div className="app-text-overline text-app-ink/50">
                  {t('meeting.availabilityAttendee')}
                </div>
              </div>
              <div className="flex min-w-0 flex-1 flex-col">
                <div className="flex border-b border-app-border/70">
                  {weekStart
                    ? Array.from({ length: 7 }, (_, index) => {
                        const date = addLocalDays(weekStart, index);
                        return (
                          <div
                            key={index}
                            className="min-w-0 flex-1 border-r border-app-border/60 px-3 py-2 last:border-r-0"
                          >
                            <div className="app-text-control-sm truncate text-app-ink">
                              {formatAvailabilityDayLabel(date, timeZone, i18n.language)}
                            </div>
                          </div>
                        );
                      })
                    : null}
                </div>
                <div className="flex bg-app-bg/30">
                  {Array.from({ length: 7 }, (_, dayIndex) => (
                    <div
                      key={dayIndex}
                      className="relative min-w-0 flex-1 border-r border-app-border/50 px-2 py-1 last:border-r-0"
                    >
                      <div className="flex justify-between text-[10px] uppercase tracking-[0.18em] text-app-ink/35">
                        {HOURS.map((hour) => (
                          <span key={hour}>{hour}</span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="ui-scrollbar min-h-0 flex-1 overflow-y-auto">
              {attendeeUsers.map((attendee) => {
                const item = itemByUserId.get(attendee.id);
                const blocks = item?.blocks ?? [];
                return (
                  <div
                    key={attendee.id}
                    className="flex border-b border-app-border last:border-b-0"
                  >
                    <div
                      className="shrink-0 border-r border-app-border px-4 py-3"
                      style={{ width: AVAILABILITY_NAME_COLUMN_PX }}
                    >
                      <div className="app-text-control text-app-ink">{attendee.full_name}</div>
                      <div className="app-text-caption truncate text-app-ink/45">
                        {attendee.email}
                      </div>
                    </div>
                    <div className="relative min-w-0 flex-1 py-2">
                      <div
                        className="relative rounded-md"
                        style={{ height: ROW_HEIGHT_PX - 16 }}
                      >
                        <div className="pointer-events-none absolute inset-0 flex">
                          {Array.from({ length: 7 }, (_, dayIndex) => (
                            <div
                              key={dayIndex}
                              className="min-w-0 flex-1 border-r border-app-border/40 last:border-r-0"
                              style={{
                                backgroundImage: `repeating-linear-gradient(to right, transparent 0, transparent calc(100%/48 - 1px), rgba(148, 163, 184, 0.12) calc(100%/48 - 1px), rgba(148, 163, 184, 0.12) calc(100%/48))`,
                                backgroundColor: 'rgba(248, 250, 252, 0.03)',
                              }}
                            />
                          ))}
                        </div>
                        {meetingHighlight ? (
                          <div
                            className="absolute inset-y-1 rounded-md border border-dashed border-app-accent/70 bg-app-accent/10"
                            style={{
                              left: `${meetingHighlight.leftPct}%`,
                              width: `${meetingHighlight.widthPct}%`,
                            }}
                            title={t('meeting.availabilityCurrentMeetingTime')}
                          />
                        ) : null}
                        {blocks.map((block) => {
                          if (!weekStart || !weekEnd) return null;
                          const position = getBlockPositionPct(block, weekStart, weekEnd);
                          if (!position) return null;
                          return (
                            <div
                              key={block.id}
                              className="absolute top-1/2 -translate-y-1/2 overflow-hidden rounded-md border px-2 py-1"
                              style={{
                                left: `${position.leftPct}%`,
                                width: `${position.widthPct}%`,
                                height: EVENT_BLOCK_HEIGHT_PX,
                                backgroundColor: getBlockColor(block),
                                borderColor: getBlockBorder(block),
                              }}
                              title={formatAvailabilityBlockLabel(
                                block,
                                timeZone,
                                i18n.language,
                                { busy: t('meeting.busy'), schedule: t('meeting.schedule') },
                              )}
                            >
                              <div className="truncate text-[12px] font-medium text-app-ink">
                                {block.masked ? t('meeting.busy') : (block.title ?? t('meeting.schedule'))}
                              </div>
                              {block.location && !block.masked ? (
                                <div className="truncate text-[11px] text-app-ink/55">
                                  {block.location}
                                </div>
                              ) : null}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </Dialog>
  );
}
