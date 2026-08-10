// i18n-exempt-file: 기본 비활성·숨김 UI 프로토타입의 MOCK_* payload 픽스처다.
// 화면 문구는 이 파일에 두지 않고 apps:personalAttendance 리소스가 소유한다.
// 실제 API 전환은 router/RBAC/OpenAPI/generated client를 함께 도입하는 별도 변경에서 한다.

export type AttendanceStatus = 'NORMAL' | 'LATE' | 'EARLY_LEAVE' | 'MISSING';
/** 휴가 종류. 표시 문구는 `attendance-labels.ts` 가 리소스에서 해석한다. */
export type LeaveType = 'ANNUAL' | 'MONTHLY' | 'ETC';

export interface TodayAttendance {
  workDate: string;
  checkInAt: string | null;
  checkOutAt: string | null;
  status: AttendanceStatus;
  workMinutes: number | null;
  workStartLabel: string;
  workEndLabel: string;
}

export interface AttendanceRecord {
  workDate: string;
  checkInAt: string | null;
  checkOutAt: string | null;
  workMinutes: number | null;
  status: AttendanceStatus;
  leaveType?: LeaveType | null; // 휴가 사용일이면 종류(연차/월차/기타)
  isHolidayWork?: boolean; // 토/일·공휴일 특근 근무 여부
}

/** 유연근무 적용 기간 (달력에 옅은 보라색 밴드로 표시) */
export interface FlexPeriod {
  start: string; // YYYY-MM-DD
  end: string; // YYYY-MM-DD
  label: string;
}

export interface LeaveUsage {
  date: string; // YYYY-MM-DD
  amount: number; // 사용 일수 (1 = 종일, 0.5 = 반차)
  note?: string;
}
export interface LeaveItem {
  name: string;
  note?: string;
}
export interface LeaveStat {
  granted: number; // 발생
  used: number; // 사용
  remaining: number; // 잔여
  usages?: LeaveUsage[]; // 사용 내역 (연차/월차) — "사용" 클릭 시 표시
  items?: LeaveItem[]; // 발생(보유) 휴가 종류 (기타휴가) — "발생" 클릭 시 표시
}
export interface LeaveSummary {
  annual: LeaveStat;
  monthly: LeaveStat;
  etc: LeaveStat;
}

export interface PersonalAttendanceSummary {
  profileName: string;
  gender?: 'M' | 'F' | null; // 인사 정보 — 성별 조건 휴가(보건휴가 등) 노출 판단용
  birthday?: string; // "MM-DD" (생일 — 달력에 해치 표시)
  month: string; // "YYYY-MM"
  today: TodayAttendance;
  leave: LeaveSummary;
  monthlyRecords: AttendanceRecord[];
  flexPeriods: FlexPeriod[];
}

// ---- Mock 데이터 ----
function iso(date: string, time: string): string {
  return `${date}T${time}:00+09:00`;
}

