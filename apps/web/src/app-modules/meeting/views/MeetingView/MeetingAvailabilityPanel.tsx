import { useMemo, useState } from 'react';
import { CalendarDays, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { MeetingUser } from '../../api/meeting-api';

import { MeetingAvailabilityModal } from './MeetingAvailabilityModal';
import {
  buildAvailabilityConflicts,
  formatAvailabilityBlockLabel,
  projectMeetingAvailabilityPanelQuery,
  selectMeetingAvailabilityPanelDisplayState,
  useMeetingAvailabilityQuery,
} from './meetingAvailability';
import {
  DEFAULT_TIME_ZONE,
  normalizeTimeZone,
} from '@/src/platform/time/time-utils';

interface MeetingAvailabilityPanelProps {
  workspaceSlug: string;
  attendeeUsers: MeetingUser[];
  meetingStart: Date | null;
  meetingEnd: Date | null;
  timeZone?: string | null;
}

export function MeetingAvailabilityPanel({
  workspaceSlug,
  attendeeUsers,
  meetingStart,
  meetingEnd,
  timeZone,
}: MeetingAvailabilityPanelProps) {
  const { t, i18n } = useTranslation('apps');
  const [modalOpen, setModalOpen] = useState(false);
  const resolvedTimeZone = normalizeTimeZone(timeZone ?? DEFAULT_TIME_ZONE);
  const panelQuery = useMemo(
    () =>
      projectMeetingAvailabilityPanelQuery({
        attendeeUsers,
        meetingEnd,
        meetingStart,
      }),
    [attendeeUsers, meetingEnd, meetingStart],
  );
  const { items, loading, error } = useMeetingAvailabilityQuery({
    workspaceSlug,
    userIds: panelQuery.attendeeIds,
    rangeStart: panelQuery.rangeStart,
    rangeEnd: panelQuery.rangeEnd,
    enabled: panelQuery.canQuery,
  });

  const conflicts = useMemo(() => {
    if (!panelQuery.validMeetingWindow || !meetingStart || !meetingEnd) {
      return [];
    }
    return buildAvailabilityConflicts(
      items,
      meetingStart,
      meetingEnd,
      resolvedTimeZone,
      i18n.language,
      { busy: t('meeting.busy'), schedule: t('meeting.schedule') },
    );
  }, [
    i18n.language,
    items,
    meetingEnd,
    meetingStart,
    panelQuery.validMeetingWindow,
    resolvedTimeZone,
    t,
  ]);

  const displayState = selectMeetingAvailabilityPanelDisplayState({
    attendeeCount: panelQuery.attendeeIds.length,
    conflictCount: conflicts.length,
    error,
    loading,
    validMeetingWindow: panelQuery.validMeetingWindow,
  });

  return (
    <>
      <div className="space-y-2 rounded-md border border-app-border bg-app-surface px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="app-text-control-sm text-app-ink/70">
              {t('meeting.attendeeSchedule')}
            </p>
            <p className="app-text-caption text-app-ink/45">
              {t('meeting.attendeeScheduleDescription')}
            </p>
          </div>
          <button
            type="button"
            onClick={() => setModalOpen(true)}
            disabled={!panelQuery.canQuery}
            className="app-text-control-sm inline-flex items-center gap-1.5 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-1.5 text-app-ink transition-colors hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-45"
          >
            <CalendarDays size={14} />
            <span>{t('meeting.scheduleView')}</span>
          </button>
        </div>

        {displayState.type === 'invalid-window' ? (
          <p className="app-text-caption text-app-ink/50">
            {t('meeting.availabilityInvalidWindow')}
          </p>
        ) : displayState.type === 'no-attendees' ? (
          <p className="app-text-caption text-app-ink/50">
            {t('meeting.availabilityNoAttendees')}
          </p>
        ) : displayState.type === 'loading' ? (
          <div className="flex items-center gap-2 text-app-ink/50">
            <Loader2 size={14} className="animate-spin" />
            <span className="app-text-caption">
              {t('meeting.availabilityChecking')}
            </span>
          </div>
        ) : displayState.type === 'error' ? (
          <p className="app-text-caption text-[var(--ui-color-warning)]">
            {displayState.message}
          </p>
        ) : displayState.type === 'no-conflicts' ? (
          <p className="app-text-caption text-app-success-text">
            {t('meeting.availabilityNoConflicts')}
          </p>
        ) : (
          <div className="space-y-2">
            <p className="app-text-caption text-[var(--ui-color-warning)]">
              {t('meeting.availabilityConflict', { count: conflicts.length })}
            </p>
            <div className="space-y-1">
              {conflicts.map((item) => (
                <div
                  key={`${item.userId}-${item.block.id}`}
                  className="app-text-caption flex items-center justify-between gap-3 rounded-md border border-[var(--ui-color-warning)]/20 bg-[var(--ui-color-warning)]/10 px-3 py-2 text-app-ink"
                >
                  <span className="font-medium">{item.fullName}</span>
                  <span className="truncate text-app-ink/60">
                    {formatAvailabilityBlockLabel(
                      item.block,
                      resolvedTimeZone,
                      i18n.language,
                      {
                        busy: t('meeting.busy'),
                        schedule: t('meeting.schedule'),
                      },
                    )}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <MeetingAvailabilityModal
        key={`${modalOpen ? 'open' : 'closed'}-${meetingStart?.getTime() ?? 'none'}`}
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        workspaceSlug={workspaceSlug}
        attendeeUsers={attendeeUsers}
        meetingStart={meetingStart}
        meetingEnd={meetingEnd}
        timeZone={resolvedTimeZone}
      />
    </>
  );
}
