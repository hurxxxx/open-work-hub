# PR3 Status

## 2026-04-19 AI chat history stabilization

- Phase 3.3 conversation-history flow에서 실제 회귀 지점 4개를 보강했다:
  - `conversation_attached` 로 `?c=` 를 갱신할 때 자기 자신을 다시 hydrate 하면서 live stream 을 덮어쓰던 경합 차단
  - 대화 전환/리셋 후 stale stream cancellation/error 가 새 화면 상태를 다시 덮어쓰던 문제 차단
  - 기존 대화 hydrate 완료 전 submit 가능하던 경로 차단
  - invalid `?c=` 로 이동했을 때 이전 대화 turn 이 화면에 남던 문제 수정
- 브라우저 검증:
  - `pnpm playwright test --config apps/web/playwright.config.ts apps/web/e2e/chat-history.spec.ts --project=chromium`
  - 결과: 3개 시나리오 모두 PASS
  - 범위: 최근 대화 목록 표시, 사이드바 선택 후 `/w/hq/ai?c=<id>` hydrate, `+ 새 대화` 빈 상태 복귀
- 단위 검증:
  - `pnpm vitest run -c apps/web/vite.config.mts apps/web/src/components/views/AIView.spec.tsx`
  - `pnpm vitest run -c apps/web/vite.config.mts apps/web/src/domains/ai/useChatStream.spec.ts`
  - 추가 커버리지: `conversation_attached` URL replace, hydrate 중 submit disable, invalid conversation stale-turn clear, `reset()` 이후 stale stream update 무시

## 2026-04-16 Planner Event + Meeting availability verification

- Local dev DB needed `alembic upgrade head` after adding `planner_events`; before migration, `/api/v1/calendar/events` returned 500 in the live browser because the new table was missing.
- Browser verification used `agent-browser` against `http://127.0.0.1:4200/w/hq/planner`.
- Verified `hq-admin` planner flow:
  - `Add > Event` opened the new `PlannerEventModal`
  - saved public event `브라우저 공개 이벤트`
  - event rendered back into the month grid immediately
- Verified `hq-member` planner flow in a separate browser session:
  - saved public event `멤버 공개 이벤트`
  - event rendered on `2026-03-29 09:00`
- Verified `MeetingCreateModal` availability flow:
  - invited `AI-DO HQ Member`
  - changed meeting time to `2026-03-29 09:30-10:00`
  - inline conflict summary showed `멤버 공개 이벤트 · 09:00-10:00`
  - `스케줄 보기` modal opened and rendered attendee row + public event title
- Found and fixed a real frontend regression during browser smoke:
  - `useMeetingAvailabilityQuery` was refetching endlessly because `useEffect` depended on unstable `Date` / array references
  - symptom: repeated `/meeting/availability` requests and React `Maximum update depth exceeded` console errors
  - fix: depend on stable timestamp / user-id keys instead of object identity

## 2026-04-13 Recording verification

- Local DB needed `alembic upgrade head` before Meeting detail would render new recording fields without 500s.
- Verified in browser at `http://127.0.0.1:4200/w/hq/meeting?id=834c5cee-e273-42ee-809e-541ff70477e4`.
- Test meeting title: `Recording E2E Test`
- Verified UI in Meeting detail right panel:
  - `녹음 시작`
  - `음성 파일 업로드`
  - failed-state `다시 시도`
- Verified manual upload path with `/tmp/doowon-recording-test.wav`.
- Current local environment does not have Redis/broker on `127.0.0.1:6379`, so uploaded recordings are intentionally saved as raw audio and shown as `failed` with retry messaging instead of 500.
- Updated the `Meeting > 녹음` top-level placeholder copy to clarify that recording actions currently live in the Meeting detail panel.

## Commands run

```bash
cd apps/api
uv run --group dev pytest tests/test_meeting_recordings.py

cd /Users/edward/projects/doowon
pnpm nx typecheck web --skip-nx-cache
```