const MOCK_SUMMARY: PersonalAttendanceSummary = {
  profileName: '이서연',
  // ⚠ 실제 값은 인사 정보에서 온다. 성별 조건 휴가(보건휴가) 노출을 확인하려고 Mock 에서만 'F'.
  gender: 'F',
  birthday: '07-29',
  month: '2026-07',
  today: {
    workDate: '2026-07-27',
    checkInAt: iso('2026-07-27', '08:02'),
    checkOutAt: iso('2026-07-27', '17:20'),
    status: 'NORMAL',
    // 08:02~17:20 이지만 야근(17:00 이후) 미승인 → 정규 종료 17:00까지만 인정. -점심 1h = 7시간 58분
    workMinutes: 478,
    workStartLabel: '08:00 AM',
    workEndLabel: '05:00 PM',
  },
  leave: {
    annual: {
      granted: 15,
      used: 3.5,
      remaining: 11.5,
      usages: [
        { date: '2026-03-14', amount: 1 },
        { date: '2026-05-02', amount: 1 },
        { date: '2026-06-20', amount: 0.5, note: '반차' },
        { date: '2026-07-14', amount: 1 },
      ],
    },
    monthly: {
      granted: 6,
      used: 5,
      remaining: 1,
      usages: [
        { date: '2026-02-10', amount: 1 },
        { date: '2026-03-23', amount: 1 },
        { date: '2026-04-17', amount: 1 },
        { date: '2026-06-05', amount: 1 },
        { date: '2026-07-10', amount: 1 },
      ],
    },
    // 기타휴가 = "자동 발생형"만. 경조·예비군 등 신청형은 휴가 신청 플로우에서 처리.
    etc: {
      granted: 2,
      used: 1,
      remaining: 1,
      items: [
        { name: '생일', note: '생일 ±2개월 내 1일 자동 부여' },
        { name: '보건휴가', note: '여성 근로자 월 1일 (성별에 따라 표시)' },
      ],
    },
  },
  monthlyRecords: [
    { workDate: '2026-07-31', checkInAt: iso('2026-07-31', '07:57'), checkOutAt: iso('2026-07-31', '17:04'), workMinutes: 480, status: 'NORMAL' },
    { workDate: '2026-07-30', checkInAt: iso('2026-07-30', '08:00'), checkOutAt: iso('2026-07-30', '17:10'), workMinutes: 480, status: 'NORMAL' },
    { workDate: '2026-07-29', checkInAt: iso('2026-07-29', '08:12'), checkOutAt: iso('2026-07-29', '17:02'), workMinutes: 468, status: 'LATE' },
    { workDate: '2026-07-28', checkInAt: iso('2026-07-28', '07:56'), checkOutAt: iso('2026-07-28', '17:05'), workMinutes: 480, status: 'NORMAL' },
    { workDate: '2026-07-27', checkInAt: iso('2026-07-27', '08:02'), checkOutAt: iso('2026-07-27', '17:20'), workMinutes: 478, status: 'NORMAL' },
    { workDate: '2026-07-24', checkInAt: iso('2026-07-24', '08:02'), checkOutAt: iso('2026-07-24', '17:20'), workMinutes: 478, status: 'NORMAL' },
    { workDate: '2026-07-23', checkInAt: iso('2026-07-23', '07:58'), checkOutAt: iso('2026-07-23', '17:05'), workMinutes: 487, status: 'NORMAL' },
    { workDate: '2026-07-22', checkInAt: iso('2026-07-22', '08:14'), checkOutAt: iso('2026-07-22', '17:02'), workMinutes: 468, status: 'LATE' },
    { workDate: '2026-07-21', checkInAt: iso('2026-07-21', '07:55'), checkOutAt: iso('2026-07-21', '16:10'), workMinutes: 435, status: 'EARLY_LEAVE' },
    { workDate: '2026-07-18', checkInAt: iso('2026-07-18', '08:00'), checkOutAt: iso('2026-07-18', '17:01'), workMinutes: 481, status: 'NORMAL', isHolidayWork: true },
    { workDate: '2026-07-17', checkInAt: iso('2026-07-17', '07:59'), checkOutAt: iso('2026-07-17', '17:03'), workMinutes: 484, status: 'NORMAL' },
    { workDate: '2026-07-16', checkInAt: null, checkOutAt: null, workMinutes: null, status: 'MISSING' },
    { workDate: '2026-07-15', checkInAt: iso('2026-07-15', '08:01'), checkOutAt: iso('2026-07-15', '17:00'), workMinutes: 479, status: 'NORMAL' },
    { workDate: '2026-07-14', checkInAt: null, checkOutAt: null, workMinutes: null, status: 'NORMAL', leaveType: 'ANNUAL' },
    { workDate: '2026-07-13', checkInAt: iso('2026-07-13', '07:59'), checkOutAt: iso('2026-07-13', '17:03'), workMinutes: 480, status: 'NORMAL' },
    { workDate: '2026-07-10', checkInAt: null, checkOutAt: null, workMinutes: null, status: 'NORMAL', leaveType: 'MONTHLY' },
    { workDate: '2026-07-09', checkInAt: iso('2026-07-09', '07:59'), checkOutAt: iso('2026-07-09', '17:03'), workMinutes: 480, status: 'NORMAL' },
    { workDate: '2026-07-08', checkInAt: iso('2026-07-08', '08:11'), checkOutAt: iso('2026-07-08', '17:00'), workMinutes: 469, status: 'LATE' },
    { workDate: '2026-07-07', checkInAt: iso('2026-07-07', '07:58'), checkOutAt: iso('2026-07-07', '17:04'), workMinutes: 480, status: 'NORMAL' },
    { workDate: '2026-07-06', checkInAt: iso('2026-07-06', '07:57'), checkOutAt: iso('2026-07-06', '17:02'), workMinutes: 480, status: 'NORMAL' },
    { workDate: '2026-07-03', checkInAt: iso('2026-07-03', '08:00'), checkOutAt: iso('2026-07-03', '17:00'), workMinutes: 480, status: 'NORMAL' },
    { workDate: '2026-07-02', checkInAt: iso('2026-07-02', '08:02'), checkOutAt: iso('2026-07-02', '17:05'), workMinutes: 478, status: 'NORMAL' },
    { workDate: '2026-07-01', checkInAt: iso('2026-07-01', '07:55'), checkOutAt: iso('2026-07-01', '17:06'), workMinutes: 480, status: 'NORMAL' },
  ],
  flexPeriods: [{ start: '2026-07-20', end: '2026-07-24', label: '유연근무 09~18' }],
};

export async function fetchPersonalAttendanceSummary(
  _token: string | null,
): Promise<PersonalAttendanceSummary> {
  return new Promise((resolve) => setTimeout(() => resolve(MOCK_SUMMARY), 120));
}

