import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import { ChevronDown, Clock, LogIn, LogOut } from 'lucide-react';

import { useAuth } from '@/src/platform/auth/auth-provider';

import {
  fetchPersonalAttendanceSummary,
  type AttendanceRecord,
  type AttendanceStatus,
  type FlexPeriod,
  type LeaveStat,
  type LeaveType,
  type PersonalAttendanceSummary,
} from '../api/personal-attendance-api';
import {
  HOLIDAY_WORK_META,
  isWeekend as isWeekendDate,
  LEAVE_META,
  STATUS_META,
  shortHours,
  timeLabel,
  todayYmd,
  weekStartKey,
} from '../lib/attendance-format';
import { useAttendanceLabels } from '../lib/attendance-labels';
import { HolidayWorkRequestView } from './HolidayWorkRequestView';
import { LeaveRequestView } from './LeaveRequestView';
import { OvertimeRequestView } from './OvertimeRequestView';

// 리스트 주간 구분용 색상(주가 바뀔 때마다 순환) — 지정 색을 은은하게(반투명)
const WEEK_TINTS = [
  'rgba(239,156,153,0.28)', // 빨
  'rgba(244,238,163,0.40)', // 노
  'rgba(242,196,165,0.32)', // 주
  'rgba(181,241,166,0.32)', // 초
  'rgba(115,173,236,0.26)', // 파
];

