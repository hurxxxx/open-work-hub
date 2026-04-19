# QA Run — PMS / Docs / Meeting Smoke (2026-04-19)

실행자: `agent-browser` 실제 상호작용 + Codex
세션:
- member: `doowon-e2e`
환경:
- web `127.0.0.1:4200`
- api `127.0.0.1:8000`
- 서버 기동 상태 재사용: `./dev.sh --restart --plain-logs`

## Result Summary

| ID | Scenario | Result | 메모 |
|----|----------|--------|------|
| A1 | PMS list detail open | PASS | `QA Scenario List` 상세 진입, list/table toolbar 정상 |
| A2 | PMS task create | PASS | `Smoke PMS Task 20260419` 생성 후 `QASCEN-3` row 반영 |
| A3 | PMS issue detail panel | PASS | `QASCEN-3` row 클릭 시 상세 패널 열림 |
| A4 | Docs library open | PASS | `All Docs` 진입, 빈 상태/템플릿/`New Doc` 동작 확인 |
| A5 | Docs native doc create | PASS | `Smoke Doc 20260419` 생성 후 editor route 진입 |
| A6 | Docs list/reopen | PASS | 목록에 새 문서 노출, row 클릭으로 재열기 성공 |
| A7 | Meeting list open | PASS | `/w/delivery-hub/meeting` 진입, `Upcoming/My Meetings/Recordings` 렌더 |
| A8 | Meeting create | PASS | `Smoke Meeting 20260419` 생성 후 `/w/delivery-hub/meeting/<id>` 상세 route 진입 |
| A9 | Meeting notes -> Docs deep link | PASS | notes 입력 후 `Open in Docs`가 같은 workspace docs route로 이동 |

PASS 9

## Findings

### F1. [LOW] PMS `New Task` dialog 접근성 warning

- **재현**: `QA Scenario List` 상세에서 `New Task` 버튼 클릭
- **브라우저 콘솔**:
  - `Warning: Missing Description or aria-describedby={undefined} for {DialogContent}.`
- **영향**: 기능 동작에는 문제 없었고 생성도 성공했지만, dialog accessibility markup은 보완이 필요하다.

## URLs Checked

- `http://127.0.0.1:4200/w/delivery-hub/pms`
- `http://127.0.0.1:4200/tool/pms-list-df0dd7a7-ce2a-4ec2-b646-e60aa64f57be`
- `http://127.0.0.1:4200/w/delivery-hub/docs`
- `http://127.0.0.1:4200/w/delivery-hub/docs/native_doc__980951cb-1c8c-4e85-9512-558f8cef8b6b`
- `http://127.0.0.1:4200/w/delivery-hub/meeting`
- `http://127.0.0.1:4200/w/delivery-hub/meeting/2b66c4d6-a778-4757-a49e-f4896a828925`
- `http://127.0.0.1:4200/w/delivery-hub/docs/38718484-772e-4cfd-95cc-e7ce18512996`

## Test Data

- PMS issue: `QASCEN-3` / `Smoke PMS Task 20260419`
- Native doc: `native_doc__980951cb-1c8c-4e85-9512-558f8cef8b6b`
- Meeting: `2b66c4d6-a778-4757-a49e-f4896a828925`
- Meeting notes doc route id: `38718484-772e-4cfd-95cc-e7ce18512996`

## Notes

- `agent-browser errors`는 비어 있었다.
- 이번 smoke는 앱별 핵심 생성/진입/딥링크 수준만 확인했다.
- PMS list detail이 `/w/:workspaceSlug/...`가 아닌 `/tool/pms-list-...` 형태로 열리는 점은 현재 동작 자체는 문제 없었지만, workspace-first routing 원칙과의 정합성은 별도 검토 여지가 있다.