export type AttendanceRequestKind = 'OVERTIME' | 'LEAVE' | 'HOLIDAY_WORK' | 'FLEX';

// ---------------------------------------------------------------------------
// 야근 신청
// ---------------------------------------------------------------------------

/**
 * 결재 상태. 신청 종류에 따라 거치는 단계가 다르다.
 *
 * 야근·휴가·유연근무: 신청 → 부서장 결재 완료(= APPROVED, 효력 발생)
 *   → 인사담당자 확인(확인 수준이라 상태를 막지 않고 hrCheckedAt 으로만 기록)
 *
 * 특근: 신청 → 부서장 결재 → 부서근태 담당자 → 그룹웨어 결재선(부서마다 다름)
 *   → 승인 후 부서근태 담당자 확정 → 앱/웹 결과처리
 *   PENDING → TIMEKEEPER_REVIEW → GROUPWARE_APPROVAL → APPROVED
 *
 * 대기 건은 아직 결재가 진행된 게 아니므로 취소 시 흔적 없이 삭제한다
 * (→ 'CANCELED' 상태는 두지 않는다).
 */
export type RequestStatus =
  | 'PENDING' // 부서장 결재 대기
  | 'TIMEKEEPER_REVIEW' // 부서장 승인 완료 → 부서근태 담당자 처리중 (특근)
  | 'GROUPWARE_APPROVAL' // 그룹웨어 결재선 진행중 (특근)
  | 'APPROVED' // 승인 완료 (특근은 근태담당자 확정까지 끝난 상태)
  | 'REJECTED';

// ---------------------------------------------------------------------------
// 결재선 — 야근·휴가·특근·유연근무 4종 신청 공통
// ---------------------------------------------------------------------------

/** 결재자 자격. 파트장은 결재선에 쓰지 않는다(인사 데이터에 보유 예정 없음). */
export type ApproverRole = 'DEPT_HEAD' | 'ACTING_DEPT_HEAD';

export interface Approver {
  id: string;
  name: string;
  position: string; // 직위 (부장/차장 등)
  department: string;
  role: ApproverRole;
}

/** 부서장 부재 사유·기간 — 이 기간에만 代부서장이 결재 권한을 대리한다 */
export interface ApprovalDelegation {
  reason: string; // 휴가 / 출장 등
  from: string; // YYYY-MM-DD
  to: string; // YYYY-MM-DD
}

/**
 * 신청자의 결재선. 사용자가 고르지 않고 인사 정보로 자동 결정된다.
 *
 * 원천: 인사담당자 앱(hr 도메인). 현재 hr 도메인은 ERP/그룹웨어 원본 스냅샷
 * (hr_org_snapshot_rows.raw_payload)까지만 보유하고 부서장이 확정 필드로
 * 정규화돼 있지 않다. → 아래 계약대로 hr 쪽에 resolve 엔드포인트 추가 필요.
 *
 * - approver 는 서버가 결정한 "지금 결재할 사람". 대리 기간이 유효하면 delegate, 아니면 deptHead.
 * - delegate 는 부서장이 직접 지정한 代부서장이 있을 때만 내려온다.
 */
export interface ApprovalLine {
  deptHead: Approver;
  delegate?: Approver | null;
  delegation?: ApprovalDelegation | null;
  approver: Approver;
}

/**
 * 야근 산정 정책.
 * ⚠ regularEnd 외 수치는 두원공조 취업규칙 확인 필요 — 아래 값은 UI 검증용 임시값.
 * weeklyLimitMinutes(주 12시간)만 근로기준법 제53조 법정 한도.
 */
export interface OvertimePolicy {
  regularEnd: string; // 정규 근무 종료 — 이 시각 이후만 야근으로 인정
  dinnerBreakMinutes: number; // 식사함 → 근무시간 미반영(공제) / 식사 안함 → 업무시간 반영
  unitMinutes: number; // 인정 단위(내림)
  minMinutes: number; // 최소 인정 시간 — 미만이면 신청 불가
  weeklyLimitMinutes: number; // 주 연장근로 법정 한도 (근로기준법 제53조: 12시간)
}

export interface OvertimeRequest {
  id: string;
  workDate: string; // YYYY-MM-DD
  startTime: string; // HH:mm
  endTime: string; // HH:mm (익일이면 자정 넘김으로 계산)
  hasDinner: boolean; // 저녁 식사 예정 여부 — 예정이면 휴게 공제
  minutes: number; // 휴게 공제 후 인정 예정 분
  reason: string;
  approverId: string;
  approverName: string;
  approverRole: ApproverRole; // 상신 시점 기준 (代부서장 결재였는지 이력 보존)
  status: RequestStatus;
  requestedAt: string; // ISO
  decidedAt?: string | null; // 부서장 결재 시각 (= 효력 발생)
  /** 인사담당자 확인 시각. 확인 수준이라 결재를 막지 않고 기록만 한다 */
  hrCheckedAt?: string | null;
  rejectReason?: string | null;
}

