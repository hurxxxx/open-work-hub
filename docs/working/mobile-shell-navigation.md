# Mobile Shell Navigation

Last updated: 2026-05-02

이 문서는 모바일 앱 셸의 현재 UX 계약을 기록한다. 데스크톱 셸은 기존 `AppBar + AppSubSidebar + content` 구조를 유지하고, 모바일에서만 전역 앱 전환과 앱 내부 메뉴를 분리한다.

## Contract

- `AppBar`의 모바일 햄버거 버튼은 `앱 전환`만 연다. 이 드로어는 Workspace와 Apps 목록만 표시한다.
- 현재 앱 내부 메뉴는 모바일 상단의 앱 제목 버튼에서 별도 드로어로 연다.
- 내부 메뉴가 없는 화면(`home`, `profile`, Whiteboard 상세처럼 sub-sidebar를 숨기는 화면)은 앱 제목을 버튼이 아닌 정적 텍스트로 렌더링한다.
- 라우트의 pathname 또는 search가 바뀌면 앱 전환 드로어와 현재 앱 메뉴 드로어를 모두 닫는다.
- 현재 앱 메뉴는 `AppSubSidebar variant="mobile"`을 재사용한다. 같은 메뉴를 앱 전환 드로어 안에 다시 넣지 않는다.

## PMS Mobile Rule

PMS 같은 밀도 높은 업무 화면은 모바일에서 가로 3단 분할을 사용하지 않는다.

- 목록은 카드 중심으로 스캔한다.
- 필터는 압축된 바, 접힘 영역, 또는 시트로 연다.
- 상세는 전체 폭 패널 또는 전용 흐름으로 연다.
- 데스크톱의 보조 패널/서브사이드바는 모바일에서 앱 제목 메뉴 또는 detail drawer로 접는다.

## Time Display Rule

- API 저장/전송은 UTC ISO timestamp를 기준으로 한다.
- 사용자 표시 시간은 `user.time_zone`을 사용한다.
- 신규 사용자 기본값은 `Asia/Seoul`이다.
- 프론트엔드 시간 표시는 `apps/web/src/platform/time/time-utils.ts`를 거쳐야 하며, 각 화면에서 임의로 `new Date(...).toLocaleString()` 패턴을 늘리지 않는다.

## Implementation References

- `apps/web/src/app/shell/AppContent.tsx`
  - `MobileNavigationDrawer`: global app/workspace switcher
  - `MobileAppMenuDrawer`: current app submenu drawer
- `apps/web/src/components/layout/AppBar.tsx`
  - mobile hamburger: global switcher trigger
  - mobile app title: current app menu trigger when available
- `packages/ui/src/lib/layout/detail-drawer.tsx`
  - shared mobile/desktop drawer primitive
- `apps/web/src/app-modules/pms/views/`
  - mobile card list, filter, and task detail flow

## Regression Checklist

- Mobile 375px/390px/430px: hamburger opens only Workspace + Apps.
- Mobile app page: tapping the app title opens only that app's internal menu.
- Home/profile/Whiteboard detail: app title is not an inactive menu button.
- Route changes close both drawers.
- Desktop 1024px+: existing sub-sidebar remains visible and is not opened through the mobile title interaction.

## Verification Commands

```bash
env -u NODE_ENV pnpm exec vitest run apps/web/src/components/layout/AppBar.spec.tsx --config apps/web/vite.config.mts
pnpm nx typecheck web
pnpm nx lint web
pnpm nx build web
```
