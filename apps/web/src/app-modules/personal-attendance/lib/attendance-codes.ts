/**
 * 근태(공제) 코드 마스터 — 레거시 ERP Deduction Code 표(1~30)와 1:1 대응.
 * UI 프로토타입용 코드 목록. 향후 commute API가 이 계약의 소유권을 가져간다.
 *
 * code/daysHoursType/dayTime 은 원본 표 컬럼 그대로다(daysHoursType 만 enum 으로 표기).
 * 원본 Deduction Code Name 은 labelKey 로 가리키고 문구는 i18n 리소스가 소유한다.
 * category/hours/isProvisional/deduction 은 앱이 쓰기 위해 붙인 파생 정보.
 *
 * ⚠ isProvisional=true (25~30 시간 코드)는 원본 비고가 "신규생성 필요" —
 *    ERP 에 아직 없는 코드다. 원본의 Days/Hours_type·DAY-TIME 이 공란이라
 *    daysHoursType 은 'HOURS' 잠정값, dayTime 은 null 로 둔다.
 * ⚠ deduction='UNCONFIRMED' 는 어느 잔여에서 차감하는지 규정 미확인. 임의로 정하지 않았다.
 *
 * 4시간이 시간 코드에 없는 이유: 반차(19)가 4시간이다.
 */

export type AttendanceCategory = 'TRIP' | 'TRAINING' | 'LEAVE' | 'DRILL' | 'ETC';

/** 레거시 Days/Hours_type 컬럼 값 (원본 표기: 일수 / 반차 / 시간) */
export type DaysHoursType = 'DAYS' | 'HALF_DAY' | 'HOURS';

/** 앱에서의 입력 단위 — daysHoursType 에서 파생 */
export type AttendanceUnit = 'DAY' | 'HALF_DAY' | 'HOURLY';

/** 차감 대상 잔여. NONE = 차감 없음, UNCONFIRMED = 규정 확인 필요 */
export type DeductionTarget = 'ANNUAL' | 'MONTHLY' | 'ETC' | 'NONE' | 'UNCONFIRMED';

export interface AttendanceCode {
  code: number; // 레거시 Deduction Code — 화면에는 노출하지 않는다(내부 식별자)
  /**
   * 표시 문구 resource key (`apps:personalAttendance.codeNames.<labelKey>`).
   * 레거시 Deduction Code Name 원문은 향후 서버 계약과 ko-KR 리소스가 보유한다.
   */
  labelKey: string;
  category: AttendanceCategory;
  daysHoursType: DaysHoursType;
  dayTime: number | null; // 일수=1, 반차=3, 시간=미정(null)
  hours: number | null; // 반차=4, 시간 코드=1~7
  isProvisional: boolean; // 비고 "신규생성 필요"
  deduction: DeductionTarget;
  /**
   * 신청 시 사유를 반드시 적어야 하는 항목.
   * ⚠ 대상 목록 확인 대기 중 — 임의로 정하지 않고 전부 false 로 둔다.
   *   목록을 받으면 해당 코드만 true 로 바꾸면 된다.
   */
  requiresReason: boolean;
  /** 신청 시 파일·사진(증빙) 업로드를 제공하는 항목 */
  allowsAttachment: boolean;
  genderOnly?: 'M' | 'F';
  /** 보충 설명 resource key (`apps:personalAttendance.codeNotes.<noteKey>`) */
  noteKey?: string;
}

const c = (
  code: number,
  labelKey: string,
  category: AttendanceCategory,
  deduction: DeductionTarget,
  extra: Partial<AttendanceCode> = {},
): AttendanceCode => ({
  code,
  labelKey,
  category,
  daysHoursType: 'DAYS',
  dayTime: 1,
  hours: null,
  isProvisional: false,
  deduction,
  requiresReason: false,
  allowsAttachment: false,
  ...extra,
});

/** 증빙 첨부를 제공하는 코드 (사용자 지정) */
const ATTACH = { allowsAttachment: true } as const;

export const ATTENDANCE_CODES: AttendanceCode[] = [
  c(1, 'trip', 'TRIP', 'NONE'),
  c(2, 'training', 'TRAINING', 'NONE', ATTACH),
  c(3, 'dispatch', 'TRIP', 'NONE'),
  c(4, 'overseasTrip', 'TRIP', 'NONE'),
  c(5, 'overseasTraining', 'TRAINING', 'NONE', ATTACH),
  c(6, 'monthlyLeave', 'LEAVE', 'MONTHLY'),
  c(7, 'annualLeave', 'LEAVE', 'ANNUAL'),
  c(8, 'industrialAccident', 'ETC', 'NONE'),
  c(9, 'leaveOfAbsence', 'ETC', 'NONE'),
  c(10, 'workInjury', 'ETC', 'NONE'),
  c(11, 'menstrual', 'LEAVE', 'ETC', {
    genderOnly: 'F',
    noteKey: 'menstrual',
  }),
  c(12, 'familyEvent', 'LEAVE', 'UNCONFIRMED', {
    noteKey: 'familyEvent',
  }),
  c(13, 'graduation', 'LEAVE', 'UNCONFIRMED'),
  c(14, 'nightDuty', 'LEAVE', 'NONE'),
  c(15, 'reserveForcesDrill', 'DRILL', 'NONE', { ...ATTACH, noteKey: 'drillEvidence' }),
  c(16, 'civilDefenseDrill', 'DRILL', 'NONE', { ...ATTACH, noteKey: 'drillEvidence' }),
  c(17, 'absence', 'ETC', 'NONE'),
  c(18, 'shutdown', 'ETC', 'NONE'),
  c(19, 'halfDay', 'LEAVE', 'UNCONFIRMED', {
    daysHoursType: 'HALF_DAY',
    dayTime: 3,
    hours: 4,
    noteKey: 'halfDay',
  }),
  c(20, 'etc', 'ETC', 'UNCONFIRMED'),
  c(21, 'longService', 'LEAVE', 'UNCONFIRMED'),
  c(22, 'birthday', 'LEAVE', 'ETC'),
  c(23, 'retirementAge', 'LEAVE', 'UNCONFIRMED'),
  c(24, 'substitute', 'LEAVE', 'NONE', {
    noteKey: 'substitute',
  }),
  // 25~30 신규생성 필요 (4시간은 반차가 대신함)
  ...[1, 2, 3, 5, 6, 7].map((h, i) =>
    c(25 + i, 'hours', 'LEAVE', 'UNCONFIRMED', {
      daysHoursType: 'HOURS',
      dayTime: null,
      hours: h,
      isProvisional: true,
      noteKey: 'provisionalHours',
    }),
  ),
];

export const ATTENDANCE_CATEGORIES: AttendanceCategory[] = [
  'TRIP',
  'TRAINING',
  'LEAVE',
  'DRILL',
  'ETC',
];

/** 입력 단위 — 레거시 Days/Hours_type 에서 파생 */
export function unitOf(code: AttendanceCode): AttendanceUnit {
  if (code.daysHoursType === 'HALF_DAY') return 'HALF_DAY';
  if (code.daysHoursType === 'HOURS') return 'HOURLY';
  return 'DAY';
}

export function codesInCategory(category: AttendanceCategory): AttendanceCode[] {
  return ATTENDANCE_CODES.filter((x) => x.category === category);
}

export function findCode(code: number): AttendanceCode | undefined {
  return ATTENDANCE_CODES.find((x) => x.code === code);
}
