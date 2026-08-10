import { describe, expect, it } from 'vitest';

import {
  canonicalUnit,
  computeAmount,
  enforceUnit,
  joinQty,
  normalizeQtyNumber,
  normUnit,
  parseNumber,
  parseQtyNumber,
  splitQty,
  UNIT_OPTIONS,
} from './meal-invoice-ocr-quantity';

describe('meal-invoice-ocr quantity parsing', () => {
  it('splits "숫자 단위" quantities without unit-digit bleed', () => {
    expect(splitQty('2 10k')).toEqual({ num: '2', unit: '10k' });
    expect(splitQty('418 10kg')).toEqual({ num: '418', unit: '10k' });
    // 구버전(공백 없음)은 앞 숫자/뒤 단위로 폴백 분리.
    expect(splitQty('418kg')).toEqual({ num: '418', unit: 'k' });
  });

  it('parses only the numeric part of a quantity (regression: not 210)', () => {
    expect(parseQtyNumber('2 10k')).toBe(2);
    expect(parseQtyNumber('418 10kg')).toBe(418);
    expect(parseQtyNumber('12통')).toBe(12);
    expect(parseQtyNumber('')).toBeNull();
  });

  it('computes amount from qty×price using the numeric part only', () => {
    // 단위 "10k"의 10 이 수량 2 에 붙어 210×3000=630000 이 되면 안 된다.
    expect(computeAmount('2 10k', '3000')).toBe(6000);
    expect(computeAmount('10 k', '1,000')).toBe(10000);
    expect(computeAmount('', '3000')).toBeNull();
    expect(computeAmount('2 10k', '')).toBeNull();
  });

  it('normalizeQtyNumber drops trailing .0 for whole numbers, keeps real decimals', () => {
    expect(normalizeQtyNumber('8.0')).toBe('8');
    expect(normalizeQtyNumber('74.00')).toBe('74');
    expect(normalizeQtyNumber('8')).toBe('8');
    expect(normalizeQtyNumber('8.5')).toBe('8.5');
    expect(normalizeQtyNumber('0.50')).toBe('0.5');
    // 숫자로 못 읽는 값·불확실 표기는 원문 유지.
    expect(normalizeQtyNumber('3?')).toBe('3?');
    expect(normalizeQtyNumber('')).toBe('');
  });

  it('normalizeQtyNumber preserves integers larger than Number.MAX_SAFE_INTEGER', () => {
    expect(normalizeQtyNumber('9007199254740993')).toBe('9007199254740993');
    expect(normalizeQtyNumber('9,007,199,254,740,993.00')).toBe(
      '9007199254740993',
    );
  });

  it('normUnit unifies kg to k, joinQty round-trips', () => {
    expect(normUnit('10kg')).toBe('10k');
    expect(joinQty('2', '10k')).toBe('2 10k');
    expect(joinQty('2', '')).toBe('2');
  });

  it('parseNumber strips commas and non-digits', () => {
    expect(parseNumber('3,500?')).toBe(3500);
    expect(parseNumber('-')).toBeNull();
  });

  it('canonicalUnit maps aliases to the fixed option set', () => {
    // 사용자 지정: kg→k, box→박스, 팩→pac.
    expect(canonicalUnit('kg')).toBe('k');
    expect(canonicalUnit('KG')).toBe('k');
    expect(canonicalUnit('Box')).toBe('박스');
    expect(canonicalUnit('box')).toBe('박스');
    expect(canonicalUnit('팩')).toBe('pac');
    expect(canonicalUnit('pack')).toBe('pac');
    // 뜻이 같은 다른 표기들.
    expect(canonicalUnit('박')).toBe('박스');
    expect(canonicalUnit('상자')).toBe('박스');
    expect(canonicalUnit('낱')).toBe('ea');
    expect(canonicalUnit('개')).toBe('ea');
    // 뜻이 다른 정상 단위는 특정 거래처 사례에 맞춰 강제 변환하지 않는다.
    expect(canonicalUnit('송')).toBe('송');
    expect(canonicalUnit('송이')).toBe('송이');
    // 이미 정규 단위면 그대로.
    for (const u of UNIT_OPTIONS) expect(canonicalUnit(u)).toBe(u);
    // 정규 목록·별칭에 없으면 정규화만 한 원문 유지(값 손실 방지).
    expect(canonicalUnit('봉')).toBe('봉');
    expect(canonicalUnit('')).toBe('');
    // 정규 목록 자체가 사용자 지정 순서·구성인지 확인(회귀 방지).
    expect(UNIT_OPTIONS).toEqual([
      'ea',
      'k',
      '박스',
      'pk',
      'pac',
      '통',
      '10k',
      '판',
      '단',
      '병',
    ]);
  });

  it('enforceUnit constrains to the 10 allowed units and blanks the rest', () => {
    // 허용 10개는 그대로, 별칭은 정규 단위로.
    for (const u of UNIT_OPTIONS) expect(enforceUnit(u)).toBe(u);
    expect(enforceUnit('kg')).toBe('k');
    expect(enforceUnit('box')).toBe('박스');
    expect(enforceUnit('개')).toBe('ea');
    expect(enforceUnit('동')).toBe('통'); // 흔한 손글씨 오독 흡수
    // 목록·별칭에 없으면(오독 'c' 또는 비허용 정상 단위 봉·포·g) 빈칸으로 강제(사용자 계약).
    expect(enforceUnit('c')).toBe('');
    expect(enforceUnit('봉')).toBe('');
    expect(enforceUnit('포')).toBe('');
    expect(enforceUnit('g')).toBe('');
    expect(enforceUnit('')).toBe('');
  });
});