/**
 * 결재자는 서버가 결재선에서 결정하므로 입력에 포함하지 않는다.
 * workDates 로 여러 날짜를 한 번에 상신한다(날짜당 1건 생성).
 */
export interface OvertimeCreateInput {
  workDates: string[];
  startTime: string;
  endTime: string;
  hasDinner: boolean;
  reason: string;
}

export const OVERTIME_POLICY: OvertimePolicy = {
  regularEnd: '17:00',
  dinnerBreakMinutes: 30,
  unitMinutes: 30,
  minMinutes: 60,
  weeklyLimitMinutes: 12 * 60,
};

/** 신청 시각 범위 + 저녁 식사 여부 → 실제 인정될 야근 분 */
export function calcOvertimeMinutes(
  startTime: string,
  endTime: string,
  hasDinner: boolean,
  policy: OvertimePolicy = OVERTIME_POLICY,
): number {
  const mins = (hhmm: string) => {
    const [h, m] = hhmm.split(':').map(Number);
    return h * 60 + m;
  };
  const start = Math.max(mins(startTime), mins(policy.regularEnd)); // 정규 종료 이전 구간은 미인정
  const rawEnd = mins(endTime);
  const end = rawEnd >= start ? rawEnd : rawEnd + 1440; // 자정 넘김
  let total = end - start;
  if (total <= 0) return 0;
  if (hasDinner) total -= policy.dinnerBreakMinutes;
  return Math.max(0, Math.floor(total / policy.unitMinutes) * policy.unitMinutes);
}

// 인사 원천 데이터 대체 Mock — 부서장 1인 + 부재 기간 동안의 代부서장
const MOCK_DEPT_HEAD: Approver = {
  id: 'u-8801',
  name: '김도현',
  position: '부장',
  department: '공조설계1팀',
  role: 'DEPT_HEAD',
};
const MOCK_DELEGATE: Approver = {
  id: 'u-8842',
  name: '정하늘',
  position: '차장',
  department: '공조설계1팀',
  role: 'ACTING_DEPT_HEAD',
};
const MOCK_DELEGATION: ApprovalDelegation = { reason: '출장', from: '2026-07-27', to: '2026-07-29' };

export async function fetchApprovalLine(_token: string | null): Promise<ApprovalLine> {
  const today = new Date().toISOString().slice(0, 10);
  const active = today >= MOCK_DELEGATION.from && today <= MOCK_DELEGATION.to;
  const line: ApprovalLine = {
    deptHead: MOCK_DEPT_HEAD,
    delegate: MOCK_DELEGATE,
    delegation: MOCK_DELEGATION,
    approver: active ? MOCK_DELEGATE : MOCK_DEPT_HEAD,
  };
  return new Promise((r) => setTimeout(() => r(line), 80));
}

let MOCK_OVERTIME: OvertimeRequest[] = [
  // 7/23 — 두 번 반려 후 재신청해 승인된 이력 (같은 날짜에 여러 건이 쌓이는 경우)
  {
    id: 'ot-1004',
    workDate: '2026-07-23',
    startTime: '17:00',
    endTime: '22:00',
    hasDinner: true,
    minutes: 270,
    reason: 'DVP 일정 대응',
    approverId: MOCK_DEPT_HEAD.id,
    approverName: MOCK_DEPT_HEAD.name,
    approverRole: 'DEPT_HEAD',
    status: 'REJECTED',
    requestedAt: iso('2026-07-23', '09:20'),
    decidedAt: iso('2026-07-23', '10:05'),
    rejectReason: '사유가 구체적이지 않음 — 작업 항목을 명시할 것',
  },
  {
    id: 'ot-1005',
    workDate: '2026-07-23',
    startTime: '17:00',
    endTime: '22:00',
    hasDinner: true,
    minutes: 270,
    reason: 'EV 열관리 시스템 DVP 시험 데이터 정리 및 보고서 초안',
    approverId: MOCK_DEPT_HEAD.id,
    approverName: MOCK_DEPT_HEAD.name,
    approverRole: 'DEPT_HEAD',
    status: 'REJECTED',
    requestedAt: iso('2026-07-23', '11:30'),
    decidedAt: iso('2026-07-23', '12:10'),
    rejectReason: '종료시간 과다 — 22시 이전으로 조정 후 재신청',
  },
  {
    id: 'ot-1003',
    workDate: '2026-07-23',
    startTime: '17:00',
    endTime: '20:30',
    hasDinner: true,
    minutes: 180,
    reason: 'EV 열관리 시스템 DVP 일정 대응 — 시험 데이터 정리',
    approverId: MOCK_DEPT_HEAD.id,
    approverName: MOCK_DEPT_HEAD.name,
    approverRole: 'DEPT_HEAD',
    status: 'APPROVED',
    requestedAt: iso('2026-07-23', '14:10'),
    decidedAt: iso('2026-07-23', '15:02'),
    hrCheckedAt: iso('2026-07-24', '09:30'),
  },
  {
    id: 'ot-1002',
    workDate: '2026-07-17',
    startTime: '17:00',
    endTime: '19:00',
    hasDinner: false,
    minutes: 120,
    reason: '고객사 도면 회신 마감',
    approverId: MOCK_DEPT_HEAD.id,
    approverName: MOCK_DEPT_HEAD.name,
    approverRole: 'DEPT_HEAD',
    status: 'APPROVED',
    requestedAt: iso('2026-07-17', '11:40'),
    decidedAt: iso('2026-07-17', '13:20'),
    hrCheckedAt: iso('2026-07-20', '10:05'),
  },
  {
    id: 'ot-1001',
    workDate: '2026-07-09',
    startTime: '17:00',
    endTime: '18:30',
    hasDinner: false,
    minutes: 90,
    reason: '설비 이슈 대응',
    approverId: MOCK_DEPT_HEAD.id,
    approverName: MOCK_DEPT_HEAD.name,
    approverRole: 'DEPT_HEAD',
    status: 'REJECTED',
    requestedAt: iso('2026-07-09', '16:05'),
    decidedAt: iso('2026-07-09', '16:44'),
    rejectReason: '해당 건은 정규 시간 내 처리 가능하다고 판단됨',
  },
];

