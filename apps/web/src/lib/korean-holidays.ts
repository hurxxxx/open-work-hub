/**
 * Korean public holiday lookup for the Planner.
 *
 * Backed by `@hyunbinseo/holidays-kr`, which ships per-year datasets sourced
 * from the official Korean gazette (관보) — including lunar holidays, alternative
 * holidays (대체공휴일), temporary holidays (임시공휴일), and election days.
 *
 * The package only contains data for years it has been published with. When
 * a new year's holidays are gazetted, the maintainer publishes a new minor
 * version (e.g. `4.2027.0`) and we need to bump the package — see the upgrade
 * notes in `docs/product/korean-holidays.md`.
 *
 * Synchronous by design so that calendar grids can call it cell-by-cell
 * without `await` or Suspense. New years are added by editing the lookup
 * table at the top of this file once the dependency has been bumped.
 */

import {
  y2018,
  y2019,
  y2020,
  y2021,
  y2022,
  y2023,
  y2024,
  y2025,
  y2026,
} from '@hyunbinseo/holidays-kr';

type HolidayYearMap = Readonly<Record<string, readonly string[]>>;

// When bumping @hyunbinseo/holidays-kr to a new year, import its `yYYYY` export
// above and add the entry here. The rest of the helper picks the year up
// automatically.
const HOLIDAYS_BY_YEAR: Readonly<Record<number, HolidayYearMap>> = {
  2018: y2018,
  2019: y2019,
  2020: y2020,
  2021: y2021,
  2022: y2022,
  2023: y2023,
  2024: y2024,
  2025: y2025,
  2026: y2026,
};

export const KOREAN_HOLIDAY_MIN_YEAR = 2018;
export const KOREAN_HOLIDAY_MAX_YEAR = 2026;

function pad2(value: number): string {
  return value.toString().padStart(2, '0');
}

// Track which years we've already warned about so the dev console isn't
// flooded — every calendar cell calls into this helper.
const warnedYears = new Set<number>();

function warnMissingYear(year: number): void {
  if (warnedYears.has(year)) return;
  warnedYears.add(year);
  console.warn(
    `[korean-holidays] No holiday data for ${year}. The Planner will render ` +
      `this year without holiday markers. Bump @hyunbinseo/holidays-kr and ` +
      `update apps/web/src/lib/korean-holidays.ts — see ` +
      `docs/product/korean-holidays.md.`,
  );
}

/**
 * Returns the holiday names for the given year/month/day, or `null` if the
 * date is not a Korean public holiday (or falls outside the supported range).
 *
 * Logs a one-time console warning the first time it is asked about a year
 * that the bundled dataset does not cover, so a stale package is noticeable
 * during development before users hit the gap.
 */
export function getKoreanHolidayNames(
  year: number,
  month: number,
  day: number,
): readonly string[] | null {
  const yearMap = HOLIDAYS_BY_YEAR[year];
  if (!yearMap) {
    if (year > KOREAN_HOLIDAY_MAX_YEAR || year < KOREAN_HOLIDAY_MIN_YEAR) {
      warnMissingYear(year);
    }
    return null;
  }
  const key = `${year}-${pad2(month + 1)}-${pad2(day)}`;
  return yearMap[key] ?? null;
}

/** True when the supplied date is a Korean public holiday. */
export function isKoreanHoliday(year: number, month: number, day: number): boolean {
  return getKoreanHolidayNames(year, month, day) !== null;
}
