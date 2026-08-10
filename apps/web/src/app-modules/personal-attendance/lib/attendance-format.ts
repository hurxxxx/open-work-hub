import type {
  AttendanceStatus,
  LeaveType,
  RequestStatus,
} from '../api/personal-attendance-api';

/**
 * 근태현황 + 4개 신청 화면(야근·휴가·특근·유연근무)이 공유하는 포맷·색상 정의.
 * 표시 문구는 여기 두지 않는다 — `attendance-labels.ts` 가 i18n 리소스에서 해석한다.
 */

export const STATUS_META: Record<
  AttendanceStatus,
  { badge: string; dot: string }
> = {
  NORMAL: {
    badge: 'bg-emerald-500/12 text-emerald-600 dark:text-emerald-400',
    dot: 'bg-emerald-500',
  },
  LATE: {
    badge: 'bg-amber-500/14 text-amber-600 dark:text-amber-400',
    dot: 'bg-amber-500',
  },
  EARLY_LEAVE: {
    badge: 'bg-orange-500/14 text-orange-600 dark:text-orange-400',
    dot: 'bg-orange-500',
  },
  MISSING: {
    badge: 'bg-rose-500/12 text-rose-600 dark:text-rose-400',
    dot: 'bg-rose-500',
  },
};

export const LEAVE_META: Record<LeaveType, { badge: string; text: string }> = {
  ANNUAL: {
    badge: 'bg-blue-500/14 text-blue-600 dark:text-blue-400',
    text: 'text-blue-600 dark:text-blue-400',
  },
  MONTHLY: {
    badge: 'bg-cyan-500/14 text-cyan-600 dark:text-cyan-400',
    text: 'text-cyan-600 dark:text-cyan-400',
  },
  ETC: {
    badge: 'bg-slate-500/14 text-slate-600 dark:text-slate-300',
    text: 'text-slate-600 dark:text-slate-300',
  },
};

export const HOLIDAY_WORK_META = {
  badge: 'bg-indigo-500/14 text-indigo-600 dark:text-indigo-400',
};

/** 신청 결재 상태 뱃지 */
export const REQUEST_STATUS_META: Record<RequestStatus, { badge: string }> = {
  PENDING: { badge: 'bg-amber-500/14 text-amber-600 dark:text-amber-400' },
  TIMEKEEPER_REVIEW: {
    badge: 'bg-indigo-500/14 text-indigo-600 dark:text-indigo-400',
  },
  GROUPWARE_APPROVAL: {
    badge: 'bg-violet-500/14 text-violet-600 dark:text-violet-400',
  },
  APPROVED: {
    badge: 'bg-emerald-500/12 text-emerald-600 dark:text-emerald-400',
  },
  REJECTED: { badge: 'bg-rose-500/12 text-rose-600 dark:text-rose-400' },
};

/** 진행 중(효력 예정) 상태 — 중복 검사·주 누적 합산에 포함해야 하는 건 */
export function isLiveRequest(status: RequestStatus): boolean {
  return status !== 'REJECTED';
}

/**
 * 특근 결재 단계 (신청 → 부서장 → 부서근태 담당자 → 그룹웨어 결재선 → 확정).
 * 그룹웨어 결재선은 부서마다 달라 앱이 그리지 않고 진행 상태만 표시한다.
 * 단계 문구는 `attendance-labels.ts` 의 `stageLabel` 이 해석한다.
 */
export const HOLIDAY_WORK_STAGES: RequestStatus[] = [
  'PENDING',
  'TIMEKEEPER_REVIEW',
  'GROUPWARE_APPROVAL',
  'APPROVED',
];

/** 현재 상태가 특근 단계 중 몇 번째인지 (-1 = 반려 등 해당 없음) */
export function holidayWorkStageIndex(status: RequestStatus): number {
  return HOLIDAY_WORK_STAGES.indexOf(status);
}

/** 값이 없는 자리를 채우는 표시 문자 — 언어와 무관한 기호다 */
export const EMPTY_VALUE = '—';

const KST_OFFSET_MS = 9 * 60 * 60 * 1000;

export interface CalendarDateParts {
  year: number;
  month: number;
  day: number;
  weekday: number;
}

/** YYYY-MM-DD를 실행 환경의 timezone과 무관한 달력 날짜로 해석한다. */
export function calendarDateParts(ymd: string): CalendarDateParts {
  const [year, month, day] = ymd.split('-').map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  return { year, month, day, weekday: date.getUTCDay() };
}

function calendarDateUtc(ymd: string): Date {
  const { year, month, day } = calendarDateParts(ymd);
  return new Date(Date.UTC(year, month - 1, day));
}