function StatusBadge({ status }: { status: AttendanceStatus }) {
  const labels = useAttendanceLabels();
  return (
    <span
      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ${STATUS_META[status].badge}`}
    >
      {labels.status(status)}
    </span>
  );
}

function LeaveCard({
  title,
  sub,
  stat,
}: {
  title: string;
  sub?: string;
  stat: LeaveStat;
}) {
  const { t } = useTranslation(['apps', 'common']);
  const labels = useAttendanceLabels();
  const [open, setOpen] = useState<'usages' | 'items' | null>(null);
  // 소수 일수(11.5일) 대신 "11일 4시간" 으로 표기
  const cells: {
    k: string;
    v: string;
    hi: boolean;
    panel: 'usages' | 'items' | null;
  }[] = [
    {
      k: t('apps:personalAttendance.leaveCard.granted'),
      v: labels.leaveDays(stat.granted),
      hi: false,
      panel: stat.items ? 'items' : null,
    },
    {
      k: t('apps:personalAttendance.leaveCard.used'),
      v: labels.leaveDays(stat.used),
      hi: false,
      panel: stat.usages ? 'usages' : null,
    },
    {
      k: t('apps:personalAttendance.leaveCard.remaining'),
      v: labels.leaveDays(stat.remaining),
      hi: true,
      panel: null,
    },
  ];
  return (
    <div className="relative rounded-xl border border-border bg-card p-4">
      <div className="text-sm font-semibold text-foreground">{title}</div>
      {sub ? (
        <div className="mt-0.5 text-xs text-muted-foreground">{sub}</div>
      ) : null}
      <div className="mt-3 flex gap-2">
        {cells.map((s) => {
          const clickable = s.panel != null;
          const isOpen = clickable && open === s.panel;
          return (
            <button
              key={s.k}
              type="button"
              onClick={
                clickable ? () => setOpen(isOpen ? null : s.panel) : undefined
              }
              className={`flex-1 rounded-lg px-2 py-2 text-center transition ${
                clickable
                  ? 'cursor-pointer bg-muted hover:bg-muted/70'
                  : 'cursor-default bg-muted'
              } ${isOpen ? 'ring-1 ring-primary' : ''}`}
            >
              <div className="flex items-center justify-center gap-0.5 text-[11px] font-medium text-muted-foreground">
                {s.k}
                {clickable ? (
                  <ChevronDown
                    className={`size-3 transition-transform ${isOpen ? 'rotate-180' : ''}`}
                  />
                ) : null}
              </div>
              <div
                className={`mt-0.5 whitespace-nowrap text-sm font-bold tabular-nums ${s.hi ? 'text-primary' : 'text-foreground'}`}
              >
                {s.v}
              </div>
            </button>
          );
        })}
      </div>

      {/* 상세 패널 (드롭다운) */}
      {open === 'usages' && stat.usages ? (
        <div className="absolute inset-x-0 top-full z-30 mt-1 rounded-xl border border-border bg-white p-3 shadow-lg dark:bg-neutral-900">
          <div className="mb-2 text-xs font-semibold text-foreground">
            {t('apps:personalAttendance.leaveCard.usageHistory')}
          </div>
          <ul className="max-h-56 space-y-1 overflow-auto text-xs">
            {stat.usages.map((u) => (
              <li key={u.date} className="flex items-center justify-between">
                <span className="text-foreground">{labels.date(u.date)}</span>
                <span className="text-muted-foreground">
                  {u.note ? `${u.note} ` : ''}
                  {labels.leaveDays(u.amount)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {open === 'items' && stat.items ? (
        <div className="absolute inset-x-0 top-full z-30 mt-1 rounded-xl border border-border bg-white p-3 shadow-lg dark:bg-neutral-900">
          <div className="mb-2 text-xs font-semibold text-foreground">
            {t('apps:personalAttendance.leaveCard.grantedTypes')}
          </div>
          <ul className="space-y-1.5 text-xs">
            {stat.items.map((it) => (
              <li key={it.name} className="flex flex-col">
                <span className="font-semibold text-foreground">{it.name}</span>
                {it.note ? (
                  <span className="text-muted-foreground">{it.note}</span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

/** 오늘 근무 카드 — 출근/퇴근 가운데 기준 2분할(각 좌측 정렬) + 총 근무시간 */
function TodayCard({ today }: { today: PersonalAttendanceSummary['today'] }) {
  const { t } = useTranslation(['apps', 'common']);
  const labels = useAttendanceLabels();
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-sm font-semibold text-foreground">
          {t('apps:personalAttendance.todayCard.title')}
        </span>
        <StatusBadge status={today.status} />
      </div>
      <div className="text-sm text-muted-foreground">
        {today.workStartLabel} – {today.workEndLabel}
      </div>

      {/* 가운데 기준 2분할, 각 칸 좌측 정렬 */}
      <div className="mt-3 grid grid-cols-2 divide-x divide-border">
        <div className="pr-3">
          <div className="text-[11px] font-medium text-muted-foreground">
            {t('apps:personalAttendance.todayCard.checkIn')}
          </div>
          <div className="mt-0.5 inline-flex items-center gap-1.5 text-sm font-semibold tabular-nums text-foreground">
            <LogIn className="size-4 text-emerald-600" />{' '}
            {timeLabel(today.checkInAt)}
          </div>
        </div>
        <div className="pl-3">
          <div className="text-[11px] font-medium text-muted-foreground">
            {t('apps:personalAttendance.todayCard.checkOut')}
          </div>
          <div className="mt-0.5 inline-flex items-center gap-1.5 text-sm font-semibold tabular-nums text-foreground">
            <LogOut className="size-4 text-rose-500" />{' '}
            {timeLabel(today.checkOutAt)}
          </div>
        </div>
      </div>

      {/* 총 근무시간 */}
      <div className="mt-3 flex items-center justify-between border-t border-border pt-2 text-sm">
        <span className="text-muted-foreground">
          {t('apps:personalAttendance.todayCard.totalWork')}
        </span>
        <span className="font-bold tabular-nums text-primary">
          {labels.work(today.workMinutes)}
        </span>
      </div>
    </div>
  );
}

interface DayInfo {
  status?: AttendanceStatus;
  leaveType?: LeaveType | null;
  workMinutes: number | null;
  isHolidayWork?: boolean;
}

function AttendanceCalendar({
  month,
  records,
  flexPeriods,
  birthday,
}: {
  month: string;
  records: AttendanceRecord[];
  flexPeriods: FlexPeriod[];
  birthday?: string; // "MM-DD"
}) {
  const { t } = useTranslation(['apps', 'common']);
  const labels = useAttendanceLabels();
  const [yy, mm] = month.split('-').map(Number);
  const dkey = (d: Date) =>
    `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;
  const localDate = (ymd: string) => {
    const [year, monthNumber, day] = ymd.split('-').map(Number);
    return new Date(year, monthNumber - 1, day);
  };

  const byDate = new Map<string, DayInfo>();
  for (const r of records) {
    const d = localDate(r.workDate);
    byDate.set(dkey(d), {
      status: r.status,
      leaveType: r.leaveType ?? null,
      workMinutes: r.workMinutes,
      isHolidayWork: r.isHolidayWork,
    });
  }

  // 유연근무 기간 → 날짜 Set + 시작일(라벨 표시용)
  const flexDates = new Set<string>();
  let firstFlexKey = '';
  for (const f of flexPeriods) {
    const s = localDate(f.start);
    const e = localDate(f.end);
    for (let cur = new Date(s); cur <= e; cur.setDate(cur.getDate() + 1)) {
      const k = dkey(cur);
      flexDates.add(k);
      if (!firstFlexKey) firstFlexKey = k;
    }
  }

  // 연속 스크롤 범위: 대상 월 기준 앞뒤 12개월(±1년 이동 지원), 주(일~토) 경계 정렬
  const rangeStart = new Date(yy, mm - 1 - 12, 1);
  rangeStart.setDate(rangeStart.getDate() - rangeStart.getDay());
  const rangeEnd = new Date(yy, mm - 1 + 13, 0);
  rangeEnd.setDate(rangeEnd.getDate() + (6 - rangeEnd.getDay()));

  const weeks: Date[][] = [];
  for (let cur = new Date(rangeStart); cur <= rangeEnd; ) {
    const week: Date[] = [];
    for (let i = 0; i < 7; i++) {
      week.push(new Date(cur));
      cur.setDate(cur.getDate() + 1);
    }
    weeks.push(week);
  }

  const todayKey = dkey(localDate(todayYmd()));
  const weekMinutes = (week: Date[]): number =>
    week.reduce<number>(
      (sum, d) => sum + (byDate.get(dkey(d))?.workMinutes ?? 0),
      0,
    );

  // 스크롤: 대상 월 첫 주로 자동 이동 + 스크롤 위치에 따라 헤더 월 라벨 갱신
  const scrollRef = useRef<HTMLDivElement>(null);
  const ROW_PX = 92; // 5.5rem 행 + 0.25rem gap
  const targetWeek = weeks.findIndex((w) =>
    w.some(
      (d) =>
        d.getFullYear() === yy && d.getMonth() + 1 === mm && d.getDate() === 1,
    ),
  );
  const [focus, setFocus] = useState({ yy, mm });
  useEffect(() => {
    const el = scrollRef.current;
    if (el && targetWeek > 0) el.scrollTop = targetWeek * ROW_PX;
  }, [targetWeek]);
  const handleScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const idx = Math.max(
      0,
      Math.min(weeks.length - 1, Math.round(el.scrollTop / ROW_PX)),
    );
    const mid = weeks[idx][3];
    setFocus({ yy: mid.getFullYear(), mm: mid.getMonth() + 1 });
  };
  // < > = 1개월, << >> = 1년 이동 (해당 월로 부드럽게 스크롤)
  const goMonths = (delta: number) => {
    const base = new Date(focus.yy, focus.mm - 1 + delta, 1);
    const ty = base.getFullYear();
    const tm = base.getMonth() + 1;
    const idx = weeks.findIndex((w) =>
      w.some(
        (d) =>
          d.getFullYear() === ty &&
          d.getMonth() + 1 === tm &&
          d.getDate() === 1,
      ),
    );
    const el = scrollRef.current;
    if (el && idx >= 0) el.scrollTo({ top: idx * ROW_PX, behavior: 'smooth' });
    setFocus({ yy: ty, mm: tm });
  };

  const renderDay = (date: Date) => {
    const key = dkey(date);
    const info = byDate.get(key);
    const isToday = key === todayKey;
    const isFlex = flexDates.has(key);
    const isFirst = date.getDate() === 1;
    const mmdd = `${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
    const isBirthday = birthday === mmdd;
    const wd = date.getDay();
    // 연속된 보라선을 위한 좌/우 이웃 유연근무 여부
    const prev = new Date(date);
    prev.setDate(prev.getDate() - 1);
    const next = new Date(date);
    next.setDate(next.getDate() + 1);
    const flexLeft = isFlex && wd !== 0 && flexDates.has(dkey(prev));
    const flexRight = isFlex && wd !== 6 && flexDates.has(dkey(next));
    const numColor =
      wd === 0
        ? 'text-rose-500'
        : wd === 6
          ? 'text-blue-700 dark:text-blue-400'
          : 'text-foreground';
    const monthAlt = date.getMonth() % 2 === 1; // 달 경계가 보이도록 은은한 교차 배경
    const numText = isFirst
      ? `${date.getMonth() + 1}/${date.getDate()}`
      : `${date.getDate()}`;
    const borderCls = isToday
      ? 'border-2 border-orange-400'
      : 'border-black/[0.06] dark:border-white/10';
    const bgCls = monthAlt ? 'bg-muted/20' : 'bg-card';
    return (
      <div
        key={key}
        className={`relative flex flex-col rounded-md border px-0.5 py-1 ${borderCls} ${bgCls}`}
      >
        {/* 날짜: 오른쪽 정렬 */}
        {isToday ? (
          <span className="flex flex-col items-end leading-none">
            <span className="whitespace-nowrap rounded-full bg-orange-500 px-1.5 py-0.5 text-[8px] font-bold uppercase tracking-wide text-white shadow-sm">
              ★ {t('apps:personalAttendance.calendar.today')} ★
            </span>
            <span className="mt-0.5 flex size-5 items-center justify-center rounded-full bg-orange-500 text-[11px] font-bold tabular-nums text-white">
              {date.getDate()}
            </span>
          </span>
        ) : (
          <span
            className={`w-full pr-0.5 text-right text-xs tabular-nums ${numColor}`}
          >
            {numText}
          </span>
        )}
        {/* 생일: 날짜 아래 케이크 */}
        {isBirthday ? (
          <span className="mt-0.5 text-center text-sm leading-none">🎂</span>
        ) : null}
        {/* 일자별 내용: 휴가종류 → 결근 → 특근 → 근무시간 (해당 월만) */}
        <span className="mt-0.5 flex flex-1 flex-col items-center justify-end gap-0.5 pb-1.5">
          {info?.leaveType ? (
            <span
              className={`rounded px-1 py-0.5 text-[10px] font-semibold ${LEAVE_META[info.leaveType].badge}`}
            >
              {labels.leaveType(info.leaveType)}
            </span>
          ) : info?.status === 'MISSING' ? (
            <span className="text-[10px] font-semibold text-rose-500">
              {labels.status('MISSING')}
            </span>
          ) : info?.isHolidayWork ? (
            <>
              <span
                className={`rounded px-1 text-[9px] font-semibold ${HOLIDAY_WORK_META.badge}`}
              >
                {labels.holidayWork}
              </span>
              <span className="text-[10px] font-semibold tabular-nums text-foreground">
                {shortHours(info.workMinutes)}
              </span>
            </>
          ) : info?.workMinutes != null ? (
            <span className="text-[10px] font-semibold tabular-nums text-foreground">
              {shortHours(info.workMinutes)}
            </span>
          ) : null}
        </span>
        {/* 유연근무: 배경 없이 얇고 연속된 옅은 보라색 선 */}
        {isFlex ? (
          <span
            className="pointer-events-none absolute bottom-1 h-1 rounded-full bg-violet-400/80"
            style={{
              left: flexLeft ? '-0.25rem' : '0.25rem',
              right: flexRight ? '-0.25rem' : '0.25rem',
            }}
          />
        ) : null}
        {key === firstFlexKey ? (
          <span className="absolute bottom-2.5 left-1 text-[9px] font-semibold leading-none text-violet-600 dark:text-violet-300">
            {t('apps:personalAttendance.calendar.flexShort')}
          </span>
        ) : null}
      </div>
    );
  };

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-border bg-card p-4">
      {/* 가운데 정렬 네비게이터: < > = 월 이동, << >> = 년 이동 */}
      <div className="mb-3 flex items-center justify-center gap-1 text-sm font-semibold text-foreground">
        <button
          type="button"
          onClick={() => goMonths(-1)}
          aria-label={t('apps:personalAttendance.calendar.prevMonth')}
          className="rounded px-1.5 py-0.5 text-muted-foreground transition hover:bg-muted hover:text-foreground"
        >
          &lt;
        </button>
        <button
          type="button"
          onClick={() => goMonths(-12)}
          aria-label={t('apps:personalAttendance.calendar.prevYear')}
          className="rounded px-1.5 py-0.5 text-muted-foreground transition hover:bg-muted hover:text-foreground"
        >
          &lt;&lt;
        </button>
        <span className="mx-2 min-w-[6.5rem] text-center tabular-nums">
          {t('apps:personalAttendance.monthLabel', {
            year: focus.yy,
            month: focus.mm,
          })}
        </span>
        <button
          type="button"
          onClick={() => goMonths(1)}
          aria-label={t('apps:personalAttendance.calendar.nextMonth')}
          className="rounded px-1.5 py-0.5 text-muted-foreground transition hover:bg-muted hover:text-foreground"
        >
          &gt;
        </button>
        <button
          type="button"
          onClick={() => goMonths(12)}
          aria-label={t('apps:personalAttendance.calendar.nextYear')}
          className="rounded px-1.5 py-0.5 text-muted-foreground transition hover:bg-muted hover:text-foreground"
        >
          &gt;&gt;
        </button>
      </div>
      {/* 요일 헤더: 7일 + 근무시간 결산 = 8열 */}
      <div className="mb-1 grid grid-cols-8 gap-1 text-center text-xs">
        {labels.weekdays.map((w, i) => (
          <div
            key={w}
            className={`py-1 font-medium ${i === 0 ? 'text-rose-500' : i === 6 ? 'text-blue-700 dark:text-blue-400' : 'text-muted-foreground'}`}
          >
            {w}
          </div>
        ))}
        <div className="py-1 font-medium text-muted-foreground">
          {t('apps:personalAttendance.calendar.workHours')}
        </div>
      </div>
      {/* 스크롤바 숨김 (스크롤 기능은 유지) */}
      <style>{`.pa-noscrollbar::-webkit-scrollbar{display:none}.pa-noscrollbar{-ms-overflow-style:none;scrollbar-width:none}`}</style>
      {/* 연속 스크롤: 위로 전주·전월 / 아래로 다음주·다음월 */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="pa-noscrollbar grid min-h-0 flex-1 grid-cols-8 gap-1 overflow-y-auto text-center text-xs"
        style={{ gridTemplateRows: `repeat(${weeks.length}, 5.5rem)` }}
      >
        {weeks.map((week, weekIdx) => {
          const total = weekMinutes(week);
          return (
            <div key={`w${weekIdx}`} className="contents">
              {week.map((date) => renderDay(date))}
              <div className="flex h-full flex-col items-center justify-center rounded-md border border-black/[0.06] dark:border-white/10 bg-muted/40 px-0.5 py-1">
                {total > 0 ? (
                  <span className="text-xs font-bold tabular-nums text-foreground">
                    {shortHours(total)}
                  </span>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** 근태현황(기본 탭) — 오늘 근무·휴가 카드 + 좌 리스트 / 우 달력 */
function AttendanceOverview() {
  const { t } = useTranslation(['apps', 'common']);
  const labels = useAttendanceLabels();
  const { token } = useAuth();
  const [data, setData] = useState<PersonalAttendanceSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetchPersonalAttendanceSummary(token)
      .then((res) => alive && setData(res))
      .catch(
        () => alive && setError(t('apps:personalAttendance.errors.loadFailed')),
      );
    return () => {
      alive = false;
    };
  }, [t, token]);

  const monthLabel = useMemo(() => {
    if (!data) return '';
    const [y, m] = data.month.split('-');
    return t('apps:personalAttendance.monthLabel', {
      year: Number(y),
      month: Number(m),
    });
  }, [data, t]);

  if (error) {
    return (
      <div style={{ paddingInline: '4%' }} className="w-full py-6">
        <p className="text-sm text-rose-600">{error}</p>
      </div>
    );
  }
  if (!data) {
    return (
      <div style={{ paddingInline: '4%' }} className="w-full py-6">
        <div className="h-24 animate-pulse rounded-xl bg-muted" />
      </div>
    );
  }

  const { today, leave, monthlyRecords, flexPeriods } = data;

  // 토·일은 특근 근무가 있을 때만 노출 (평일은 항상 노출)
  const visibleRecords = monthlyRecords.filter((rec) => {
    return isWeekendDate(rec.workDate) ? !!rec.isHolidayWork : true;
  });

  // 리스트 주간 구분: 같은 주(週)끼리 투명 색상 블록을 순환 배정해 그룹이 한눈에 보이도록
  const weekOrder: string[] = [];
  const tintByDate = new Map<string, string>();
  for (const rec of visibleRecords) {
    const wk = weekStartKey(rec.workDate);
    let i = weekOrder.indexOf(wk);
    if (i === -1) {
      weekOrder.push(wk);
      i = weekOrder.length - 1;
    }
    tintByDate.set(rec.workDate, WEEK_TINTS[i % WEEK_TINTS.length]);
  }

  // 평균 주간 근무시간 = 전체 근무시간 합계 / 주 수
  const totalWorkMin = visibleRecords.reduce(
    (s, r) => s + (r.workMinutes ?? 0),
    0,
  );
  const avgWeeklyMin = weekOrder.length
    ? Math.round(totalWorkMin / weekOrder.length)
    : 0;

  return (
    <div
      style={{ paddingInline: '4%' }}
      className="flex w-full flex-col gap-3 py-4"
    >
      {/* header — 좌측 정렬 */}
      <header className="flex items-center gap-3">
        <span className="flex size-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <Clock className="size-6" />
        </span>
        <div>
          <h1 className="text-xl font-semibold text-foreground">
            {t('shell:apps.personal-attendance')}
          </h1>
          <p className="text-sm text-muted-foreground">
            {t('apps:personalAttendance.overview.subtitle', {
              name: data.profileName,
            })}
          </p>
        </div>
      </header>

      {/* 오늘 근무 + 휴가 현황 카드 */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <TodayCard today={today} />
        <LeaveCard
          title={t('apps:personalAttendance.leaveCard.annual.title')}
          sub={t('apps:personalAttendance.leaveCard.annual.sub')}
          stat={leave.annual}
        />
        <LeaveCard
          title={t('apps:personalAttendance.leaveCard.monthly.title')}
          sub={t('apps:personalAttendance.leaveCard.monthly.sub')}
          stat={leave.monthly}
        />
        <LeaveCard
          title={t('apps:personalAttendance.leaveCard.etc.title')}
          sub={t('apps:personalAttendance.leaveCard.etc.sub')}
          stat={leave.etc}
        />
      </div>

      {/* 2분할: 좌 리스트 / 우 달력 — 뷰포트에 맞춰 한 화면 + 내부 스크롤 */}
      <div className="grid grid-cols-1 gap-4 lg:h-[calc(100vh-13.5rem)] lg:grid-cols-2 lg:grid-rows-1">
        {/* 좌: 리스트 */}
        <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-border bg-card">
          <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
            <h2 className="text-sm font-semibold text-foreground">
              {t('apps:personalAttendance.overview.recordsTitle', {
                month: monthLabel,
              })}
            </h2>
          </div>
          <ul className="min-h-0 flex-1 overflow-y-auto">
            {visibleRecords.map((rec) => (
              <li
                key={rec.workDate}
                style={{ backgroundColor: tintByDate.get(rec.workDate) }}
                className="flex items-center justify-between gap-3 px-4 py-2"
              >
                <div className="flex items-center gap-2.5">
                  <span className="w-14 text-xs text-foreground">
                    {labels.date(rec.workDate)}
                  </span>
                  {rec.leaveType ? (
                    <span
                      className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-semibold ${LEAVE_META[rec.leaveType].badge}`}
                    >
                      {t('apps:personalAttendance.overview.leaveUsed', {
                        type: labels.leaveType(rec.leaveType),
                      })}
                    </span>
                  ) : (
                    <span className="text-xs tabular-nums text-muted-foreground">
                      {timeLabel(rec.checkInAt)} ~ {timeLabel(rec.checkOutAt)}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {rec.leaveType ? (
                    <span className="text-xs text-muted-foreground">
                      {t('apps:personalAttendance.overview.leave')}
                    </span>
                  ) : (
                    <>
                      {rec.isHolidayWork ? (
                        <span
                          className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-semibold ${HOLIDAY_WORK_META.badge}`}
                        >
                          {labels.holidayWork}
                        </span>
                      ) : null}
                      <span className="text-xs tabular-nums text-muted-foreground">
                        {labels.work(rec.workMinutes)}
                      </span>
                      <StatusBadge status={rec.status} />
                    </>
                  )}
                </div>
              </li>
            ))}
          </ul>
          {/* 평균 주간 근무시간 합산 */}
          <div className="flex items-center justify-between border-t border-border px-4 py-2.5 text-sm">
            <span className="font-semibold text-foreground">
              {t('apps:personalAttendance.overview.avgWeekly')}
            </span>
            <span className="font-bold tabular-nums text-primary">
              {labels.work(avgWeeklyMin)}
            </span>
          </div>
        </div>

        {/* 우: 달력 */}
        <AttendanceCalendar
          month={data.month}
          records={visibleRecords}
          flexPeriods={flexPeriods}
          birthday={data.birthday}
        />
      </div>
    </div>
  );
}

/** 준비 중인 신청 탭 자리표시 — 화면 완성 시 실제 뷰로 교체 */
function ComingSoon({ title }: { title: string }) {
  const { t } = useTranslation(['apps', 'common']);
  return (
    <div style={{ paddingInline: '4%' }} className="w-full py-6">
      <div className="rounded-xl border border-dashed border-border bg-card p-10 text-center">
        <p className="text-sm font-semibold text-foreground">{title}</p>
        <p className="mt-1 text-sm text-muted-foreground">
          {t('apps:personalAttendance.comingSoon')}
        </p>
      </div>
    </div>
  );
}

/**
 * 좌측 사이드바 nav 는 같은 경로(/personal-attendance)에 ?tab= 만 붙여 이동한다
 * (manifest.navItems 의 pathSuffix). 여기서 tab 값으로 화면을 분기한다.
 */
export function PersonalAttendanceView() {
  const { t } = useTranslation(['apps', 'common', 'shell']);
  const [searchParams] = useSearchParams();
  const tab = searchParams.get('tab');

  switch (tab) {
    case 'overtime':
      return <OvertimeRequestView />;
    case 'leave':
      return <LeaveRequestView />;
    case 'holiday':
      return <HolidayWorkRequestView />;
    case 'flex':
      return <ComingSoon title={t('shell:nav.personal-attendance-flex')} />;
    default:
      return <AttendanceOverview />;
  }
}
