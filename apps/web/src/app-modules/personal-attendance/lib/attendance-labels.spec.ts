import { describe, expect, it } from 'vitest';

import { i18n } from '@/src/platform/i18n/i18n';

import { ATTENDANCE_CODES, findCode } from './attendance-codes';
import { createAttendanceLabels } from './attendance-labels';

/**
 * 근태 화면 문구는 전부 i18n 리소스가 소유한다.
 * 여기서는 실제 리소스로 팩토리를 돌려 키 누락(= 키 문자열이 그대로 노출되는 상태)을 막는다.
 */
async function labelsFor(locale: 'ko-KR' | 'en-US') {
  await i18n.changeLanguage(locale);
  return createAttendanceLabels(i18n.t);
}

describe('createAttendanceLabels', () => {
  it('ko-KR 근태 상태·휴가 종류·결재 상태를 문구로 해석한다', async () => {
    const labels = await labelsFor('ko-KR');

    expect(labels.status('NORMAL')).toBe('정상');
    expect(labels.status('MISSING')).toBe('결근');
    expect(labels.leaveType('ANNUAL')).toBe('연차');
    expect(labels.requestStatus('TIMEKEEPER_REVIEW')).toBe('부서근태 담당자 처리중');
    expect(labels.stage('APPROVED')).toBe('확정');
    expect(labels.category('TRIP')).toBe('출장');
    expect(labels.holidayWork).toBe('특근');
  });

  it('en-US 로도 같은 키가 모두 해석된다', async () => {
    const labels = await labelsFor('en-US');

    expect(labels.status('NORMAL')).toBe('Normal');
    expect(labels.leaveType('ANNUAL')).toBe('Annual');
    expect(labels.requestStatus('APPROVED')).toBe('Approved');
    expect(labels.category('LEAVE')).toBe('Leave');
  });

  it('근태 코드 30개 전부 이름을 갖는다 (시간 코드는 시간 수로 구분)', async () => {
    const labels = await labelsFor('ko-KR');

    for (const code of ATTENDANCE_CODES) {
      const name = labels.code(code);
      expect(name).not.toContain('personalAttendance');
      expect(name.length).toBeGreaterThan(0);
    }
    expect(labels.code(findCode(7))).toBe('연차');
    expect(labels.code(findCode(19))).toBe('반차');
    expect(labels.code(findCode(25))).toBe('1시간');
    expect(labels.code(findCode(30))).toBe('7시간');
    expect(labels.code(undefined)).toBe('알 수 없는 항목');
  });

  it('noteKey 가 있는 코드만 보충 설명을 돌려준다', async () => {
    const labels = await labelsFor('ko-KR');

    expect(labels.codeNote(findCode(11))).toContain('근로기준법 제73조');
    expect(labels.codeNote(findCode(7))).toBeNull();
  });

  it('근무시간을 시간·분 단위로 표기한다', async () => {
    const labels = await labelsFor('ko-KR');

    expect(labels.work(null)).toBe('—');
    expect(labels.work(0)).toBe('0분');
    expect(labels.work(45)).toBe('45분');
    expect(labels.work(480)).toBe('8시간');
    expect(labels.work(510)).toBe('8시간 30분');
  });

  it('휴가 일수는 소수 대신 일 + 시간으로 표기한다', async () => {
    const labels = await labelsFor('ko-KR');

    expect(labels.leaveDays(0)).toBe('0일');
    expect(labels.leaveDays(11)).toBe('11일');
    expect(labels.leaveDays(11.5)).toBe('11일 4시간');
    expect(labels.leaveDays(0.5)).toBe('4시간');
    // 반올림으로 하루가 꽉 차면 다음 일수로 올린다
    expect(labels.leaveDays(1.99)).toBe('2일');
  });

  it('요일·날짜·시각을 로케일 문구로 만든다', async () => {
    const ko = await labelsFor('ko-KR');
    expect(ko.weekdays).toEqual(['일', '월', '화', '수', '목', '금', '토']);
    expect(ko.date('2026-07-30')).toBe('7.30 (목)');
    expect(ko.clock('17:05')).toBe('오후 5:05');
    expect(ko.clock('00:30')).toBe('오전 12:30');

    const en = await labelsFor('en-US');
    expect(en.date('2026-07-30')).toBe('7/30 (Thu)');
    expect(en.clock('17:05')).toBe('5:05 PM');
  });
});
