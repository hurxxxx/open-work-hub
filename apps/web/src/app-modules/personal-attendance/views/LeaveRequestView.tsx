import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, CheckCircle2, Info, Paperclip, Plane, TriangleAlert } from 'lucide-react';

import { useConfirm } from '@open-alm/ui';

import { useAuth } from '@/src/platform/auth/auth-provider';

import {
  createAttendanceRequest,
  deleteAttendanceRequest,
  fetchApprovalLine,
  fetchAttendanceRequests,
  fetchPersonalAttendanceSummary,
  type ApprovalLine,
  type AttendanceRequest,
  type HalfDay,
  type RequestAttachment,
  type LeaveStat,
  type LeaveSummary,
} from '../api/personal-attendance-api';
import { ApproverField } from '../components/ApproverField';
import { AttachmentField } from '../components/AttachmentField';
import { DateField } from '../components/DateField';
import { TimeField } from '../components/TimeField';
import {
  ATTENDANCE_CATEGORIES,
  codesInCategory,
  findCode,
  unitOf,
  type AttendanceCategory,
  type AttendanceCode,
  type DeductionTarget,
} from '../lib/attendance-codes';
import {
  EMPTY_VALUE,
  REQUEST_STATUS_META,
  LEAVE_HOURS_PER_DAY,
  businessDays,
  datesInRange,
  isLiveRequest,
  todayYmd,
} from '../lib/attendance-format';
import { useAttendanceLabels } from '../lib/attendance-labels';
import type { AttendanceLabels } from '../lib/attendance-labels';

const DEFAULT_CODE = 7; // 연차

function balanceOf(leave: LeaveSummary | null, target: DeductionTarget): LeaveStat | null {
  if (!leave) return null;
  if (target === 'ANNUAL') return leave.annual;
  if (target === 'MONTHLY') return leave.monthly;
  if (target === 'ETC') return leave.etc;
  return null; // NONE / UNCONFIRMED
}

function defaultForm() {
  const today = todayYmd();
  return {
    code: DEFAULT_CODE,
    startDate: today,
    endDate: today,
    halfDay: 'AM' as HalfDay,
    startTime: '09:00',
    reason: '',
    attachments: [] as RequestAttachment[],
  };
}

function SummaryCard({
  icon,
  label,
  value,
  sub,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="rounded-xl border border-app-border bg-app-surface px-4 py-3">
      <div className="flex items-center gap-2 text-xs font-medium text-app-ink-muted">
        {icon}
        {label}
      </div>
      <div className="mt-1 text-xl font-bold tabular-nums text-app-accent">{value}</div>
      {sub ? <div className="mt-0.5 text-xs text-app-ink-muted">{sub}</div> : null}
    </div>
  );
}

/** 신청 1건의 사용량 표기 — 일수 / 반차 / 시간 */
function usageLabel(
  r: AttendanceRequest,
  code: AttendanceCode | undefined,
  labels: AttendanceLabels,
): string {
  if (!code) return labels.leaveDays(r.days);
  const unit = unitOf(code);
  if (unit === 'HALF_DAY') {
    const half = r.halfDay ? `${labels.meridiem(r.halfDay)} ` : '';
    return `${half}${labels.work((code.hours ?? 4) * 60)}`;
  }
  if (unit === 'HOURLY') {
    const at = r.startTime ? `${labels.clock(r.startTime)} ` : '';
    return `${at}${labels.work((r.hours ?? code.hours ?? 1) * 60)}`;
  }
  return labels.leaveDays(r.days);
}

