import { describe, expect, it } from 'vitest';
import {
  datePlaceholderForFormat,
  dateTimePlaceholderForFormat,
  formatDateInputText,
  formatDateTimeInputText,
  normalizeDateInputText,
  normalizeDateTimeInputText,
  normalizeDateTimeValue,
  normalizeDateValue,
} from './date-input-model';

describe('date-input-model', () => {
  it('normalizes compact and year-first date text to ISO dates', () => {
    expect(normalizeDateInputText('20260526', 'korean', 'ko-KR')).toBe('2026-05-26');
    expect(normalizeDateInputText('2026년 5월 26일', 'korean', 'ko-KR')).toBe(
      '2026-05-26',
    );
    expect(normalizeDateInputText('2026. 5. 26.', 'korean', 'ko-KR')).toBe(
      '2026-05-26',
    );
  });

  it('normalizes slash dates using selected format and locale preference', () => {
    expect(normalizeDateInputText('05/26/2026', 'us', 'en-US')).toBe('2026-05-26');
    expect(normalizeDateInputText('26/05/2026', 'european', 'en-GB')).toBe(
      '2026-05-26',
    );
    expect(normalizeDateInputText('05/06/2026', 'locale', 'en-US')).toBe(
      '2026-05-06',
    );
    expect(normalizeDateInputText('05/06/2026', 'locale', 'ko-KR')).toBe(
      '2026-06-05',
    );
  });

  it('rejects impossible dates and invalid time text', () => {
    expect(normalizeDateInputText('2026-02-30', 'iso', 'en-US')).toBeNull();
    expect(normalizeDateTimeInputText('2026-05-26 24:00', 'iso', 'en-US')).toBeNull();
    expect(normalizeDateTimeInputText('2026-05-26 09:60', 'iso', 'en-US')).toBeNull();
  });

  it('commits empty text as a clearing value', () => {
    expect(normalizeDateInputText('  ', 'korean', 'ko-KR')).toBe('');
    expect(normalizeDateTimeInputText('  ', 'korean', 'ko-KR')).toBe('');
  });

  it('normalizes date-time text and native values', () => {
    expect(normalizeDateTimeInputText('2026. 5. 26. 9:05', 'korean', 'ko-KR')).toBe(
      '2026-05-26T09:05',
    );
    expect(normalizeDateValue('2026-05-26')).toBe('2026-05-26');
    expect(normalizeDateValue('2026-5-26')).toBe('');
    expect(normalizeDateTimeValue('2026-05-26T09:05')).toBe('2026-05-26T09:05');
    expect(normalizeDateTimeValue('2026-05-26 09:05')).toBe('');
  });

  it('formats display text and placeholders', () => {
    expect(formatDateInputText('2026-05-26', 'iso', 'en-US')).toBe('2026-05-26');
    expect(formatDateTimeInputText('2026-05-26T09:05', 'iso', 'en-US')).toBe(
      '2026-05-26 09:05',
    );
    expect(datePlaceholderForFormat('locale', 'en-US')).toBe('MM/DD/YYYY');
    expect(datePlaceholderForFormat('locale', 'ko-KR')).toBe('YYYY. M. D.');
    expect(dateTimePlaceholderForFormat('european', 'en-GB')).toBe('DD/MM/YYYY HH:mm');
  });
});
