# Korean Holidays

Planner/PMS/Home use `@hyunbinseo/holidays-kr` static data. No runtime external API call.

## Contract

- Helper: `apps/web/src/lib/korean-holidays.ts`.
- Function: `getKoreanHolidayNames(year, month, day)`.
- Return holiday names or `null`.
- Supported data range currently: 2018-2027.
- Out-of-range lookup returns `null` and logs one dev warning.
- Holidays render red in calendars.

## Update Year

Government announces next-year holidays around July/August. Package versions include the year, e.g. `5.2028.0`.

```bash
pnpm add -w @hyunbinseo/holidays-kr@latest
pnpm view @hyunbinseo/holidays-kr version
```

Then update:

- import new `yYYYY` from `@hyunbinseo/holidays-kr/all`
- `HOLIDAYS_BY_YEAR`
- `KOREAN_HOLIDAY_MAX_YEAR`

Validate:

```bash
pnpm nx run web:typecheck
pnpm nx run web:build
```

Patch releases for temporary/substitute holiday changes follow the same upgrade path.

Fallback if package is abandoned: backend proxy/cache for public holiday API, or local JSON while preserving helper signature.
