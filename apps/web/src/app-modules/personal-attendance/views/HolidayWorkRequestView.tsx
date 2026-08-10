import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, CalendarClock, CheckCircle2, TriangleAlert, Users } from 'lucide-react';

import { useConfirm } from '@open-alm/ui';

import { useAuth } from '@/src/platform/auth/auth-provider';

import {
  HOLIDAY_WORK_POLICY,
  calcCompLeaveDays,
  calcHolidayPremiumMinutes,
  calcHolidayWorkMinutes,
  createHolidayWorkRequests,
  deleteHolidayWorkRequest,
  fetchApprovalLine,
  fetchHolidayWorkRequests,
  fetchOvertimeRequests,
  type ApprovalLine,
  type HolidayWorkCompensation,
  type HolidayWorkRequest,
  type OvertimeRequest,
} from '../api/personal-attendance-api';
import { ApproverField } from '../components/ApproverField';
import { DateField } from '../components/DateField';
import { TimeField } from '../components/TimeField';
import {
  HOLIDAY_WORK_STAGES,
  REQUEST_STATUS_META,
  datesInRange,
  holidayWorkStageIndex,
  isLiveRequest,
  isWeekend,
  todayYmd,
  weekStartKey,
} from '../lib/attendance-format';
import { useAttendanceLabels } from '../lib/attendance-labels';

const P = HOLIDAY_WORK_POLICY;

const BREAK_OPTIONS = [0, 30, 60, 90];

const COMPENSATIONS: HolidayWorkCompensation[] = ['ALLOWANCE', 'COMP_LEAVE'];

function defaultForm() {
  const today = todayYmd();
  return {
    startDate: today,
    endDate: today,
    startTime: '08:00',
    endTime: '17:00',
    breakMinutes: 60,
    compensation: 'ALLOWANCE' as HolidayWorkCompensation,
    reason: '',
  };
}

function SummaryCard({
  icon,
  label,
  value,
  sub,
  tone = 'default',
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub?: string;
  tone?: 'default' | 'warn';
}) {
  return (
    <div className="rounded-xl border border-app-border bg-app-surface px-4 py-3">
      <div className="flex items-center gap-2 text-xs font-medium text-app-ink-muted">
        {icon}
        {label}
      </div>
      <div
        className={`mt-1 text-xl font-bold tabular-nums ${
          tone === 'warn' ? 'text-amber-600 dark:text-amber-400' : 'text-app-accent'
        }`}
      >
        {value}
      </div>
      {sub ? <div className="mt-0.5 text-xs text-app-ink-muted">{sub}</div> : null}
    </div>
  );
}

/**
 * 특근 결재 단계 진행 표시.
 * 그룹웨어 결재선은 부서마다 달라 앱이 결재자를 그리지 않고 단계만 보여준다.
 */