export function LeaveRequestView() {
  const { t } = useTranslation(['apps', 'common', 'shell']);
  const labels = useAttendanceLabels();
  const { token } = useAuth();
  const { confirm, confirmDialog } = useConfirm();
  const [requests, setRequests] = useState<AttendanceRequest[] | null>(null);
  const [line, setLine] = useState<ApprovalLine | null>(null);
  const [leave, setLeave] = useState<LeaveSummary | null>(null);
  const [gender, setGender] = useState<'M' | 'F' | null>(null);
  const [category, setCategory] = useState<AttendanceCategory>('LEAVE');
  const [form, setForm] = useState(defaultForm);
  const [submitting, setSubmitting] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const reasonRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    let alive = true;
    Promise.all([
      fetchAttendanceRequests(token),
      fetchApprovalLine(token),
      fetchPersonalAttendanceSummary(token),
    ])
      .then(([reqs, approvalLine, summary]) => {
        if (!alive) return;
        setRequests(reqs);
        setLine(approvalLine);
        setLeave(summary.leave);
        setGender(summary.gender ?? null);
      })
      .catch(() => alive && setLoadError(t('apps:personalAttendance.leave.loadFailed')));
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

  /**
   * 성별 조건 코드(생리)는 해당 성별에게만 노출. 성별 미확인이면 숨긴다.
   * 표시 순서는 맨 뒤로 보낸다 — 중간에 있으면 숨겨질 때 격자 배치가 흐트러진다.
   * (코드 마스터는 원본 표 순서를 유지하고 여기서만 재정렬한다)
   */
  const codes = useMemo(
    () =>
      codesInCategory(category)
        .filter((x) => !x.genderOnly || x.genderOnly === gender)
        .sort((a, b) => Number(!!a.genderOnly) - Number(!!b.genderOnly)),
    [category, gender],
  );
  const code = findCode(form.code) ?? codes[0];
  const unit = code ? unitOf(code) : 'DAY';
  const isRange = unit === 'DAY';

  // 카테고리를 바꾸면 그 카테고리의 첫 코드로 옮긴다
  const selectCategory = (next: AttendanceCategory) => {
    setCategory(next);
    const first = codesInCategory(next).filter((x) => !x.genderOnly || x.genderOnly === gender)[0];
    if (first) setForm((f) => ({ ...f, code: first.code, endDate: f.startDate }));
  };

  const invalidRange = isRange && !!form.endDate && form.endDate < form.startDate;
  const endDate = isRange ? form.endDate : form.startDate; // 반차·시간은 하루
  const dates = useMemo(() => datesInRange(form.startDate, endDate), [form.startDate, endDate]);

  const days =
    unit === 'HALF_DAY'
      ? 0.5
      : unit === 'HOURLY'
        ? Math.round(((code?.hours ?? 1) / LEAVE_HOURS_PER_DAY) * 100) / 100
        : businessDays(form.startDate, endDate);

  const balance = balanceOf(leave, code?.deduction ?? 'NONE');
  const shortOfBalance = balance != null && days > balance.remaining;
  // 사유 필수 항목은 코드 마스터가 정한다 (⚠ 대상 목록 확인 대기 중 — 현재 전부 false)
  const reasonRequired = code?.requiresReason ?? false;

  const live = useMemo(
    () => (requests ?? []).filter((r) => isLiveRequest(r.status)),
    [requests],
  );
  const overlapping = useMemo(
    () => live.filter((r) => r.startDate <= endDate && r.endDate >= form.startDate),
    [live, form.startDate, endDate],
  );

  const pendingCount = (requests ?? []).filter((r) => r.status === 'PENDING').length;

  const B = 'apps:personalAttendance.leave.block';
  const blockReason = !code
    ? t(`${B}.pickCode`)
    : !form.startDate
      ? t(`${B}.pickDate`)
      : invalidRange
        ? t(`${B}.endBeforeStart`)
        : dates.length === 0
          ? t(`${B}.invalidRange`)
          : days === 0
            ? t(`${B}.noBusinessDay`)
            : overlapping.length > 0
              ? t(`${B}.overlapping`)
              : shortOfBalance
                ? t(`${B}.overBalance`, {
                    code: labels.code(code),
                    remaining: labels.leaveDays(balance?.remaining ?? 0),
                  })
                : reasonRequired && form.reason.trim().length < 5
                  ? t('apps:personalAttendance.block.reasonTooShort', { count: 5 })
                  : !line
                    ? t('apps:personalAttendance.block.loadingApprovalLine')
                    : null;

  const submit = async () => {
    if (blockReason || submitting || !code) return;
    setSubmitting(true);
    try {
      const created = await createAttendanceRequest(
        token,
        {
          code: code.code,
          startDate: form.startDate,
          endDate,
          halfDay: unit === 'HALF_DAY' ? form.halfDay : null,
          startTime: unit === 'HOURLY' ? form.startTime : null,
          hours: unit === 'HOURLY' ? code.hours : null,
          reason: form.reason.trim(),
          attachments: form.attachments,
        },
        days,
      );
      setRequests((prev) => [created, ...(prev ?? [])]);
      setForm({ ...defaultForm(), code: code.code });
      const span =
        created.startDate === created.endDate
          ? labels.date(created.startDate)
          : `${labels.date(created.startDate)}~${labels.date(created.endDate)}`;
      setToast(
        t('apps:personalAttendance.leave.toast.created', {
          code: labels.code(code),
          usage: usageLabel(created, code, labels),
          span,
          approver: created.approverName,
        }),
      );
    } catch {
      setToast(t('apps:personalAttendance.toast.createFailed'));
    } finally {
      setSubmitting(false);
    }
  };

  const remove = async (r: AttendanceRequest) => {
    const rc = findCode(r.code);
    const ok = await confirm({
      title: t('apps:personalAttendance.leave.delete.title'),
      description: t('apps:personalAttendance.leave.delete.description', {
        date: labels.date(r.startDate),
        code: labels.code(rc),
      }),
      confirmLabel: t('common:actions.delete'),
      cancelLabel: t('common:actions.cancel'),
    });
    if (!ok) return;
    await deleteAttendanceRequest(token, r.id);
    setRequests((prev) => (prev ?? []).filter((x) => x.id !== r.id));
    setToast(t('apps:personalAttendance.toast.deleted'));
  };

  /** 시작일 내림차순 → 같은 시작일은 신청 시각 내림차순(최신이 맨 위). 차수는 시간순으로 매긴다. */
  const rows = useMemo(() => {
    const sorted = [...(requests ?? [])].sort((a, b) =>
      a.startDate !== b.startDate
        ? b.startDate.localeCompare(a.startDate)
        : b.requestedAt.localeCompare(a.requestedAt),
    );
    const totalByDate = new Map<string, number>();
    for (const r of sorted) totalByDate.set(r.startDate, (totalByDate.get(r.startDate) ?? 0) + 1);
    const seen = new Map<string, number>();
    return sorted.map((r) => {
      const idx = seen.get(r.startDate) ?? 0;
      seen.set(r.startDate, idx + 1);
      const attempts = totalByDate.get(r.startDate) ?? 1;
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
          <Plane className="size-5" />
        </span>
        <div>
          <h1 className="text-lg font-semibold text-app-ink">
            {t('shell:nav.personal-attendance-leave')}
          </h1>
          <p className="text-xs text-app-ink-muted">
            {t('apps:personalAttendance.leave.subtitle')}
          </p>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <SummaryCard
          icon={<Plane className="size-3.5" />}
          label={t('apps:personalAttendance.leave.summary.annualRemaining')}
          value={leave ? labels.leaveDays(leave.annual.remaining) : EMPTY_VALUE}
          sub={
            leave
              ? t('apps:personalAttendance.leave.summary.grantedUsed', {
                  granted: labels.leaveDays(leave.annual.granted),
                  used: labels.leaveDays(leave.annual.used),
                })
              : undefined
          }
        />
        <SummaryCard
          icon={<Plane className="size-3.5" />}
          label={t('apps:personalAttendance.leave.summary.monthlyRemaining')}
          value={leave ? labels.leaveDays(leave.monthly.remaining) : EMPTY_VALUE}
          sub={
            leave
              ? t('apps:personalAttendance.leave.summary.grantedUsed', {
                  granted: labels.leaveDays(leave.monthly.granted),
                  used: labels.leaveDays(leave.monthly.used),
                })
              : undefined
          }
        />
        <SummaryCard
          icon={<CheckCircle2 className="size-3.5" />}
          label={t('apps:personalAttendance.summary.pending')}
          value={t('apps:personalAttendance.requestCount', { count: pendingCount })}
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
            {/* 카테고리 */}
            <div>
              <span className="mb-1 block text-xs font-medium text-app-ink-muted">
                {t('apps:personalAttendance.leave.form.category')}
              </span>
              <div className="flex gap-1.5">
                {ATTENDANCE_CATEGORIES.map((cat) => {
                  const on = category === cat;
                  return (
                    <button
                      key={cat}
                      type="button"
                      aria-pressed={on}
                      onClick={() => selectCategory(cat)}
                      className={`flex-1 rounded-lg border py-1.5 text-sm font-semibold transition ${
                        on
                          ? 'border-app-accent bg-app-accent text-app-accent-fg'
                          : 'border-app-border bg-app-bg text-app-ink hover:bg-app-surface-hover'
                      }`}
                    >
                      {labels.category(cat)}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* 근태코드 */}
            <div>
              <span className="mb-1 block text-xs font-medium text-app-ink-muted">
                {t('apps:personalAttendance.leave.form.code')}
              </span>
              <div className="grid grid-cols-4 gap-1.5">
                {codes.map((x) => {
                  const on = form.code === x.code;
                  const bal = balanceOf(leave, x.deduction);
                  return (
                    <button
                      key={x.code}
                      type="button"
                      aria-pressed={on}
                      onClick={() => setForm((f) => ({ ...f, code: x.code, endDate: f.startDate }))}
                      className={`relative rounded-lg border px-1.5 py-1.5 text-center transition ${
                        on
                          ? 'border-app-accent bg-app-accent-weak'
                          : 'border-app-border bg-app-bg hover:bg-app-surface-hover'
                      }`}
                    >
                      <span className={`block text-sm font-semibold ${on ? 'text-app-accent' : 'text-app-ink'}`}>
                        {labels.code(x)}
                      </span>
                      <span className="block text-[10px] tabular-nums text-app-ink-muted">
                        {bal != null
                          ? labels.leaveDays(bal.remaining)
                          : x.allowsAttachment
                            ? t('apps:personalAttendance.attachment.label')
                            : ''}
                      </span>
                      {/* ERP 에 아직 없는 코드 */}
                      {x.isProvisional ? (
                        <span className="absolute right-0.5 top-0.5 text-[9px] font-bold text-amber-500">
                          {t('apps:personalAttendance.leave.form.provisionalTag')}
                        </span>
                      ) : null}
                    </button>
                  );
                })}
              </div>
              {code?.noteKey ? (
                <p className="mt-1 flex items-start gap-1 text-[11px] text-app-ink-muted">
                  <Info className="mt-0.5 size-3 shrink-0" />
                  {labels.codeNote(code)}
                </p>
              ) : null}
            </div>

            {/* 기간 — 일수 코드만 범위, 반차·시간은 하루 */}
            <div className="grid grid-cols-2 gap-3">
              <DateField
                id="ar-start-date"
                label={
                  isRange
                    ? t('apps:personalAttendance.leave.form.startDate')
                    : t('apps:personalAttendance.leave.form.useDate')
                }
                value={form.startDate}
                onChange={(v) =>
                  setForm((f) => ({ ...f, startDate: v, endDate: f.endDate < v ? v : f.endDate }))
                }
              />
              {isRange ? (
                <DateField
                  id="ar-end-date"
                  label={t('apps:personalAttendance.form.endDate')}
                  value={form.endDate}
                  min={form.startDate}
                  onChange={(v) => setForm((f) => ({ ...f, endDate: v }))}
                />
              ) : unit === 'HALF_DAY' ? (
                <div>
                  <span className="mb-1 block text-xs font-medium text-app-ink-muted">
                    {t('apps:personalAttendance.leave.form.halfDaySlot', {
                      hours: labels.work((code?.hours ?? 4) * 60),
                    })}
                  </span>
                  <div className="grid grid-cols-2 gap-2">
                    {(['AM', 'PM'] as HalfDay[]).map((h) => {
                      const on = form.halfDay === h;
                      return (
                        <button
                          key={h}
                          type="button"
                          aria-pressed={on}
                          onClick={() => setForm((f) => ({ ...f, halfDay: h }))}
                          className={`rounded-lg border py-2 text-sm font-semibold transition ${
                            on
                              ? 'border-app-accent bg-app-accent-weak text-app-accent'
                              : 'border-app-border bg-app-bg text-app-ink hover:bg-app-surface-hover'
                          }`}
                        >
                          {labels.meridiem(h)}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ) : (
                <TimeField
                  id="ar-start-time"
                  label={t('apps:personalAttendance.leave.form.startTimeWithHours', {
                    hours: labels.work((code?.hours ?? 1) * 60),
                  })}
                  value={form.startTime}
                  onChange={(v) => setForm((f) => ({ ...f, startTime: v }))}
                />
              )}
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-app-ink-muted" htmlFor="ar-reason">
                {reasonRequired
                  ? t('apps:personalAttendance.form.reason')
                  : t('apps:personalAttendance.leave.form.reasonOptional')}
              </label>
              <textarea
                ref={reasonRef}
                id="ar-reason"
                rows={2}
                value={form.reason}
                onChange={(e) => setForm((f) => ({ ...f, reason: e.target.value }))}
                placeholder={
                  reasonRequired
                    ? t('apps:personalAttendance.leave.form.reasonPlaceholderRequired')
                    : t('apps:personalAttendance.leave.form.reasonPlaceholderOptional')
                }
                className="w-full resize-none overflow-hidden rounded-lg border border-app-border bg-app-bg px-3 py-2 text-sm text-app-ink outline-none transition focus:ring-2 focus:ring-app-accent/40"
              />
            </div>

            {/* 증빙 첨부 — 코드 마스터가 허용한 항목만 */}
            {code?.allowsAttachment ? (
              <AttachmentField
                hint={t('apps:personalAttendance.leave.form.attachmentHint')}
              />
            ) : null}

            <ApproverField line={line} />

            {code?.isProvisional ? (
              <div className="flex items-start gap-2 rounded-lg bg-amber-500/10 p-2 text-[11px] text-amber-700 dark:text-amber-400">
                <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
                <span>
                  {t('apps:personalAttendance.leave.warn.provisionalCode', {
                    code: labels.code(code),
                  })}
                </span>
              </div>
            ) : null}
            {code?.deduction === 'UNCONFIRMED' ? (
              <div className="flex items-start gap-2 rounded-lg bg-amber-500/10 p-2 text-[11px] text-amber-700 dark:text-amber-400">
                <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
                <span>
                  {t('apps:personalAttendance.leave.warn.unconfirmedDeduction', {
                    code: labels.code(code),
                  })}
                </span>
              </div>
            ) : null}
            {shortOfBalance ? (
              <div className="flex items-start gap-2 rounded-lg bg-amber-500/10 p-2 text-[11px] text-amber-700 dark:text-amber-400">
                <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
                <span>
                  {t('apps:personalAttendance.leave.warn.shortOfBalance', {
                    code: labels.code(code),
                    remaining: labels.leaveDays(balance?.remaining ?? 0),
                    requested: labels.leaveDays(days),
                  })}
                </span>
              </div>
            ) : null}
            {overlapping.length > 0 ? (
              <div className="flex items-start gap-2 rounded-lg bg-rose-500/10 p-2 text-[11px] text-rose-600 dark:text-rose-400">
                <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
                <span>
                  {t('apps:personalAttendance.leave.warn.overlapping', {
                    ranges: overlapping
                      .map((r) => `${labels.date(r.startDate)}~${labels.date(r.endDate)}`)
                      .join(', '),
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
                : unit === 'DAY'
                  ? t('apps:personalAttendance.leave.submitDays', {
                      code: labels.code(code),
                      days: labels.leaveDays(days),
                    })
                  : unit === 'HALF_DAY'
                    ? t('apps:personalAttendance.leave.submitHalfDay', {
                        code: labels.code(code),
                        slot: labels.meridiem(form.halfDay),
                        hours: labels.work((code?.hours ?? 4) * 60),
                      })
                    : t('apps:personalAttendance.leave.submitCode', { code: labels.code(code) })}
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
                const rc = findCode(r.code);
                return (
                  <li
                    key={r.id}
                    className={`px-4 py-2.5 ${voided ? 'bg-slate-500/[0.055] dark:bg-slate-500/[0.12]' : ''}`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-semibold text-app-ink">
                          {labels.date(r.startDate)}
                          {r.startDate !== r.endDate ? ` ~ ${labels.date(r.endDate)}` : ''}
                        </span>
                        {attempts > 1 ? (
                          <span className="rounded bg-app-ink/10 px-1.5 text-[10px] font-semibold text-app-ink-muted">
                            {t('apps:personalAttendance.history.attempt', { count: attempt })}
                          </span>
                        ) : null}
                        {rc ? (
                          <span className="rounded bg-app-surface-subtle px-1.5 py-0.5 text-[10px] font-semibold text-app-ink-muted">
                            {labels.category(rc.category)}
                          </span>
                        ) : null}
                        <span className="rounded bg-app-accent-weak px-1.5 py-0.5 text-[11px] font-semibold text-app-accent">
                          {labels.code(rc)}
                        </span>
                        <span className="text-xs font-semibold tabular-nums text-app-ink-muted">
                          {usageLabel(r, rc, labels)}
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
                    {r.reason ? (
                      <p className="mt-0.5 line-clamp-2 text-xs text-app-ink-muted">{r.reason}</p>
                    ) : null}
                    {r.attachments.length > 0 ? (
                      <p className="mt-0.5 flex items-center gap-1 text-[11px] text-app-ink-muted">
                        <Paperclip className="size-3" />
                        {t('apps:personalAttendance.leave.history.attachments', {
                          count: r.attachments.length,
                          names: r.attachments.map((a) => a.name).join(', '),
                        })}
                      </p>
                    ) : null}
                    <p className="mt-0.5 text-[11px] text-app-ink-muted">
                      {[
                        t('apps:personalAttendance.history.approver', {
                          name: r.approverName,
                          role:
                            r.approverRole === 'ACTING_DEPT_HEAD'
                              ? t('apps:personalAttendance.approver.actingShort')
                              : '',
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
