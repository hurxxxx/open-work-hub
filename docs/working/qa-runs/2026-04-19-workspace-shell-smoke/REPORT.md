# QA Run — Workspace Shell Smoke (2026-04-19)

실행자: `agent-browser` 실제 상호작용 + Codex
세션:
- member: `doowon-e2e`
- workspace-admin: `doowon-admin-e2e`
- platform-admin: `doowon-platform-e2e`
환경:
- web `127.0.0.1:4200`
- api `127.0.0.1:8000`
- 실행 전 `apps/api`에서 `uv run --python 3.12 alembic upgrade head` 적용
- 서버 기동: `./dev.sh --restart --plain-logs`

## Result Summary

| ID | Scenario | Result | 메모 |
|----|----------|--------|------|
| W1 | Dev login with seed member account | PASS | seed quick-login 카드는 불안정. 이메일/비밀번호 직접 입력으로 로그인 성공 |
| W2 | Workspace home shell bootstrap | PASS | `delivery-hub-member` 로그인 후 `/w/delivery-hub/home` 진입, AppBar에 `HOME/AI/PMS/DOCS/Planner/MEETING` 노출 |
| W3 | AI shell + bootstrap nav | PASS | `/w/delivery-hub/ai`에서 subsidebar `Core Tools / Assistants / Patent` 및 하위 링크 렌더링 확인 |
| W4 | Cross-workspace URL block | PASS | `delivery-hub-member`로 `/w/knowledge-base/ai` 직접 진입 시 `접근 권한 없음` |
| W5 | Legacy top-level route block | PASS | `/meeting` 직접 진입 시 `페이지를 찾을 수 없습니다` |
| W6 | Workspace settings member gate | PASS | `delivery-hub-member`로 `/w/delivery-hub/settings` 진입 시 `접근 권한 없음` |
| W7 | Workspace settings admin access | PASS | `delivery-hub-admin`로 `/w/delivery-hub/settings` 진입 시 workspace detail/member preview 정상 렌더 |
| W8 | Admin workspace list/detail | PASS | `platform-admin`로 `/admin/workspaces` 진입 및 `Delivery Hub` detail 패널 전환 정상 |

PASS 8

## Notes

- `agent-browser errors`는 member / platform-admin 세션 모두 빈 결과였다.
- 브라우저 콘솔에는 page error 없이 Vite 연결 로그와 React DevTools 안내만 보였다.
- 로그인 화면의 seed quick-login 카드는 이번 자동화에서도 클릭이 먹지 않았다. 저장소 지침대로 로그인 폼 직접 입력이 더 안정적이었다.

## URLs Checked

- `http://127.0.0.1:4200/login`
- `http://127.0.0.1:4200/w/delivery-hub/home`
- `http://127.0.0.1:4200/w/delivery-hub/ai`
- `http://127.0.0.1:4200/w/knowledge-base/ai`
- `http://127.0.0.1:4200/meeting`
- `http://127.0.0.1:4200/w/delivery-hub/settings`
- `http://127.0.0.1:4200/admin/workspaces`

## Follow-up

1. 이번 smoke는 shell/access 수준만 확인했다. AI tool 실행 파이프라인 end-to-end는 아직 미연결이라 별도 시점에 검증해야 한다.
2. quick-login 카드 클릭 불안정은 계속 남아 있으니, 브라우저 자동화 기본 경로는 폼 로그인으로 유지하는 편이 낫다.
