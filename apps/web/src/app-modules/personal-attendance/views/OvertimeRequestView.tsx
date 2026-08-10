import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, CalendarClock, CheckCircle2, Timer, TriangleAlert } from 'lucide-react';

import { useConfirm } from '@open-alm/ui';

import { useAuth } from '@/src/platform/auth/auth-provider';

import {
  OVERTIME_POLICY,
  calcOvertimeMinutes,
  createOvertimeRequests,
  deleteOvertimeRequest,
  fetchApprovalLine,
  fetchOvertimeRequests,
  type ApprovalLine,
  type OvertimeRequest,
} from '../api/personal-attendance-api';
import { ApproverField } from '../components/ApproverField';
import { DateField } from '../components/DateField';
import { TimeField } from '../components/TimeField';
import {
  REQUEST_STATUS_META,
  datesInRange,
  elapsedMinutes,
  isLiveRequest,
  isWeekend,
  todayYmd,
  weekStartKey,
} from '../lib/attendance-format';
import { useAttendanceLabels } from '../lib/attendance-labels';

const P = OVERTIME_POLICY;

/** 신청 폼 초기값 — 오늘 하루, 정규 종료 ~ +3시간 */
function defaultForm() {
  const today = todayYmd();
  return {
    startDate: today,
    endDate: today,
    startTime: P.regularEnd,
    endTime: '20:00',
    hasDinner: true,
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

export function OvertimeRequestView() {
  const { t } = useTranslation(['apps', 'common', 'shell']);
  const labels = useAttendanceLabels();
  const { token } = useAuth();
  const { confirm, confirmDialog } = useConfirm();
  const [requests, setRequests] = useState<OvertimeRequest[] | null>(null);
  const [line, setLine] = useState<ApprovalLine | null>(null);
  const [form, setForm] = useState(defaultForm);
  const [submitting, setSubmitting] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const reasonRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    let alive = true;
    Promise.all([fetchOvertimeRequests(token), fetchApprovalLine(token)])
      .then(([reqs, approvalLine]) => {
        if (!alive) return;
        setRequests(reqs);
        setLine(approvalLine);
      })
      .catch(() => alive && setLoadError(t('apps:personalAttendance.overtime.loadFailed')));
    return () => {
      alive = false;
    };
  }, [t, token]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 3000);
    return () => clearTimeout(t);
  }, [toast]);

  // 사유는 기본 높이를 유지하다가 길게 쓸 때만 늘어난다
  useLayoutEffect(() => {
    const el = reasonRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.max(72, el.scrollHeight)}px`;
  }, [form.reason]);

  // 하루치 인정 시간 (정책 적용)
  const rawMinutes = elapsedMinutes(form.startTime, form.endTime);
  const perDayMinutes = calcOvertimeMinutes(form.startTime, form.endTime, form.hasDinner);
  const beforeRegularEnd = form.startTime < P.regularEnd;

  const invalidRange = !!form.startDate && !!form.endDate && form.endDate < form.startDate;
  const dates = useMemo(
    () => datesInRange(form.startDate, form.endDate),
    [form.startDate, form.endDate],
  );
  const totalMinutes = perDayMinutes * dates.length;
  const weekendDates = dates.filter(isWeekend);

  const live = useMemo(
    () => (requests ?? []).filter((r) => isLiveRequest(r.status)),
    [requests],
  );

  /**
   * 신청 내역 정렬: 근무일 내림차순 → 같은 날짜는 신청 시각 내림차순(최신이 맨 위).
   * 반려 후 재신청한 날짜는 마지막 시도가 위에 오므로 승인 건이 먼저 보이고, 아래로 반려 이력이 쌓인다.
   * 차수는 시간 순서(가장 이른 신청 = 1차)로 매겨 표시만 역순이 된다.
   */
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
      const idx = seen.get(r.workDate) ?? 0; // 0 = 그 날짜의 최신 건
      seen.set(r.workDate, idx + 1);
      const attempts = totalByDate.get(r.workDate) ?? 1;
      return { r, attempt: attempts - idx, attempts };
    });
  }, [requests]);
  const dupDates = dates.filter((d) => live.some((r) => r.workDate === d));

  // 신청 기간이 걸친 각 주의 연장근로 누적 — 법정 한도 체크
  const weeks = useMemo(() => {
    const add = new Map<string, number>();
    for (const d of dates) add.set(weekStartKey(d), (add.get(weekStartKey(d)) ?? 0) + perDayMinutes);
    return [...add.entries()].map(([wk, addMin]) => {
      const used = live
        .filter((r) => weekStartKey(r.workDate) === wk)
        .reduce((s, r) => s + r.minutes, 0);
      return { wk, used, after: used + addMin };
    });
  }, [dates, perDayMinutes, live]);
  const worstWeek = weeks.reduce<{ used: number; after: number }>(
    (acc, w) => (w.after > acc.after ? w : acc),
    { used: 0, after: 0 },
  );
  const overWeeklyLimit = weeks.some((w) => w.after > P.weeklyLimitMinutes);

  const monthPrefix = todayYmd().slice(0, 7);
  const monthApproved = (requests ?? [])
    .filter((r) => r.status === 'APPROVED' && r.workDate.startsWith(monthPrefix))
    .reduce((s, r) => s + r.minutes, 0);
  const pendingCount = (requests ?? []).filter((r) => r.status === 'PENDING').length;

  const B = 'apps:personalAttendance.overtime.block';
  const blockReason = !form.startDate || !form.endDate
    ? t(`${B}.pickDates`)
    : invalidRange
      ? t(`${B}.endBeforeStart`)
      : dupDates.length > 0
        ? t(`${B}.duplicate`)
        : rawMinutes === 0
          ? t(`${B}.sameTime`)
          : perDayMinutes < P.minMinutes
            ? t(`${B}.belowMinimum`, { minimum: labels.work(P.minMinutes) })
            : form.reason.trim().length < 5
              ? t('apps:personalAttendance.block.reasonTooShort', { count: 5 })
              : !line
                ? t('apps:personalAttendance.block.loadingApprovalLine')
                : overWeeklyLimit
                  ? t(`${B}.weeklyLimit`, { limit: labels.work(P.weeklyLimitMinutes) })
                  : null;

  const submit = async () => {
    if (blockReason || submitting) return;
    setSubmitting(true);
    try {
      const created = await createOvertimeRequests(token, {
        workDates: dates,
        startTime: form.startTime,
        endTime: form.endTime,
        hasDinner: form.hasDinner,
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
        t('apps:personalAttendance.overtime.toast.created', {
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

  // 결재 전이라 이력을 남길 이유가 없다 → 상태 표시 없이 삭제
  const remove = async (r: OvertimeRequest) => {
    const ok = await confirm({
      title: t('apps:personalAttendance.overtime.delete.title'),
      description: t('apps:personalAttendance.overtime.delete.description', {
        date: labels.date(r.workDate),
      }),
      confirmLabel: t('common:actions.delete'),
      cancelLabel: t('common:actions.cancel'),
    });
    if (!ok) return;
    await deleteOvertimeRequest(token, r.id);
    setRequests((prev) => (prev ?? []).filter((x) => x.id !== r.id));
    setToast(t('apps:personalAttendance.toast.deleted'));
  };

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
          <Timer className="size-5" />
        </span>
        <div>
          <h1 className="text-lg font-semibold text-app-ink">
            {t('shell:nav.personal-attendance-overtime')}
          </h1>
          <p className="text-xs text-app-ink-muted">
            {t('apps:personalAttendance.overtime.subtitle', { regularEnd: P.regularEnd })}
          </p>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <SummaryCard
          icon={<CalendarClock className="size-3.5" />}
          label={t('apps:personalAttendance.overtime.summary.monthApproved')}
          value={labels.work(monthApproved)}
        />
        <SummaryCard
          icon={<Timer className="size-3.5" />}
          label={t('apps:personalAttendance.overtime.summary.weekTotal')}
          value={labels.work(worstWeek.used)}
          sub={
            totalMinutes > 0
              ? t('apps:personalAttendance.overtime.summary.afterRequest', {
                  value: labels.work(worstWeek.after),
                })
              : undefined
          }
          tone={overWeeklyLimit ? 'warn' : 'default'}
        />
        <SummaryCard
          icon={<CheckCircle2 className="size-3.5" />}
          label={t('apps:personalAttendance.summary.pending')}
          value={t('apps:personalAttendance.requestCount', { count: pendingCount })}
        />
      </div>

      {/* 한 화면 기준 배치 — 폼은 내용만큼, 내역은 남는 높이 안에서 스크롤 */}
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
                id="ot-start-date"
                label={t('apps:personalAttendance.form.workDate')}
                value={form.startDate}
                onChange={(v) =>
                  setForm((f) => ({ ...f, startDate: v, endDate: f.endDate < v ? v : f.endDate }))
                }
              />
              <DateField
                id="ot-end-date"
                label={t('apps:personalAttendance.form.endDate')}
                value={form.endDate}
                min={form.startDate}
                onChange={(v) => setForm((f) => ({ ...f, endDate: v }))}
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <TimeField
                id="ot-start"
                label={t('apps:personalAttendance.form.startTime')}
                value={form.startTime}
                onChange={(v) => setForm((f) => ({ ...f, startTime: v }))}
              />
              <TimeField
                id="ot-end"
                label={t('apps:personalAttendance.form.endTimePlanned')}
                value={form.endTime}
                onChange={(v) => setForm((f) => ({ ...f, endTime: v }))}
              />
            </div>

            {/* 저녁 식사 — 인정 시간 계산 기준 */}
            <div>
              <span className="mb-1 block text-xs font-medium text-app-ink-muted">
                {t('apps:personalAttendance.overtime.form.dinner')}
              </span>
              <div className="grid grid-cols-2 gap-2">
                {[
                  // 식사함 → 휴게 시간을 근무시간에서 공제. 공제 결과는 아래 인정 시간 줄이 보여준다.
                  { v: false, label: t('apps:personalAttendance.overtime.form.dinnerNo') },
                  { v: true, label: t('apps:personalAttendance.overtime.form.dinnerYes') },
                ].map((o) => {
                  const on = form.hasDinner === o.v;
                  return (
                    <button
                      key={o.label}
                      type="button"
                      aria-pressed={on}
                      onClick={() => setForm((f) => ({ ...f, hasDinner: o.v }))}
                      className={`rounded-lg border px-3 py-1.5 text-center transition ${
                        on
                          ? 'border-app-accent bg-app-accent-weak'
                          : 'border-app-border bg-app-bg hover:bg-app-surface-hover'
                      }`}
                    >
                      <span className={`block text-sm font-semibold ${on ? 'text-app-accent' : 'text-app-ink'}`}>
                        {o.label}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-app-ink-muted" htmlFor="ot-reason">
                {t('apps:personalAttendance.form.reason')}
              </label>
              <textarea
                ref={reasonRef}
                id="ot-reason"
                rows={2}
                value={form.reason}
                onChange={(e) => setForm((f) => ({ ...f, reason: e.target.value }))}
                placeholder={t('apps:personalAttendance.overtime.form.reasonPlaceholder')}
                className="w-full resize-none overflow-hidden rounded-lg border border-app-border bg-app-bg px-3 py-2 text-sm text-app-ink outline-none transition focus:ring-2 focus:ring-app-accent/40"
              />
            </div>

            <ApproverField line={line} />

            {/* 경고는 해당될 때만 자리를 차지한다 */}
            {beforeRegularEnd ? (
              <p className="text-[11px] text-amber-600 dark:text-amber-400">
                {t('apps:personalAttendance.overtime.warn.beforeRegularEnd', {
                  regularEnd: P.regularEnd,
                })}
              </p>
            ) : null}
            {weekendDates.length > 0 ? (
              <p className="text-[11px] text-amber-600 dark:text-amber-400">
                {t('apps:personalAttendance.overtime.warn.weekend', { count: weekendDates.length })}
              </p>
            ) : null}
            {overWeeklyLimit ? (
              <div className="flex items-start gap-2 rounded-lg bg-amber-500/10 p-2 text-[11px] text-amber-700 dark:text-amber-400">
                <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
                <span>
                  {t('apps:personalAttendance.overtime.warn.weeklyLimit', {
                    after: labels.work(worstWeek.after),
                    limit: labels.work(P.weeklyLimitMinutes),
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
                  ? t('apps:personalAttendance.overtime.submitMulti', {
                      days: dates.length,
                      total: labels.work(totalMinutes),
                    })
                  : t('apps:personalAttendance.overtime.submitSingle', {
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
                // 반려 = 효력 없는 건 → 아주 옅은 회색으로 깔아 죽은 항목임을 표시
                const voided = r.status === 'REJECTED';
                return (
                  <li
                    key={r.id}
                    className={`px-4 py-2.5 ${voided ? 'bg-slate-500/[0.055] dark:bg-slate-500/[0.12]' : ''}`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-app-ink">{labels.date(r.workDate)}</span>
                        {attempts > 1 ? (
                          <span className="rounded bg-app-ink/10 px-1.5 text-[10px] font-semibold text-app-ink-muted">
                            {t('apps:personalAttendance.history.attempt', { count: attempt })}
                          </span>
                        ) : null}
                        <span className="text-xs tabular-nums text-app-ink-muted">
                          {labels.clock(r.startTime)} ~ {labels.clock(r.endTime)}
                        </span>
                        <span className="text-xs font-semibold tabular-nums text-app-accent">{labels.work(r.minutes)}</span>
                      </div>
                      <div className="flex items-center gap-2">
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
                        t('apps:personalAttendance.history.approver', {
                          name: r.approverName,
                          role:
                            r.approverRole === 'ACTING_DEPT_HEAD'
                              ? t('apps:personalAttendance.approver.actingShort')
                              : '',
                        }),
                        t('apps:personalAttendance.overtime.history.dinner', {
                          value: r.hasDinner
                            ? t('apps:personalAttendance.overtime.form.dinnerYes')
                            : t('apps:personalAttendance.overtime.form.dinnerNo'),
                        }),
                        r.hrCheckedAt ? t('apps:personalAttendance.history.hrChecked') : null,
                      ]
                        .filter(Boolean)
                        .join(' · ')}
                    </p>
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