let overtimeSeq = 1006;

export async function fetchOvertimeRequests(_token: string | null): Promise<OvertimeRequest[]> {
  return new Promise((r) => setTimeout(() => r([...MOCK_OVERTIME]), 120));
}

/** 날짜당 1건씩 생성해 상신 결과를 돌려준다 (최신 날짜가 앞) */
export async function createOvertimeRequests(
  token: string | null,
  input: OvertimeCreateInput,
): Promise<OvertimeRequest[]> {
  // 결재자는 클라이언트 입력이 아니라 프로토타입 결재선에서 확정한다.
  const { approver } = await fetchApprovalLine(token);
  const minutes = calcOvertimeMinutes(input.startTime, input.endTime, input.hasDinner);
  const requestedAt = new Date().toISOString();
  const created: OvertimeRequest[] = input.workDates.map((workDate) => ({
    id: `ot-${overtimeSeq++}`,
    workDate,
    startTime: input.startTime,
    endTime: input.endTime,
    hasDinner: input.hasDinner,
    minutes,
    reason: input.reason,
    approverId: approver.id,
    approverName: approver.name,
    approverRole: approver.role,
    status: 'PENDING',
    requestedAt,
    decidedAt: null,
  }));
  const newest = [...created].sort((a, b) => b.workDate.localeCompare(a.workDate));
  MOCK_OVERTIME = [...newest, ...MOCK_OVERTIME];
  return new Promise((r) => setTimeout(() => r(newest), 200));
}

/** 결재 대기 건 철회 — 이력을 남기지 않고 삭제한다 */
export async function deleteOvertimeRequest(_token: string | null, id: string): Promise<void> {
  MOCK_OVERTIME = MOCK_OVERTIME.filter((r) => r.id !== id);
  return new Promise((r) => setTimeout(() => r(), 150));
}

// ---------------------------------------------------------------------------
// 휴가 신청
// ---------------------------------------------------------------------------

/** 반차·시간 휴가의 시간대 지정 */
export type HalfDay = 'AM' | 'PM';

/** 향후 신청 API가 소유할 첨부 계약. 현재 프로토타입에서는 업로드하지 않는다. */
export interface RequestAttachment {
  url: string;
  name: string;
  size: number;
  contentType: string;
}

/** 신청 1건 = 근태코드 + 기간(또는 하루 + 시간대) */
export interface AttendanceRequest {
  id: string;
  code: number; // 근태코드 (commute_attendance_codes.code)
  startDate: string; // YYYY-MM-DD
  endDate: string; // YYYY-MM-DD (하루면 startDate 와 동일)
  halfDay?: HalfDay | null; // 반차 코드일 때
  startTime?: string | null; // 시간 휴가 시작 시각 "HH:mm"
  hours?: number | null; // 시간 휴가 사용 시간
  days: number; // 잔여 차감 환산 일수
  reason: string;
  attachments: RequestAttachment[];
  approverId: string;
  approverName: string;
  approverRole: ApproverRole;
  status: RequestStatus;
  requestedAt: string;
  decidedAt?: string | null; // 부서장 결재 시각 (= 효력 발생)
  /** 인사담당자 확인 시각. 확인 수준이라 결재를 막지 않고 기록만 한다 */
  hrCheckedAt?: string | null;
  rejectReason?: string | null;
}

export interface AttendanceRequestCreateInput {
  code: number;
  startDate: string;
  endDate: string;
  halfDay?: HalfDay | null;
  startTime?: string | null;
  hours?: number | null;
  reason: string;
  attachments: RequestAttachment[];
}