function paddedUtcYmd(date: Date): string {
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}-${String(date.getUTCDate()).padStart(2, '0')}`;
}

/** ISO 시각 → "HH:mm" (24시간제). 값이 없으면 EMPTY_VALUE */
export function timeLabel(iso: string | null): string {
  if (!iso) return EMPTY_VALUE;
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

/** 분 → { hours, minutes } (표기는 attendance-labels 가 담당) */
export function splitMinutes(min: number): { hours: number; minutes: number } {
  return { hours: Math.floor(min / 60), minutes: min % 60 };
}

/** 달력 셀용 짧은 근무시간 (예: 8.3h) */
export function shortHours(min: number | null): string {
  if (min == null) return '';
  return `${(min / 60).toFixed(1)}h`;
}

/** 해당 날짜가 속한 주의 시작일(일요일) 키 — 리스트 주간 음영 그룹핑용 */
export function weekStartKey(ymd: string): string {
  const d = calendarDateUtc(ymd);
  d.setUTCDate(d.getUTCDate() - d.getUTCDay());
  return `${d.getUTCFullYear()}-${d.getUTCMonth() + 1}-${d.getUTCDate()}`;
}

/** "HH:mm" → 분 (자정 기준) */
export function toMinutes(hhmm: string): number {
  const [h, m] = hhmm.split(':').map(Number);
  return h * 60 + m;
}

/** 분 → "HH:mm" (24시 넘어가면 다음날로 wrap) */
export function toHhmm(min: number): string {
  const v = ((min % 1440) + 1440) % 1440;
  return `${String(Math.floor(v / 60)).padStart(2, '0')}:${String(v % 60).padStart(2, '0')}`;
}

/** 종료가 시작보다 이르면 익일로 간주해 경과 분 계산 (야근 자정 넘김 대응) */
export function elapsedMinutes(start: string, end: string): number {
  const s = toMinutes(start);
  const e = toMinutes(end);
  return e >= s ? e - s : e + 1440 - s;
}

export type Meridiem = 'AM' | 'PM';

export const MERIDIEMS: Meridiem[] = ['AM', 'PM'];

/** "HH:mm"(24h) → 오전/오후 + 12시간제 */
export function to12h(hhmm: string): {
  meridiem: Meridiem;
  hour12: number;
  minute: number;
} {
  const [h, m] = hhmm.split(':').map(Number);
  return {
    meridiem: h < 12 ? 'AM' : 'PM',
    hour12: h % 12 === 0 ? 12 : h % 12,
    minute: m,
  };
}

/** 오전/오후 + 12시간제 → "HH:mm"(24h) */
export function from12h(
  meridiem: Meridiem,
  hour12: number,
  minute: number,
): string {
  const base = hour12 % 12; // 12시 → 0
  const h = meridiem === 'PM' ? base + 12 : base;
  return `${String(h).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
}

/** 오늘 날짜 YYYY-MM-DD (KST 기준) */
export function todayYmd(): string {
  return paddedUtcYmd(new Date(Date.now() + KST_OFFSET_MS));
}

/** start~end(양끝 포함) 사이의 모든 날짜 YYYY-MM-DD */
export function datesInRange(start: string, end: string): string[] {
  if (!start || !end || end < start) return [];
  const out: string[] = [];
  const cur = calendarDateUtc(start);
  const last = calendarDateUtc(end);
  while (cur <= last) {
    out.push(paddedUtcYmd(cur));
    cur.setUTCDate(cur.getUTCDate() + 1);
  }
  return out;
}

/** YYYY-MM-DD → 주말 여부 */
export function isWeekend(ymd: string): boolean {
  const wd = calendarDateParts(ymd).weekday;
  return wd === 0 || wd === 6;
}

/**
 * 휴가 1일에 해당하는 시간.
 * ⚠ 규정 확인 필요 — 반차(근태코드 19)가 4시간이라 1일 = 8시간으로 가정.
 */
export const LEAVE_HOURS_PER_DAY = 8;

/**
 * 휴가 일수를 "일 + 시간" 성분으로 나눈다. 소수 일수(11.5일)는 쓰지 않는다.
 * 표기는 `attendance-labels.ts` 의 `leaveDaysLabel` 이 담당한다.
 */
export function splitLeaveDays(
  days: number,
  hoursPerDay = LEAVE_HOURS_PER_DAY,
): { days: number; hours: number } {
  if (!Number.isFinite(days) || days <= 0) return { days: 0, hours: 0 };
  const whole = Math.floor(days);
  const hours = Math.round((days - whole) * hoursPerDay);
  // 반올림으로 하루가 꽉 찬 경우
  if (hours >= hoursPerDay) return { days: whole + 1, hours: 0 };
  return { days: whole, hours };
}

/**
 * 기간 내 영업일 수 (주말 제외).
 * ⚠ 공휴일 달력이 아직 없어 공휴일은 빠지지 않는다 — 연동 시 여기서 함께 제외할 것.
 */
export function businessDays(start: string, end: string): number {
  return datesInRange(start, end).filter((d) => !isWeekend(d)).length;
}
