import type { TFunction } from 'i18next';
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import type {
  AttendanceStatus,
  LeaveType,
  RequestStatus,
} from '../api/personal-attendance-api';
import type { AttendanceCategory, AttendanceCode } from './attendance-codes';
import {
  calendarDateParts,
  EMPTY_VALUE,
  LEAVE_HOURS_PER_DAY,
  splitLeaveDays,
  splitMinutes,
  to12h,
} from './attendance-format';
import type { Meridiem } from './attendance-format';

/**
 * 근태 화면의 모든 표시 문구를 i18n 리소스에서 해석한다.
 * 포맷·계산은 `attendance-format.ts`(순수 함수)가, 문구는 여기가 소유한다.
 */

const NS = 'apps:personalAttendance';

export interface AttendanceLabels {
  /** 근태 상태(정상/지각/조퇴/결근) */
  status: (status: AttendanceStatus) => string;
  /** 휴가 종류(연차/월차/기타) */
  leaveType: (type: LeaveType) => string;
  /** 신청 결재 상태 */
  requestStatus: (status: RequestStatus) => string;
  /** 특근 결재 단계 이름 */
  stage: (status: RequestStatus) => string;
  /** 특근 뱃지 */
  holidayWork: string;
  /** 근태(공제) 코드 이름 */
  code: (code: AttendanceCode | undefined) => string;
  /** 근태 코드 보충 설명 */
  codeNote: (code: AttendanceCode | undefined) => string | null;
  /** 근태 코드 분류 */
  category: (category: AttendanceCategory) => string;
  /** 요일 (0=일 ~ 6=토) */
  weekday: (day: number) => string;
  /** 요일 전체 (달력 헤더) */
  weekdays: string[];
  /** 오전/오후 */
  meridiem: (meridiem: Meridiem) => string;
  /** YYYY-MM-DD → "7.30 (목)" */
  date: (ymd: string) => string;
  /** 분 → "8시간 30분" */
  work: (minutes: number | null) => string;
  /** "HH:mm" → "오후 5:30" */
  clock: (hhmm: string) => string;
  /** 휴가 일수 → "11일 4시간" */
  leaveDays: (days: number, hoursPerDay?: number) => string;
}

export function createAttendanceLabels(t: TFunction): AttendanceLabels {
  const weekdays = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'].map(
    (key) => t(`${NS}.weekdays.${key}`),
  );

  const work = (minutes: number | null): string => {
    if (minutes == null) return EMPTY_VALUE;
    const { hours, minutes: rest } = splitMinutes(minutes);
    if (!hours) return t(`${NS}.duration.minutes`, { count: rest });
    return rest
      ? t(`${NS}.duration.hoursMinutes`, { hours, minutes: rest })
      : t(`${NS}.duration.hours`, { count: hours });
  };

  return {
    status: (status) => t(`${NS}.attendanceStatus.${status}`),
    leaveType: (type) => t(`${NS}.leaveType.${type}`),
    requestStatus: (status) => t(`${NS}.requestStatus.${status}`),
    stage: (status) => t(`${NS}.requestStage.${status}`),
    holidayWork: t(`${NS}.holidayWorkBadge`),
    code: (code) => {
      if (!code) return t(`${NS}.codeNames.unknown`);
      // 25~30 시간 코드만 시간 수로 이름이 갈린다 (1시간/2시간 …)
      return code.labelKey === 'hours'
        ? t(`${NS}.codeNames.hours`, { count: code.hours ?? 0 })
        : t(`${NS}.codeNames.${code.labelKey}`);
    },
    codeNote: (code) =>
      code?.noteKey ? t(`${NS}.codeNotes.${code.noteKey}`) : null,
    category: (category) => t(`${NS}.codeCategory.${category}`),
    weekday: (day) => weekdays[((day % 7) + 7) % 7] ?? '',
    weekdays,
    meridiem: (meridiem) => t(`${NS}.meridiem.${meridiem}`),
    date: (ymd) => {
      const { month, day, weekday } = calendarDateParts(ymd);
      return t(`${NS}.dateShort`, {
        month,
        day,
        weekday: weekdays[weekday],
      });
    },
    work,
    clock: (hhmm) => {
      const { meridiem, hour12, minute } = to12h(hhmm);
      return t(`${NS}.clock`, {
        meridiem: t(`${NS}.meridiem.${meridiem}`),
        hour: hour12,
        minute: String(minute).padStart(2, '0'),
      });
    },
    leaveDays: (days, hoursPerDay = LEAVE_HOURS_PER_DAY) => {
      const parts = splitLeaveDays(days, hoursPerDay);
      if (!parts.days && !parts.hours)
        return t(`${NS}.duration.days`, { count: 0 });
      if (!parts.days) return t(`${NS}.duration.hours`, { count: parts.hours });
      return parts.hours
        ? t(`${NS}.duration.daysHours`, {
            days: parts.days,
            hours: parts.hours,
          })
        : t(`${NS}.duration.days`, { count: parts.days });
    },
  };
}

export function useAttendanceLabels(): AttendanceLabels {
  const { t } = useTranslation(['apps', 'common']);
  return useMemo(() => createAttendanceLabels(t), [t]);
}
