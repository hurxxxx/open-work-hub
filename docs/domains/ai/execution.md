# AI Execution

This document owns durable AI execution state: approval-paused agent runs, queued graph runs, and
AI artifacts. Provider/model routing remains in [AI Gateway](gateway.md); write-tool exposure and
approval policy remain in [AI Write Policy](write-policy.md).

## Approval Pause And Resume

- A write tool halts before mutation and persists the exact conversation messages, resolved model
  metadata, allowed app IDs, resolved tool names, tool call, arguments, preview, actor, workspace,
  and conversation identity.
- Only the requesting user in the same workspace and conversation may resolve and resume it.
- Resume replays the frozen snapshot. A request may narrow but never widen the stored app scope;
  the available tool set is intersected with the stored tool names, and the approved tool's app
  must remain in scope.
- Approval does not preserve authorization. Resume and tool execution recheck current app
  availability, descriptor discoverability, source ACL, and domain business rules before mutation.
- Snapshot states are `awaiting_approval`, `resumed`, `completed`, and `abandoned`. Expired or
  cancelled approvals cannot be resumed; only one live approval snapshot may own a conversation.

## Durable Graph Runs

- Current graph runs are workspace-scoped and bind the requester, owning executable app, graph ID
  and version, checkpoint namespace, visibility, and input schema version.
- The caller transaction stages the run, bootstrap input, optional pending artifact, and dispatch
  outbox together. The broker message carries a reference, not mutable graph state.
- Outbox publication is at least once. Dispatch rows and graph execution use claim tokens; stale
  claims may be recovered, while an active execution lease fences duplicate workers.
- LangGraph PostgreSQL checkpoints own resumable node state. `ai_graph_runs` is only the monotone UI
  status/progress projection. A stale-lease recovery resumes from the checkpoint when present.
- App availability is rechecked before dispatch, after execution claim, before every node, and
  before completion. Disablement terminalizes the run as cancelled and fails pending/building
  artifacts before provider or storage mutation can continue.
- Graph terminal states are `completed`, `failed`, and `cancelled`; they cannot transition again.
  Bootstrap input is deleted only after a terminal state.

## Artifacts And Visibility

- Runs and artifacts are visible only inside their workspace, to their owner or workspace audience,
  and while the owning app remains enabled for the viewer.
- Artifacts build through `pending`/`building` and finish as `completed` or `failed`. Content,
  sources, queries, and generation evidence are mutable only while building.
- Completion atomically records content hash, size, and completion time. Completed artifact content
  is immutable; an owner may change only `private`/`workspace` visibility.
- A replacement creates a new artifact that explicitly supersedes a completed artifact of the same
  workspace and type. It never edits the prior artifact in place.

## Checks

```bash
(cd apps/api && uv run --python 3.12 --group dev python -m pytest tests/test_ai_approvals.py tests/test_ai_graph_artifacts.py -q)
(cd apps/worker && uv run --python 3.12 --group dev python -m pytest tests/test_ai_graph_tasks.py -q)
pnpm exec vitest run --root apps/web src/app-modules/chatbot/api/ai-artifacts-api.spec.ts src/app-modules/chatbot/views/chat/artifacts/AiReportArtifact.spec.tsx src/app-modules/chatbot/views/chat/artifacts/artifact-download.spec.ts
```
