# Chat View Design

Updated: 2026-04-18

## Scope

This document fixes the Phase 2 chat view baseline so Phase 3 tool calling and
Phase 4 approval flows can land without changing the stream state model.

## Message Bubbles

- Layout: assistant messages are left-aligned, user messages are right-aligned.
- Width: bubbles cap at `min(720px, 80%)` to keep long Korean prose readable.
- Shape: use the existing `rounded-lg` app surface language; avoid heavy cards,
  shadows, or dashboard framing.
- Typography: body copy uses `app-text-body-sm` with relaxed line height and
  preserved newlines.
- Meta line: render compact routing/error metadata under assistant bubbles only.
  Show it for `error`, `cancelled`, or when pool/policy metadata exists.

## Thinking Panel

- Placement: inside the assistant bubble, below visible answer text.
- Default: collapsed.
- Streaming state:
  - no reasoning yet: render nothing
  - reasoning streaming: panel label indicates active thinking
  - reasoning complete: panel stays available but collapsed by default
- Reasoning text is secondary content, not the primary answer. Use subdued
  contrast and smaller type than the answer body.

## Tool And Approval Placeholders

- Tool calls render in a dedicated placeholder strip below the thread, not
  inline inside message text.
- Approval prompts use the same finalized-turn data source as tool calls.
- Even before real UI ships, the turn model must retain `toolCalls` and
  `pendingApprovals` after the live stream buffer resets.
- Phase 3 and 4 should only need component-body work; no hook or envelope
  reshaping should be required.

## Approval Modal

- Placement: modal overlay, one approval at a time.
- Source of truth: current live pending approval state seeded from SSE
  `approval_required` envelopes or `conversation.live_pending_approval` on
  reload.
- Content:
  - tool name and short Korean label
  - `resource_preview` summary
  - expandable full arguments JSON block from `GET /ai/approvals/{id}`
  - optional reject reason textarea with 140-character cap
- Actions:
  - 승인: resolve API then resume SSE immediately
  - 거절: resolve API with optional reason then resume SSE immediately
  - 요청 취소: abandon API, no resume
- Composer policy:
  - pending approval blocks new user input
  - approved/rejected but not yet resumed keeps the composer blocked and shows
    an inline "이어가기" recovery action

## Error And Cancel States

- Pre-stream failure: rollback the optimistic user turn, restore the draft
  input, and show an inline error banner above the composer.
- In-stream error: keep the user turn, finalize the partial assistant turn, and
  mark the assistant meta line as `응답 실패`.
- Cancelled stream: keep partial assistant output if any; otherwise finalize a
  short `응답이 중단되었습니다.` fallback copy and mark the meta line as
  `응답 중단`.
- Do not restore composer text after an in-stream error or cancellation.

## Hidden Stream Toggle

- Streaming is default-on.
- Rollback control stays hidden from end users.
- Allowed controls:
  - code constant
  - `localStorage` key for operator debugging
- Do not add a visible settings toggle unless product explicitly asks for it.
