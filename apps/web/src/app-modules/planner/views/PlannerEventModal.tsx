import { useEffect, useMemo, useState } from 'react';
import { Button, Dialog } from '@ai-do/ui';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  createPlannerEvent,
  deletePlannerEvent,
  getPlannerEvent,
  updatePlannerEvent,
  type PlannerEvent,
  type PlannerEventVisibility,
} from '../api/planner-api';

interface PlannerEventModalProps {
  isOpen: boolean;
  onClose: () => void;
  workspaceSlug: string | undefined;
  eventId?: string | null;
  initialRange?: {
    start: Date;
    end: Date;
    allDay: boolean;
  } | null;
  onSaved?: (event: PlannerEvent) => void;
  onDeleted?: (eventId: string) => void;
}

function pad(value: number): string {
  return String(value).padStart(2, '0');
}

function formatDateInputValue(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function formatDateTimeInputValue(date: Date): string {
  return `${formatDateInputValue(date)}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function parseLocalDate(value: string): Date {
  const [year, month, day] = value.split('-').map(Number);
  return new Date(year, month - 1, day);
}

function addLocalDays(date: Date, days: number): Date {
  const next = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  next.setDate(next.getDate() + days);
  return next;
}

function incrementYmd(value: string): string {
  return formatDateInputValue(addLocalDays(parseLocalDate(value), 1));
}

function decrementYmd(value: string): string {
  return formatDateInputValue(addLocalDays(parseLocalDate(value), -1));
}

function defaultTimedRange() {
  const start = new Date();
  start.setMinutes(0, 0, 0);
  start.setHours(start.getHours() + 1);
  const end = new Date(start.getTime());
  end.setHours(end.getHours() + 1);
  return { start, end };
}

function buildDraftFromRange(range?: { start: Date; end: Date; allDay: boolean } | null) {
  if (range?.allDay) {
    return {
      allDay: true,
      startValue: formatDateInputValue(range.start),
      endValue: decrementYmd(formatDateInputValue(range.end)),
    };
  }
  if (range) {
    return {
      allDay: false,
      startValue: formatDateTimeInputValue(range.start),
      endValue: formatDateTimeInputValue(range.end),
    };
  }
  const fallback = defaultTimedRange();
  return {
    allDay: false,
    startValue: formatDateTimeInputValue(fallback.start),
    endValue: formatDateTimeInputValue(fallback.end),
  };
}

function plannerEventToDraft(event: PlannerEvent) {
  if (event.allDay) {
    return {
      allDay: true,
      startValue: event.start,
      endValue: decrementYmd(event.end),
    };
  }
  return {
    allDay: false,
    startValue: formatDateTimeInputValue(new Date(event.start)),
    endValue: formatDateTimeInputValue(new Date(event.end)),
  };
}

export function PlannerEventModal({
  isOpen,
  onClose,
  workspaceSlug,
  eventId,
  initialRange,
  onSaved,
  onDeleted,
}: PlannerEventModalProps) {
  const { t } = useTranslation(['apps', 'common']);
  const { token } = useAuth();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [location, setLocation] = useState('');
  const [visibility, setVisibility] = useState<PlannerEventVisibility>('private');
  const [allDay, setAllDay] = useState(false);
  const [startValue, setStartValue] = useState('');
  const [endValue, setEndValue] = useState('');

  const isEditMode = Boolean(eventId);

  useEffect(() => {
    if (!isOpen) return;
    const draft = buildDraftFromRange(initialRange);
    setTitle('');
    setDescription('');
    setLocation('');
    setVisibility('private');
    setAllDay(draft.allDay);
    setStartValue(draft.startValue);
    setEndValue(draft.endValue);
    setError(null);
    setSaving(false);
    setDeleting(false);

    if (!eventId || !token || !workspaceSlug) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    getPlannerEvent(token, workspaceSlug, eventId)
      .then((event) => {
        if (cancelled) return;
        const eventDraft = plannerEventToDraft(event);
        setTitle(event.title);
        setDescription(event.description);
        setLocation(event.location);
        setVisibility(event.visibility);
        setAllDay(eventDraft.allDay);
        setStartValue(eventDraft.startValue);
        setEndValue(eventDraft.endValue);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setError(err.message ?? t('apps:planner.loadFailed'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [eventId, initialRange, isOpen, t, token, workspaceSlug]);

  const canSave = useMemo(() => {
    if (!title.trim()) return false;
    if (allDay) {
      return Boolean(startValue && endValue && parseLocalDate(endValue) >= parseLocalDate(startValue));
    }
    return Boolean(startValue && endValue && new Date(endValue) > new Date(startValue));
  }, [allDay, endValue, startValue, title]);

  function toggleAllDay(nextAllDay: boolean) {
    if (nextAllDay === allDay) return;
    if (nextAllDay) {
      const nextStart = startValue ? new Date(startValue) : defaultTimedRange().start;
      const nextEnd = endValue ? new Date(endValue) : defaultTimedRange().end;
      setAllDay(true);
      setStartValue(formatDateInputValue(nextStart));
      setEndValue(formatDateInputValue(nextEnd));
      return;
    }
    const startDate = startValue ? parseLocalDate(startValue) : new Date();
    const endDate = endValue ? parseLocalDate(endValue) : addLocalDays(startDate, 1);
    const nextStart = new Date(startDate.getFullYear(), startDate.getMonth(), startDate.getDate(), 9, 0, 0, 0);
    const nextEnd = new Date(endDate.getFullYear(), endDate.getMonth(), endDate.getDate(), 10, 0, 0, 0);
    setAllDay(false);
    setStartValue(formatDateTimeInputValue(nextStart));
    setEndValue(
      formatDateTimeInputValue(
        nextEnd > nextStart ? nextEnd : new Date(nextStart.getTime() + (60 * 60 * 1000)),
      ),
    );
  }

  async function handleSave() {
    if (!token || !workspaceSlug || !canSave) return;
    setSaving(true);
    setError(null);
    const payload = {
      title: title.trim(),
      description: description.trim(),
      location: location.trim(),
      visibility,
      allDay,
      start: allDay ? startValue : new Date(startValue).toISOString(),
      end: allDay ? incrementYmd(endValue) : new Date(endValue).toISOString(),
    };
    try {
      const event = eventId
        ? await updatePlannerEvent(token, workspaceSlug, eventId, payload)
        : await createPlannerEvent(token, workspaceSlug, payload);
      onSaved?.(event);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('apps:planner.saveFailed'));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!token || !workspaceSlug || !eventId) return;
    setDeleting(true);
    setError(null);
    try {
      await deletePlannerEvent(token, workspaceSlug, eventId);
      onDeleted?.(eventId);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('apps:planner.deleteFailed'));
    } finally {
      setDeleting(false);
    }
  }

  return (
    <Dialog
        closeLabel={t('common:actions.close')}
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={isEditMode ? t('apps:planner.editEvent') : t('apps:planner.newEvent')}
      description={t('apps:planner.eventDescription')}
      maxWidth="max-w-xl"
      dismissOnInteractOutside={false}
      actions={
        <div className="flex w-full items-center justify-between gap-3">
          <div>
            {isEditMode ? (
              <Button
                variant="secondary"
                onClick={() => void handleDelete()}
                disabled={deleting || saving}
                className="text-[var(--ui-color-danger)]"
              >
                {deleting ? t('apps:planner.deletePending') : t('common:actions.delete')}
              </Button>
            ) : null}
          </div>
          <div className="flex items-center gap-3">
            <Button variant="secondary" onClick={onClose} disabled={saving || deleting}>
              {t('common:actions.cancel')}
            </Button>
            <Button variant="primary" onClick={() => void handleSave()} disabled={!canSave || saving || loading || deleting}>
              {saving ? t('apps:planner.savePending') : t('common:actions.save')}
            </Button>
          </div>
        </div>
      }
    >
      <div className="space-y-5 text-app-ink">
        {error ? (
          <div
            role="alert"
            className="app-text-body rounded-md border border-[var(--ui-color-warning)]/40 bg-[var(--ui-color-warning)]/10 px-3 py-2 text-[var(--ui-color-warning)]"
          >
            {error}
          </div>
        ) : null}

        {loading ? (
          <div className="rounded-md border border-app-border bg-app-surface px-4 py-6 text-center text-app-ink/50">
            {t('apps:planner.eventLoading')}
          </div>
        ) : (
          <>
            <div className="space-y-1">
              <label className="app-text-control-sm text-app-ink/70">
                {t('apps:planner.title')} <span className="text-[var(--ui-color-danger)]">*</span>
              </label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                maxLength={200}
                autoFocus
                placeholder={t('apps:planner.titlePlaceholder')}
                className="app-text-body w-full rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink placeholder:text-app-ink/30 focus:border-app-accent focus:outline-none"
              />
            </div>

            <div className="flex items-center gap-3">
              <label className="app-text-control-sm text-app-ink/70">{t('apps:planner.allDay')}</label>
              <button
                type="button"
                role="switch"
                aria-checked={allDay}
                onClick={() => toggleAllDay(!allDay)}
                className={`relative h-6 w-11 rounded-full transition-colors ${allDay ? 'bg-app-accent' : 'bg-app-border'}`}
              >
                <span
                  className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${allDay ? 'translate-x-5' : 'translate-x-0.5'}`}
                />
              </button>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <label className="app-text-control-sm text-app-ink/70">{allDay ? t('apps:planner.startDate') : t('apps:planner.start')}</label>
                <input
                  type={allDay ? 'date' : 'datetime-local'}
                  value={startValue}
                  onChange={(e) => setStartValue(e.target.value)}
                  className="app-text-body w-full rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink focus:border-app-accent focus:outline-none"
                />
              </div>
              <div className="space-y-1">
                <label className="app-text-control-sm text-app-ink/70">{allDay ? t('apps:planner.endDate') : t('apps:planner.end')}</label>
                <input
                  type={allDay ? 'date' : 'datetime-local'}
                  value={endValue}
                  onChange={(e) => setEndValue(e.target.value)}
                  className="app-text-body w-full rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink focus:border-app-accent focus:outline-none"
                />
                {allDay ? (
                  <p className="app-text-caption text-app-ink/45">
                    {t('apps:planner.endDateHint')}
                  </p>
                ) : null}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <label className="app-text-control-sm text-app-ink/70">{t('apps:planner.visibility')}</label>
                <select
                  value={visibility}
                  onChange={(e) => setVisibility(e.target.value as PlannerEventVisibility)}
                  className="app-text-body w-full rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink focus:border-app-accent focus:outline-none"
                >
                  <option value="private">{t('ai.search.visibilityPrivate')}</option>
                  <option value="public">{t('ai.search.visibilityPublic')}</option>
                </select>
              </div>
              <div className="space-y-1">
                <label className="app-text-control-sm text-app-ink/70">{t('apps:planner.location')}</label>
                <input
                  type="text"
                  value={location}
                  onChange={(e) => setLocation(e.target.value)}
                  maxLength={240}
                  placeholder={t('apps:planner.locationPlaceholder')}
                  className="app-text-body w-full rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink placeholder:text-app-ink/30 focus:border-app-accent focus:outline-none"
                />
              </div>
            </div>

            <div className="space-y-1">
              <label className="app-text-control-sm text-app-ink/70">{t('apps:planner.description')}</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={4}
                placeholder={t('apps:planner.descriptionPlaceholder')}
                className="app-text-body w-full resize-none rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink placeholder:text-app-ink/30 focus:border-app-accent focus:outline-none"
              />
            </div>
          </>
        )}
      </div>
    </Dialog>
  );
}
