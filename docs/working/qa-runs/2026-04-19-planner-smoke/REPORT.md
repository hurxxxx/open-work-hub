# QA Run — Planner Smoke + Dialog A11y Fix (2026-04-19)

실행자: `agent-browser` 실제 상호작용 + Codex
세션:
- member: `doowon-e2e`
환경:
- web `127.0.0.1:4200`
- api `127.0.0.1:8000`
- 서버 기동 상태 재사용: `./dev.sh --restart --plain-logs`

## Code Change

- 공통 `Dialog`가 description 없는 경우에도 Radix warning 없이 열리도록 [dialog.tsx](/Users/edward/projects/doowon/packages/ui/src/lib/primitives/dialog.tsx:45)에 `aria-describedby={undefined}` opt-out 경로 추가
- shared-ui 계약 테스트 추가: [ui.spec.tsx](/Users/edward/projects/doowon/packages/ui/src/lib/ui.spec.tsx:1)

검증:
- `pnpm nx test ui --skip-nx-cache` PASS
- `pnpm exec tsc -p apps/web/tsconfig.app.json --noEmit` PASS

## Result Summary

| ID | Scenario | Result | 메모 |
|----|----------|--------|------|
| P1 | PMS `New Task` dialog warning regression check | PASS | 기존 `Missing Description or aria-describedby` warning 재현되지 않음 |
| P2 | Planner shell open | PASS | `/w/delivery-hub/planner` 진입, calendar/agenda shell 정상 |
| P3 | Planner event create | PASS | `Smoke Planner Agenda 20260419` 저장 성공 |
| P4 | Planner event visibility | PASS | Agenda view에 `2026년 4월 12일 / 오전 9:00 - 오전 10:00 / Smoke Planner Agenda 20260419` 노출 |
| P5 | Planner event edit reopen | PASS | 생성한 일정 클릭 시 `Edit Event` 모달로 재진입, title/location/notes 유지 |

PASS 5

## URLs Checked

- `http://127.0.0.1:4200/tool/pms-list-df0dd7a7-ce2a-4ec2-b646-e60aa64f57be`
- `http://127.0.0.1:4200/w/delivery-hub/planner`

## Test Data

- Planner event title: `Smoke Planner Agenda 20260419`
- Planner event date: `2026-04-12 09:00-10:00`
- Location: `Delivery Hub`

## Notes

- 이번 세션 기준 `agent-browser console`, `agent-browser errors` 모두 빈 결과였다.
- Planner `Add -> Event`의 기본 날짜는 현재 화면의 period context를 따르기 때문에, smoke 시에는 저장 직후 `Agenda` view에서 노출 여부를 확인하는 편이 안정적이었다.