let MOCK_ATTENDANCE_REQ: AttendanceRequest[] = [
  {
    id: 'ar-2005',
    code: 4, // 해외출장
    startDate: '2026-09-07',
    endDate: '2026-09-11',
    halfDay: null,
    startTime: null,
    hours: null,
    days: 5,
    reason: '중국 광저우 고객사 열관리 모듈 품질 이슈 대응',
    attachments: [],
    approverId: MOCK_DEPT_HEAD.id,
    approverName: MOCK_DEPT_HEAD.name,
    approverRole: 'DEPT_HEAD',
    status: 'PENDING',
    requestedAt: iso('2026-07-26', '17:05'),
    decidedAt: null,
  },
  {
    id: 'ar-2004',
    code: 15, // 예비군훈련
    startDate: '2026-07-21',
    endDate: '2026-07-21',
    halfDay: null,
    startTime: null,
    hours: null,
    days: 1,
    reason: '동원훈련 소집 — 소집통지서 제출 예정',
    attachments: [],
    approverId: MOCK_DEPT_HEAD.id,
    approverName: MOCK_DEPT_HEAD.name,
    approverRole: 'DEPT_HEAD',
    status: 'APPROVED',
    requestedAt: iso('2026-07-13', '08:40'),
    decidedAt: iso('2026-07-13', '09:20'),
  },
  {
    id: 'ar-2003',
    code: 7,
    startDate: '2026-08-10',
    endDate: '2026-08-12',
    halfDay: null,
    days: 3,
    reason: '가족 여행',
    attachments: [],
    approverId: MOCK_DEPT_HEAD.id,
    approverName: MOCK_DEPT_HEAD.name,
    approverRole: 'DEPT_HEAD',
    status: 'PENDING',
    requestedAt: iso('2026-07-25', '09:12'),
    decidedAt: null,
  },
  {
    id: 'ar-2002',
    code: 7,
    startDate: '2026-07-14',
    endDate: '2026-07-14',
    halfDay: null,
    days: 1,
    reason: '',
    attachments: [],
    approverId: MOCK_DEPT_HEAD.id,
    approverName: MOCK_DEPT_HEAD.name,
    approverRole: 'DEPT_HEAD',
    status: 'APPROVED',
    requestedAt: iso('2026-07-08', '13:40'),
    decidedAt: iso('2026-07-08', '15:11'),
  },
  {
    id: 'ar-2001',
    code: 6,
    startDate: '2026-07-10',
    endDate: '2026-07-10',
    halfDay: null,
    days: 1,
    reason: '',
    attachments: [],
    approverId: MOCK_DEPT_HEAD.id,
    approverName: MOCK_DEPT_HEAD.name,
    approverRole: 'DEPT_HEAD',
    status: 'APPROVED',
    requestedAt: iso('2026-07-06', '10:02'),
    decidedAt: iso('2026-07-06', '11:30'),
  },
  {
    id: 'ar-2000',
    code: 19,
    startDate: '2026-06-20',
    endDate: '2026-06-20',
    halfDay: 'PM',
    days: 0.5,
    reason: '병원 진료',
    attachments: [],
    approverId: MOCK_DEPT_HEAD.id,
    approverName: MOCK_DEPT_HEAD.name,
    approverRole: 'DEPT_HEAD',
    status: 'REJECTED',
    requestedAt: iso('2026-06-18', '16:22'),
    decidedAt: iso('2026-06-19', '09:05'),
    rejectReason: '해당일 고객 감사 일정 — 일정 조정 후 재신청 요망',
  },
];

let attendanceReqSeq = 2006;

export async function fetchAttendanceRequests(
  _token: string | null,
): Promise<AttendanceRequest[]> {
  return new Promise((r) => setTimeout(() => r([...MOCK_ATTENDANCE_REQ]), 120));
}

export async function createAttendanceRequest(
  token: string | null,
  input: AttendanceRequestCreateInput,
  days: number,
): Promise<AttendanceRequest> {
  const { approver } = await fetchApprovalLine(token);
  const created: AttendanceRequest = {
    id: `ar-${attendanceReqSeq++}`,
    code: input.code,
    startDate: input.startDate,
    endDate: input.endDate,
    halfDay: input.halfDay ?? null,
    startTime: input.startTime ?? null,
    hours: input.hours ?? null,
    days,
    reason: input.reason,
    attachments: input.attachments,
    approverId: approver.id,
    approverName: approver.name,
    approverRole: approver.role,
    status: 'PENDING',
    requestedAt: new Date().toISOString(),
    decidedAt: null,
  };
  MOCK_ATTENDANCE_REQ = [created, ...MOCK_ATTENDANCE_REQ];
  return new Promise((r) => setTimeout(() => r(created), 200));
}

