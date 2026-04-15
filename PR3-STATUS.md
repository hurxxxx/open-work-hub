# PR3 Status

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
  - invited `Aidoo HQ Member`
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
