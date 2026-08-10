# 한국 공휴일 데이터 관리

Planner 캘린더는 한국 공식 관보(官報)를 그대로 따르는
[`@hyunbinseo/holidays-kr`](https://github.com/hyunbinseo/holidays-kr) npm 패키지를
이용해 양력·음력·대체공휴일·임시공휴일·선거일을 모두 표시한다.

## 동작 방식

- 패키지는 연도별로 정적 데이터셋(`y2025`, `y2026`, `y2027`, …)을 export 한다.
- 모든 데이터는 빌드 타임에 클라이언트 번들에 포함되므로 외부 API 호출이 없다.
- 헬퍼 모듈: [`apps/web/src/lib/korean-holidays.ts`](../../apps/web/src/lib/korean-holidays.ts)
  - `getKoreanHolidayNames(year, month, day)` — 동기 lookup, 휴일이면 한국어 명칭
    배열을 반환하고 아니면 `null`
  - 지원 연도 범위를 벗어난 lookup 은 개발 콘솔에 1회 warning 을 남긴다.
- 사용처: Planner / PMS 공통 캘린더와 홈 오늘 패널. 휴일은 빨간색으로 강조된다.

## 데이터 신뢰 범위

현재 패키지는 **2018 ~ 2027년** 데이터만 포함한다.
범위를 벗어난 날짜를 lookup 하면 `null`을 돌려준다 (휴일 없음으로 처리).
캘린더 자체는 동작하지만 강조 표시가 사라지므로, 새 연도가 시작되기 전에 반드시
패키지를 업그레이드해야 한다.

## 새 연도 추가 절차

대한민국 정부는 매년 7~8월경 다음 해 공휴일을 관보로 고시하며, 패키지 메인테이너는
관보 고시 직후 새 버전(예: `5.2028.0`)을 npm 에 올린다.

새 연도 데이터를 통합하는 절차:

1. **패키지 업그레이드**

   ```sh
   pnpm add -w @hyunbinseo/holidays-kr@latest
   ```

2. **버전 확인**

   ```sh
   pnpm view @hyunbinseo/holidays-kr version
   ```

   버전 형식에 추가하려는 연도(`YYYY`)가 포함되어 있는지 확인한다.

3. **헬퍼 모듈 업데이트** —
   [`apps/web/src/lib/korean-holidays.ts`](../../apps/web/src/lib/korean-holidays.ts)

   - 새 연도 export 를 import 에 추가:

     ```ts
     import { …, y2028 } from '@hyunbinseo/holidays-kr/all';
     ```

     연도별 export 는 `@hyunbinseo/holidays-kr/all` 하위 경로에서 가져온다.
     기본 export 는 async API 이므로, 동기 lookup 을 유지하려면 `all` export 를
     사용해야 한다.

   - `HOLIDAYS_BY_YEAR` 매핑에 항목 추가:

     ```ts
     const HOLIDAYS_BY_YEAR = {
       …,
       2028: y2028,
     };
     ```

   - `KOREAN_HOLIDAY_MAX_YEAR` 상수를 새 연도로 갱신.

4. **타입 체크 + 빌드**

   ```sh
   pnpm nx run web:typecheck
   pnpm nx run web:build
   ```

5. **임시공휴일 / 대체공휴일 변경 대응**

   임시공휴일(예: 대선일, 명절 사이 끼인 날)이나 대체공휴일 룰 변경이 연중에
   발생할 수 있다. 패키지 메인테이너가 patch 버전을 release 하면 같은 명령으로
   업그레이드만 하면 자동으로 반영된다.

## 패키지 메인테이너가 사라지는 경우

만에 하나 패키지 유지 관리가 중단되면 다음 백업 경로를 고려한다.

1. **공공데이터포털 특일 정보 조회 API**
   (https://www.data.go.kr/data/15012690/openapi.do) — 공식, 무료, 키 발급 필요.
   백엔드에 프록시 + 캐시 레이어를 두면 클라이언트에서 같은 헬퍼 시그니처로
   교체 가능하다.
2. **하드코드 fallback** — 헬퍼 모듈 안에서 `HOLIDAYS_BY_YEAR` 를 자체 JSON 으로
   교체. `getKoreanHolidayNames` 시그니처는 그대로 유지하면 사용처를 건드릴 필요
   없다.