/** 결재 대기 건 철회 — 야근과 동일하게 흔적 없이 삭제 */
export async function deleteAttendanceRequest(_token: string | null, id: string): Promise<void> {
  MOCK_ATTENDANCE_REQ = MOCK_ATTENDANCE_REQ.filter((r) => r.id !== id);
  return new Promise((r) => setTimeout(() => r(), 150));
}

// ---------------------------------------------------------------------------
// 특근 신청 (휴일근로)
// ---------------------------------------------------------------------------

/** 보상 방식 — 수당 또는 대체휴가(근로기준법 제57조 보상휴가제) */
export type HolidayWorkCompensation = 'ALLOWANCE' | 'COMP_LEAVE';

/**
 * 특근(휴일근로) 산정 정책.
 * premium* 은 근로기준법 제56조 제2항 법정 가산율이라 확정값이다.
 * ⚠ 나머지(휴게 기본값·인정 단위·최소 시간·대체휴가 환산 기준)는 두원공조 취업규칙 확인 필요.
 */
export interface HolidayWorkPolicy {
  premiumWithin8hPercent: number; // 8시간 이내 가산 50%
  premiumOver8hPercent: number; // 8시간 초과 가산 100%
  regularDayMinutes: number; // 가산율이 바뀌는 기준 (8시간)
  unitMinutes: number; // 인정 단위(내림)
  minMinutes: number; // 최소 인정 시간
  hoursPerDay: number; // 대체휴가 일수 환산 기준
  weeklyReferenceMinutes: number; // 주 연장·휴일근로 참고 한도
}

export const HOLIDAY_WORK_POLICY: HolidayWorkPolicy = {
  premiumWithin8hPercent: 50,
  premiumOver8hPercent: 100,
  regularDayMinutes: 8 * 60,
  unitMinutes: 30,
  minMinutes: 60,
  hoursPerDay: 8,
  weeklyReferenceMinutes: 12 * 60,
};

/** 실근로 인정 분 — 휴게 공제 후 단위 내림 */
export function calcHolidayWorkMinutes(
  startTime: string,
  endTime: string,
  breakMinutes: number,
  policy: HolidayWorkPolicy = HOLIDAY_WORK_POLICY,
): number {
  const mins = (hhmm: string) => {
    const [h, m] = hhmm.split(':').map(Number);
    return h * 60 + m;
  };
  const start = mins(startTime);
  const rawEnd = mins(endTime);
  const end = rawEnd >= start ? rawEnd : rawEnd + 1440; // 자정 넘김
  const total = end - start - breakMinutes;
  if (total <= 0) return 0;
  return Math.floor(total / policy.unitMinutes) * policy.unitMinutes;
}

/** 가산 포함 환산 분 (수당·대체휴가 산정 기준) */
export function calcHolidayPremiumMinutes(
  workedMinutes: number,
  policy: HolidayWorkPolicy = HOLIDAY_WORK_POLICY,
): number {
  const within = Math.min(workedMinutes, policy.regularDayMinutes);
  const over = Math.max(0, workedMinutes - policy.regularDayMinutes);
  return Math.round(
    within * (1 + policy.premiumWithin8hPercent / 100) +
      over * (1 + policy.premiumOver8hPercent / 100),
  );
}

/** 대체휴가로 받을 때 발생 예상 일수 */
export function calcCompLeaveDays(
  premiumMinutes: number,
  policy: HolidayWorkPolicy = HOLIDAY_WORK_POLICY,
): number {
  return Math.round((premiumMinutes / (policy.hoursPerDay * 60)) * 100) / 100;
}

export interface HolidayWorkRequest {
  id: string;
  workDate: string; // YYYY-MM-DD
  startTime: string; // HH:mm
  endTime: string; // HH:mm
  breakMinutes: number;
  minutes: number; // 실근로 인정 분
  premiumMinutes: number; // 가산 포함 환산 분
  compensation: HolidayWorkCompensation;
  compLeaveDays: number | null; // 대체휴가 선택 시 발생 예상 일수
  reason: string;
  approverId: string;
  approverName: string;
  approverRole: ApproverRole;
  status: RequestStatus;
  requestedAt: string;
  /** 부서장 승인 시각 — 이 시점부터 부서 근태담당자가 그룹웨어로 결재를 올린다 */
  deptApprovedAt?: string | null;
  /** 그룹웨어 결재 문서번호 — 근태담당자가 상신하면 채워진다 (연동 후) */
  groupwareDocNo?: string | null;
  decidedAt?: string | null; // 최종 확정 시각
  rejectReason?: string | null;
}

/** 야근과 동일하게 날짜당 1건 생성 */
export interface HolidayWorkCreateInput {
  workDates: string[];
  startTime: string;
  endTime: string;
  breakMinutes: number;
  compensation: HolidayWorkCompensation;
  reason: string;
}

