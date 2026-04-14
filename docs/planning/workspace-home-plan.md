# Per-Workspace Home — 향후 과제로 미룸

## Context

앱바 HOME 버그 수습 중에 "워크스페이스별 홈" 주제가 떠올랐지만, 현재 우선순위가 아니라고 판단됨. 본격 구현은 미루고 [TODO-PLAN.md](../../TODO-PLAN.md)의 `후속 개선 후보` 섹션 **마지막**에 한 줄로 기록만 남긴다. 실제 설계/구현은 해당 항목이 다시 꺼내질 때 이 파일을 참고해 재개한다.

## 벤치마크 요약

| 서비스 | 차용 포인트 |
|---|---|
| **Notion Home** | "Jump back in" 수평 카드 스트립, 중앙 정렬 여백 레이아웃, 상단 greeting |
| **Linear Inbox / My Issues** | 상태별 그룹핑, 키보드 내비, 미니멀 정보 밀도 |
| **ClickUp Home** | Agenda(오늘 미팅) + LineUp(내 일) + Assigned 위젯 조합 |
| **Slack Home** | 워크스페이스 전환 시 홈이 같이 바뀌는 멘탈 모델 |
| **Asana My Tasks** | Today / Upcoming / Later 시간대 버킷 |

공통 합의점: 시간대 인지 greeting, "최근 작업"이 최고 클릭률 위젯, 오늘 캘린더, 내 태스크 그룹핑, 중앙 정렬 max-w ~960px + 널찍한 수직 간격 + 얕은 보더(Notion/Linear 미학).

## 수정할 파일 (구현 착수 시)

- [apps/web/src/domains/workspaces/workspace-utils.ts](../../apps/web/src/domains/workspaces/workspace-utils.ts) — `WorkspaceAppId` 유니온(L3), `WORKSPACE_APP_IDS`(L5-11), `WORKSPACE_APP_PATH_PATTERN`(L24)에 `home` 추가
- [apps/web/src/App.tsx](../../apps/web/src/App.tsx) — L252 `/` 라우트를 `Navigate replace`로 교체, `/w/:workspaceSlug/home` 라우트 신규 추가 (WorkspaceGate 래핑), `/w/:workspaceSlug` bare path도 `/w/:slug/home`으로 리다이렉트
- [apps/web/src/components/layout/AppBar.tsx](../../apps/web/src/components/layout/AppBar.tsx) — 현재 상태(L285-287) 유지. `buildAppLink`가 `home`도 자연스럽게 처리하도록 workspace-utils 확장에 의존
- [apps/web/src/components/layout/SubSidebar.tsx](../../apps/web/src/components/layout/SubSidebar.tsx) — `NAV_ITEMS.filter(...)` 결과가 빈 배열이면 `return null` (home은 서브사이드바 접힘)
- [apps/web/src/app-shell.ts](../../apps/web/src/app-shell.ts) — `ShellAppId`가 `/w/:slug/home`을 `activeAppId='home'`으로 매핑하는지 확인
- [apps/web/src/components/views/HomeView.tsx](../../apps/web/src/components/views/HomeView.tsx) — 더미 데이터만 있는 146줄 파일이므로 삭제
- 신규: `apps/web/src/components/views/WorkspaceHomeView/`
  - `WorkspaceHomeView.tsx` (레이아웃 셸)
  - `GreetingHeader.tsx` — korean-holidays 재사용
  - `QuickActionsRow.tsx` — `meeting:create-event` window event 재사용
  - `TodayMeetingsWidget.tsx`
  - `MyTasksWidget.tsx`
  - `RecentlyVisitedWidget.tsx`

## 재사용 대상 (신규 API/유틸 만들지 않음)

- `buildWorkspaceAppPath`, `resolveDefaultWorkspaceAppPath`, `resolveWorkspaceSwitchPath`
- `rewriteWorkspaceApiPath` — 도메인 클라이언트가 자동으로 `/api/v1/workspaces/:slug/...` 경로 생성 ([workspace-utils.ts:205](../../apps/web/src/domains/workspaces/workspace-utils.ts#L205))
- 기존 meeting/pms/docs 도메인 hook
- 백엔드 엔드포인트:
  - `GET /api/v1/workspaces/:slug/meeting/meetings?scope=upcoming` — [meeting/router.py:63-79](../../apps/api/src/aidoo_api/domains/meeting/router.py#L63-L79)
  - `GET /api/v1/workspaces/:slug/pms/docs-hub/recent-pages?limit=10` — [pms/router.py:4701](../../apps/api/src/aidoo_api/domains/pms/router.py#L4701)
  - PMS assigned-to-me — 존재 여부 사전 확인 필요, 없으면 해당 위젯만 다음 라운드로

## 구현 시 검증 루틴

1. `pnpm nx typecheck web` — `WorkspaceAppId` 확장 회귀 0건
2. Playwright MCP 또는 브라우저 수동 QA:
   - `/` → `/w/hq/home` 리다이렉트
   - 앱바 HOME 클릭 → 현재 워크스페이스의 home
   - 워크스페이스 스위처로 전환 시 home 데이터 스코프 변경
   - `/w/:bad-slug/home` → AccessDeniedView
   - 각 위젯 empty state
3. 서브사이드바 접힘 / 복귀
4. WCAG AA 4.5:1 다크모드 contrast (D6 이월 항목)
5. `cd apps/api && uv run --python 3.12 --group dev pytest` — 75 passing 유지 (신규 엔드포인트 없으므로 회귀만 체크)

## Out of Scope (구현 시에도 다음 라운드)

- 워크스페이스 활동 피드 (Slack/Linear 업데이트 타임라인)
- 즐겨찾기 / 고정 문서
- 위젯 재정렬 / 커스터마이즈 (Notion 수준)
- 크로스 워크스페이스 "모든 내 태스크" 글로벌 인박스
- Home 서브사이드바 탭 (Overview/Activity/Bookmarks)