function StageTrail({ status }: { status: HolidayWorkRequest['status'] }) {
  const labels = useAttendanceLabels();
  const current = holidayWorkStageIndex(status);
  if (current < 0) return null;
  return (
    <div className="mt-1 flex items-center gap-1">
      {HOLIDAY_WORK_STAGES.map((s, i) => {
        const done = i < current;
        const active = i === current;
        return (
          <span key={s} className="flex items-center gap-1">
            {i > 0 ? <span className="text-[9px] text-app-ink-muted">›</span> : null}
            <span
              className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                active
                  ? 'bg-app-accent text-app-accent-fg'
                  : done
                    ? 'bg-emerald-500/12 text-emerald-600 dark:text-emerald-400'
                    : 'bg-app-surface-subtle text-app-ink-muted'
              }`}
            >
              {done ? '✓ ' : ''}
              {labels.stage(s)}
            </span>
          </span>
        );
      })}
    </div>
  );
}

export function HolidayWorkRequestView() {
  const { t } = useTranslation(['apps', 'common', 'shell']);
  const labels = useAttendanceLabels();
  const { token } = useAuth();
  const { confirm, confirmDialog } = useConfirm();
  const [requests, setRequests] = useState<HolidayWorkRequest[] | null>(null);
  const [overtime, setOvertime] = useState<OvertimeRequest[]>([]);
  const [line, setLine] = useState<ApprovalLine | null>(null);
  const [form, setForm] = useState(defaultForm);
  const [submitting, setSubmitting] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const reasonRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    let alive = true;
    Promise.all([
      fetchHolidayWorkRequests(token),
      fetchApprovalLine(token),
      fetchOvertimeRequests(token),
    ])
      .then(([reqs, approvalLine, ot]) => {
        if (!alive) return;
        setRequests(reqs);
        setLine(approvalLine);
        setOvertime(ot);
      })
      .catch(() => alive && setLoadError(t('apps:personalAttendance.holidayWork.loadFailed')));
    return () => {
      alive = false;
    };
  }, [t, token]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 3000);
    return () => clearTimeout(t);
  }, [toast]);

  useLayoutEffect(() => {
    const el = reasonRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.max(64, el.scrollHeight)}px`;
  }, [form.reason]);

  // 하루치 산정 — 실근로 → 가산 환산 → 대체휴가 일수
  const perDayMinutes = calcHolidayWorkMinutes(form.startTime, form.endTime, form.breakMinutes);
  const perDayPremium = calcHolidayPremiumMinutes(perDayMinutes);
  const crossesMidnight = form.endTime <= form.startTime;

  const invalidRange = !!form.startDate && !!form.endDate && form.endDate < form.startDate;
  const dates = useMemo(
    () => datesInRange(form.startDate, form.endDate),
    [form.startDate, form.endDate],
  );
  const totalMinutes = perDayMinutes * dates.length;
  const totalPremium = perDayPremium * dates.length;
  const totalCompLeave = calcCompLeaveDays(totalPremium);
  // 특근은 휴일 근무다. 평일이 섞이면 야근·정상근무 대상일 수 있어 알려준다.
  const weekdayDates = dates.filter((d) => !isWeekend(d));

  const live = useMemo(
    () => (requests ?? []).filter((r) => isLiveRequest(r.status)),
    [requests],
  );
  const dupDates = dates.filter((d) => live.some((r) => r.workDate === d));

  /**
   * 주 합계는 야근(연장근로) + 특근(휴일근로) 실근로시간을 함께 본다.
   * ⚠ 휴일근로가 주 12시간 연장근로 한도에 포함되는지는 해석·사규 확인이 필요해
   *   차단하지 않고 참고 경고만 띄운다.
   */
  const liveOvertime = useMemo(
    () => overtime.filter((r) => isLiveRequest(r.status)),
    [overtime],
  );
  const weeks = useMemo(() => {
    const add = new Map<string, number>();
    for (const d of dates) add.set(weekStartKey(d), (add.get(weekStartKey(d)) ?? 0) + perDayMinutes);
    return [...add.entries()].map(([wk, addMin]) => {
      const used =
        live.filter((r) => weekStartKey(r.workDate) === wk).reduce((s, r) => s + r.minutes, 0) +
        liveOvertime.filter((r) => weekStartKey(r.workDate) === wk).reduce((s, r) => s + r.minutes, 0);
      return { wk, used, after: used + addMin };
    });
  }, [dates, perDayMinutes, live, liveOvertime]);
  const worstWeek = weeks.reduce<{ used: number; after: number }>(
    (acc, w) => (w.after > acc.after ? w : acc),
    { used: 0, after: 0 },
  );
  const overWeeklyReference = weeks.some((w) => w.after > P.weeklyReferenceMinutes);

  const monthPrefix = todayYmd().slice(0, 7);
  const monthApproved = (requests ?? [])
    .filter((r) => r.status === 'APPROVED' && r.workDate.startsWith(monthPrefix))
    .reduce((s, r) => s + r.minutes, 0);
  const pendingCount = (requests ?? []).filter((r) => r.status === 'PENDING').length;
  // 부서장 승인 후 근태담당자·그룹웨어 단계에 걸려 있는 건
  const inProgressCount = (requests ?? []).filter(
    (r) => r.status === 'TIMEKEEPER_REVIEW' || r.status === 'GROUPWARE_APPROVAL',
  ).length;

  const B = 'apps:personalAttendance.holidayWork.block';
  const blockReason = !form.startDate || !form.endDate
    ? t(`${B}.pickDates`)
    : invalidRange
      ? t(`${B}.endBeforeStart`)
      : dupDates.length > 0
        ? t('apps:personalAttendance.overtime.block.duplicate')
        : perDayMinutes === 0
          ? t(`${B}.noWorkAfterBreak`)
          : perDayMinutes < P.minMinutes
            ? t('apps:personalAttendance.overtime.block.belowMinimum', {
                minimum: labels.work(P.minMinutes),
              })
            : form.reason.trim().length < 5
              ? t('apps:personalAttendance.block.reasonTooShort', { count: 5 })
              : !line
                ? t('apps:personalAttendance.block.loadingApprovalLine')
                : null;

  const submit = async () => {
    if (blockReason || submitting) return;
    setSubmitting(true);
    try {
      const created = await createHolidayWorkRequests(token, {
        workDates: dates,
        startTime: form.startTime,
        endTime: form.endTime,
        breakMinutes: form.breakMinutes,
        compensation: form.compensation,
        reason: form.reason.trim(),
      });
      setRequests((prev) => [...created, ...(prev ?? [])]);
      setForm(defaultForm());
      const span =
        created.length > 1
          ? t('apps:personalAttendance.spanMultiDay', {
              date: labels.date(created[created.length - 1].workDate),
              count: created.length - 1,
            })
          : labels.date(created[0].workDate);
      setToast(
        t('apps:personalAttendance.holidayWork.toast.created', {
          span,
          total: labels.work(totalMinutes),
          approver: created[0].approverName,
        }),
      );
    } catch {
      setToast(t('apps:personalAttendance.toast.createFailed'));
    } finally {
      setSubmitting(false);
    }
  };

  const remove = async (r: HolidayWorkRequest) => {
    const ok = await confirm({
      title: t('apps:personalAttendance.holidayWork.delete.title'),
      description: t('apps:personalAttendance.holidayWork.delete.description', {
        date: labels.date(r.workDate),
      }),
      confirmLabel: t('common:actions.delete'),
      cancelLabel: t('common:actions.cancel'),
    });
    if (!ok) return;
    await deleteHolidayWorkRequest(token, r.id);
    setRequests((prev) => (prev ?? []).filter((x) => x.id !== r.id));
    setToast(t('apps:personalAttendance.toast.deleted'));
  };

  /** 근무일 내림차순 → 같은 날짜는 신청 시각 내림차순(최신이 맨 위). 차수는 시간순. */
  const rows = useMemo(() => {
    const sorted = [...(requests ?? [])].sort((a, b) =>
      a.workDate !== b.workDate
        ? b.workDate.localeCompare(a.workDate)
        : b.requestedAt.localeCompare(a.requestedAt),
    );
    const totalByDate = new Map<string, number>();
    for (const r of sorted) totalByDate.set(r.workDate, (totalByDate.get(r.workDate) ?? 0) + 1);
    const seen = new Map<string, number>();
    return sorted.map((r) => {
      const idx = seen.get(r.workDate) ?? 0;
      seen.set(r.workDate, idx + 1);
      const attempts = totalByDate.get(r.workDate) ?? 1;
      return { r, attempt: attempts - idx, attempts };
    });
  }, [requests]);

  if (loadError) {
    return (
      <div style={{ paddingInline: '4%' }} className="w-full py-6">
        <p className="text-sm text-rose-600">{loadError}</p>
      </div>
    );
  }

  return (
    <div style={{ paddingInline: '4%' }} className="flex w-full flex-col gap-3 py-4">
      <header className="flex items-center gap-3">
        <span className="flex size-10 items-center justify-center rounded-xl bg-app-accent-weak text-app-accent">
          <Users className="size-5" />
        </span>
        <div>
          <h1 className="text-lg font-semibold text-app-ink">
            {t('shell:nav.personal-attendance-holiday')}
          </h1>
          <p className="text-xs text-app-ink-muted">
            {t('apps:personalAttendance.holidayWork.subtitle', {
              within8h: P.premiumWithin8hPercent,
              over8h: P.premiumOver8hPercent,
            })}
          </p>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <SummaryCard
          icon={<CalendarClock className="size-3.5" />}
          label={t('apps:personalAttendance.holidayWork.summary.monthApproved')}
          value={labels.work(monthApproved)}
        />
        <SummaryCard
          icon={<Users className="size-3.5" />}
          label={t('apps:personalAttendance.holidayWork.summary.weekTotal')}
          value={labels.work(worstWeek.used)}
          sub={
            totalMinutes > 0
              ? t('apps:personalAttendance.overtime.summary.afterRequest', {
                  value: labels.work(worstWeek.after),
                })
              : undefined
          }
          tone={overWeeklyReference ? 'warn' : 'default'}
        />
        <SummaryCard
          icon={<CheckCircle2 className="size-3.5" />}
          label={t('apps:personalAttendance.holidayWork.summary.pending')}
          value={t('apps:personalAttendance.requestCount', { count: pendingCount })}
          sub={
            inProgressCount > 0
              ? t('apps:personalAttendance.holidayWork.summary.inProgress', {
                  count: inProgressCount,
                })
              : undefined
          }
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 lg:items-start">
        {/* 좌: 신청 폼 */}
        <div className="rounded-xl border border-app-border bg-app-surface">
          <div className="rounded-t-xl border-b border-app-border bg-app-accent-weak px-4 py-2">
            <h2 className="text-sm font-semibold text-app-accent">
              {t('apps:personalAttendance.form.title')}
            </h2>
          </div>
          <div className="space-y-2.5 p-4">
            <div className="grid grid-cols-2 gap-3">
              <DateField
                id="hw-start-date"
                label={t('apps:personalAttendance.holidayWork.form.workDate')}
                value={form.startDate}
                onChange={(v) =>
                  setForm((f) => ({ ...f, startDate: v, endDate: f.endDate < v ? v : f.endDate }))
                }
              />
              <DateField
                id="hw-end-date"
                label={t('apps:personalAttendance.form.endDate')}
                value={form.endDate}
                min={form.startDate}
                onChange={(v) => setForm((f) => ({ ...f, endDate: v }))}
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <TimeField
                id="hw-start"
                label={t('apps:personalAttendance.form.startTime')}
                value={form.startTime}
                onChange={(v) => setForm((f) => ({ ...f, startTime: v }))}
              />
              <TimeField
                id="hw-end"
                label={t('apps:personalAttendance.form.endTimePlanned')}
                value={form.endTime}
                onChange={(v) => setForm((f) => ({ ...f, endTime: v }))}
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-xs font-medium text-app-ink-muted" htmlFor="hw-break">
                  {t('apps:personalAttendance.holidayWork.form.breakTime')}
                </label>
                <select
                  id="hw-break"
                  value={form.breakMinutes}
                  onChange={(e) => setForm((f) => ({ ...f, breakMinutes: Number(e.target.value) }))}
                  className="w-full rounded-lg border border-app-border bg-app-bg px-3 py-2 text-sm tabular-nums text-app-ink outline-none transition focus:ring-2 focus:ring-app-accent/40"
                >
                  {BREAK_OPTIONS.map((m) => (
                    <option key={m} value={m}>
                      {m === 0 ? t('apps:personalAttendance.holidayWork.form.breakNone') : labels.work(m)}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <span className="mb-1 block text-xs font-medium text-app-ink-muted">
                  {t('apps:personalAttendance.holidayWork.form.compensation')}
                </span>
                <div className="grid grid-cols-2 gap-2">
                  {COMPENSATIONS.map((c) => {
                    const on = form.compensation === c;
                    return (
                      <button
                        key={c}
                        type="button"
                        aria-pressed={on}
                        onClick={() => setForm((f) => ({ ...f, compensation: c }))}
                        className={`rounded-lg border px-2 py-1.5 text-center transition ${
                          on
                            ? 'border-app-accent bg-app-accent-weak'
                            : 'border-app-border bg-app-bg hover:bg-app-surface-hover'
                        }`}
                      >
                        <span className={`block text-sm font-semibold ${on ? 'text-app-accent' : 'text-app-ink'}`}>
                          {t(`apps:personalAttendance.holidayWork.compensation.${c}.label`)}
                        </span>
                        <span className="block text-[10px] text-app-ink-muted">
                          {t(`apps:personalAttendance.holidayWork.compensation.${c}.desc`)}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* 산정 결과 — 실근로와 가산 환산을 함께 보여준다 */}
            <div className="rounded-lg border border-app-border bg-app-surface-subtle px-3 py-2">
              <div className="flex items-baseline justify-between">
                <span className="text-xs font-medium text-app-ink-muted">
                  {dates.length > 1
                    ? t('apps:personalAttendance.holidayWork.calc.actualWorkMultiDay', {
                        count: dates.length,
                      })
                    : t('apps:personalAttendance.holidayWork.calc.actualWork')}
                </span>
                <span className="text-sm font-bold tabular-nums text-app-ink">{labels.work(totalMinutes)}</span>
              </div>
              <div className="mt-0.5 flex items-baseline justify-between">
                <span className="text-xs font-medium text-app-ink-muted">
                  {t('apps:personalAttendance.holidayWork.calc.withPremium')}
                </span>
                <span className="text-sm font-bold tabular-nums text-app-accent">{labels.work(totalPremium)}</span>
              </div>
              {form.compensation === 'COMP_LEAVE' && totalPremium > 0 ? (
                <div className="mt-0.5 flex items-baseline justify-between border-t border-app-border pt-1">
                  <span className="text-xs font-medium text-app-ink-muted">
                    {t('apps:personalAttendance.holidayWork.calc.expectedCompLeave')}
                  </span>
                  <span className="text-sm font-bold tabular-nums text-app-accent">
                    {labels.leaveDays(totalCompLeave)}
                  </span>
                </div>
              ) : null}
              {crossesMidnight ? (
                <p className="mt-1 text-[11px] text-app-ink-muted">
                  {t('apps:personalAttendance.holidayWork.calc.crossesMidnight')}
                </p>
              ) : null}
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-app-ink-muted" htmlFor="hw-reason">
                {t('apps:personalAttendance.form.reason')}
              </label>
              <textarea
                ref={reasonRef}
                id="hw-reason"
                rows={2}
                value={form.reason}
                onChange={(e) => setForm((f) => ({ ...f, reason: e.target.value }))}
                placeholder={t('apps:personalAttendance.holidayWork.form.reasonPlaceholder')}
                className="w-full resize-none overflow-hidden rounded-lg border border-app-border bg-app-bg px-3 py-2 text-sm text-app-ink outline-none transition focus:ring-2 focus:ring-app-accent/40"
              />
            </div>

            <ApproverField line={line} />

            {weekdayDates.length > 0 ? (
              <p className="text-[11px] text-amber-600 dark:text-amber-400">
                {t('apps:personalAttendance.holidayWork.warn.weekday', {
                  count: weekdayDates.length,
                })}
              </p>
            ) : null}
            {overWeeklyReference ? (
              <div className="flex items-start gap-2 rounded-lg bg-amber-500/10 p-2 text-[11px] text-amber-700 dark:text-amber-400">
                <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
                <span>
                  {t('apps:personalAttendance.holidayWork.warn.weeklyReference', {
                    after: labels.work(worstWeek.after),
                    limit: labels.work(P.weeklyReferenceMinutes),
                  })}
                </span>
              </div>
            ) : null}
            {dupDates.length > 0 ? (
              <div className="flex items-start gap-2 rounded-lg bg-rose-500/10 p-2 text-[11px] text-rose-600 dark:text-rose-400">
                <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
                <span>
                  {t('apps:personalAttendance.warn.alreadyLive', {
                    dates: dupDates.map(labels.date).join(', '),
                  })}
                </span>
              </div>
            ) : null}
          </div>

          <div className="border-t border-app-border p-3">
            {blockReason ? (
              <p className="mb-1.5 text-center text-[11px] text-app-ink-muted">{blockReason}</p>
            ) : null}
            <button
              type="button"
              onClick={submit}
              disabled={!!blockReason || submitting}
              className="w-full rounded-lg bg-app-accent py-2.5 text-sm font-semibold text-app-accent-fg transition hover:bg-app-accent-hover disabled:cursor-not-allowed disabled:opacity-40"
            >
              {submitting
                ? t('apps:personalAttendance.submitting')
                : dates.length > 1
                  ? t('apps:personalAttendance.holidayWork.submitMulti', {
                      days: dates.length,
                      total: labels.work(totalMinutes),
                    })
                  : t('apps:personalAttendance.holidayWork.submitSingle', {
                      total: labels.work(perDayMinutes),
                    })}
            </button>
          </div>
        </div>

        {/* 우: 신청 내역 */}
        <div className="flex flex-col overflow-hidden rounded-xl border border-app-border bg-app-surface lg:max-h-[calc(100vh-13rem)]">
          <div className="flex items-center justify-between rounded-t-xl border-b border-app-border bg-app-accent-weak px-4 py-2">
            <h2 className="text-sm font-semibold text-app-accent">
              {t('apps:personalAttendance.history.title')}
            </h2>
            <span className="text-xs text-app-accent/70">
              {t('apps:personalAttendance.requestCount', { count: requests?.length ?? 0 })}
            </span>
          </div>
          {requests == null ? (
            <div className="space-y-2 p-4">
              {[0, 1, 2].map((i) => (
                <div key={i} className="h-16 animate-pulse rounded-lg bg-app-surface-subtle" />
              ))}
            </div>
          ) : requests.length === 0 ? (
            <p className="p-6 text-center text-sm text-app-ink-muted">
              {t('apps:personalAttendance.history.empty')}
            </p>
          ) : (
            <ul className="min-h-0 flex-1 divide-y divide-app-border overflow-y-auto">
              {rows.map(({ r, attempt, attempts }) => {
                const voided = r.status === 'REJECTED';
                return (
                  <li
                    key={r.id}
                    className={`px-4 py-2.5 ${voided ? 'bg-slate-500/[0.055] dark:bg-slate-500/[0.12]' : ''}`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-semibold text-app-ink">{labels.date(r.workDate)}</span>
                        {attempts > 1 ? (
                          <span className="rounded bg-app-ink/10 px-1.5 text-[10px] font-semibold text-app-ink-muted">
                            {t('apps:personalAttendance.history.attempt', { count: attempt })}
                          </span>
                        ) : null}
                        <span className="text-xs tabular-nums text-app-ink-muted">
                          {labels.clock(r.startTime)} ~ {labels.clock(r.endTime)}
                        </span>
                        <span className="text-xs font-semibold tabular-nums text-app-accent">
                          {labels.work(r.minutes)}
                        </span>
                        <span className="rounded bg-app-surface-subtle px-1.5 py-0.5 text-[10px] font-semibold text-app-ink-muted">
                          {t(`apps:personalAttendance.holidayWork.compensation.${r.compensation}.label`)}
                        </span>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        <span
                          className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-semibold ${REQUEST_STATUS_META[r.status].badge}`}
                        >
                          {labels.requestStatus(r.status)}
                        </span>
                        {r.status === 'PENDING' ? (
                          <button
                            type="button"
                            onClick={() => remove(r)}
                            className="rounded border border-app-border px-2 py-0.5 text-[11px] text-app-ink-muted transition hover:bg-rose-500/10 hover:text-rose-600 dark:hover:text-rose-400"
                          >
                            {t('common:actions.delete')}
                          </button>
                        ) : null}
                      </div>
                    </div>
                    <p className="mt-0.5 line-clamp-2 text-xs text-app-ink-muted">{r.reason}</p>
                    <p className="mt-0.5 text-[11px] text-app-ink-muted">
                      {[
                        t('apps:personalAttendance.holidayWork.history.premium', {
                          value: labels.work(r.premiumMinutes),
                        }),
                        r.compLeaveDays != null
                          ? t('apps:personalAttendance.holidayWork.history.compLeave', {
                              value: labels.leaveDays(r.compLeaveDays),
                            })
                          : null,
                        r.breakMinutes > 0
                          ? t('apps:personalAttendance.holidayWork.history.break', {
                              value: labels.work(r.breakMinutes),
                            })
                          : null,
                        t('apps:personalAttendance.history.approver', {
                          name: r.approverName,
                          role:
                            r.approverRole === 'ACTING_DEPT_HEAD'
                              ? t('apps:personalAttendance.approver.actingShort')
                              : '',
                        }),
                        r.groupwareDocNo
                          ? t('apps:personalAttendance.holidayWork.history.groupwareDoc', {
                              value: r.groupwareDocNo,
                            })
                          : null,
                      ]
                        .filter(Boolean)
                        .join(' · ')}
                    </p>
                    {/* 결재 단계 — 부서장 → 부서근태 담당자 → 그룹웨어 결재 → 확정 */}
                    {!voided ? <StageTrail status={r.status} /> : null}
                    {r.status === 'REJECTED' && r.rejectReason ? (
                      <p className="mt-1 rounded bg-rose-500/10 px-2 py-1 text-[11px] text-rose-600 dark:text-rose-400">
                        {t('apps:personalAttendance.history.rejectReason', {
                          reason: r.rejectReason,
                        })}
                      </p>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>

      {toast ? (
        <div className="pointer-events-none fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-full bg-app-ink px-4 py-2 text-sm font-medium text-app-bg shadow-lg">
          {toast}
        </div>
      ) : null}
      {confirmDialog}
    </div>
  );
}