function mockHolidayWork(
  id: string,
  workDate: string,
  startTime: string,
  endTime: string,
  breakMinutes: number,
  compensation: HolidayWorkCompensation,
  reason: string,
  status: RequestStatus,
  requestedAt: string,
  decidedAt: string | null,
  rejectReason?: string,
  deptApprovedAt?: string | null,
  groupwareDocNo?: string | null,
): HolidayWorkRequest {
  const minutes = calcHolidayWorkMinutes(startTime, endTime, breakMinutes);
  const premiumMinutes = calcHolidayPremiumMinutes(minutes);
  return {
    id,
    workDate,
    startTime,
    endTime,
    breakMinutes,
    minutes,
    premiumMinutes,
    compensation,
    compLeaveDays: compensation === 'COMP_LEAVE' ? calcCompLeaveDays(premiumMinutes) : null,
    reason,
    approverId: MOCK_DEPT_HEAD.id,
    approverName: MOCK_DEPT_HEAD.name,
    approverRole: 'DEPT_HEAD',
    status,
    requestedAt,
    deptApprovedAt: deptApprovedAt ?? null,
    groupwareDocNo: groupwareDocNo ?? null,
    decidedAt,
    rejectReason: rejectReason ?? null,
  };
}

let MOCK_HOLIDAY_WORK: HolidayWorkRequest[] = [
  mockHolidayWork(
    'hw-3002',
    '2026-07-26', // 일요일
    '08:00',
    '12:00',
    0,
    'ALLOWANCE',
    '고객 감사 대응 — 시험 설비 예약 일정',
    'PENDING',
    iso('2026-07-24', '15:20'),
    null,
  ),
  // 부서장 승인은 났고, 부서 근태담당자가 그룹웨어 결재를 올려 확정하기 전 단계
  mockHolidayWork(
    'hw-3001',
    '2026-07-18', // 토요일
    '08:00',
    '17:00',
    60,
    'ALLOWANCE',
    '양산 라인 이관 대응',
    'TIMEKEEPER_REVIEW',
    iso('2026-07-16', '10:05'),
    null,
    undefined,
    iso('2026-07-16', '11:40'),
  ),
  // 근태담당자가 그룹웨어에 상신해 결재선이 도는 중 (결재선은 부서마다 다름)
  mockHolidayWork(
    'hw-3000b',
    '2026-07-11', // 토요일
    '08:00',
    '14:00',
    30,
    'COMP_LEAVE',
    '고객 요청 시험 대응',
    'GROUPWARE_APPROVAL',
    iso('2026-07-09', '16:40'),
    null,
    undefined,
    iso('2026-07-10', '09:15'),
    'GW-2026-07-0412',
  ),
  // 그룹웨어 승인 후 근태담당자가 확정까지 마친 건
  mockHolidayWork(
    'hw-3000',
    '2026-07-04', // 토요일
    '09:00',
    '15:00',
    60,
    'COMP_LEAVE',
    '설비 정기 점검 입회',
    'APPROVED',
    iso('2026-07-02', '09:30'),
    iso('2026-07-06', '10:20'),
    undefined,
    iso('2026-07-02', '13:12'),
    'GW-2026-07-0155',
  ),
];

let holidayWorkSeq = 3003;

export async function fetchHolidayWorkRequests(
  _token: string | null,
): Promise<HolidayWorkRequest[]> {
  return new Promise((r) => setTimeout(() => r([...MOCK_HOLIDAY_WORK]), 120));
}

export async function createHolidayWorkRequests(
  token: string | null,
  input: HolidayWorkCreateInput,
): Promise<HolidayWorkRequest[]> {
  const { approver } = await fetchApprovalLine(token);
  const requestedAt = new Date().toISOString();
  const minutes = calcHolidayWorkMinutes(input.startTime, input.endTime, input.breakMinutes);
  const premiumMinutes = calcHolidayPremiumMinutes(minutes);
  const created: HolidayWorkRequest[] = input.workDates.map((workDate) => ({
    id: `hw-${holidayWorkSeq++}`,
    workDate,
    startTime: input.startTime,
    endTime: input.endTime,
    breakMinutes: input.breakMinutes,
    minutes,
    premiumMinutes,
    compensation: input.compensation,
    compLeaveDays:
      input.compensation === 'COMP_LEAVE' ? calcCompLeaveDays(premiumMinutes) : null,
    reason: input.reason,
    approverId: approver.id,
    approverName: approver.name,
    approverRole: approver.role,
    status: 'PENDING',
    requestedAt,
    decidedAt: null,
  }));
  const newest = [...created].sort((a, b) => b.workDate.localeCompare(a.workDate));
  MOCK_HOLIDAY_WORK = [...newest, ...MOCK_HOLIDAY_WORK];
  return new Promise((r) => setTimeout(() => r(newest), 200));
}

export async function deleteHolidayWorkRequest(
  _token: string | null,
  id: string,
): Promise<void> {
  MOCK_HOLIDAY_WORK = MOCK_HOLIDAY_WORK.filter((r) => r.id !== id);
  return new Promise((r) => setTimeout(() => r(), 150));
}
