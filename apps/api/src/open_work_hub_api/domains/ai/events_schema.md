# Agent Event Envelope

Wire format for `POST /api/v1/workspaces/{workspace_slug}/chatbot/chat/stream` (Server-Sent Events).

## Envelope shape

Every frame has the same top-level fields:

| field          | type   | notes                             |
| -------------- | ------ | --------------------------------- |
| `seq`          | int    | monotone, starts at 0 per stream  |
| `timestamp_ms` | int    | server wall clock, ms since epoch |
| `type`         | string | discriminator                     |
| `data`         | object | shape determined by `type`        |

Consumers **must ignore unknown `type` values**. The discriminated union is
versioned by event type, not by implementation phase.

SSE framing: each frame is `event: <type>\ndata: <json>\n\n`. The server configures
an SSE ping interval of 25 seconds; consumers must ignore comment frames.

## Core event types

### `content_delta`

```json
{
  "seq": 1,
  "timestamp_ms": 1700000000123,
  "type": "content_delta",
  "data": { "text": "Hello" }
}
```

### `reasoning_delta`

Only emitted when `reasoning_effort != "none"` and `stream_reasoning=true`.

```json
{
  "seq": 0,
  "timestamp_ms": 1700000000100,
  "type": "reasoning_delta",
  "data": { "text": "Let me think…" }
}
```

### `usage`

Provider-reported token counts. Any field may be missing.

```json
{"seq":5,"timestamp_ms":...,"type":"usage","data":{"prompt_tokens":12,"completion_tokens":42,"total_tokens":54}}
```

### `done`

Terminal frame. `finish_reason` values: `stop`, `length`, `cancelled`, `error`,
`awaiting_approval`.
`meta` carries the same policy/pool badges as the sync
`POST /api/v1/workspaces/{workspace_slug}/chatbot/chat` response.
`audit_id` is optional.

```json
{
  "seq":6,"timestamp_ms":...,"type":"done",
  "data":{
    "finish_reason":"stop","audit_id":null,
    "meta":{
      "policy":"external","chosen_pool":"local","decision_reason":"pii_detected",
      "forced_local":true,"pii_hits":["email"],
      "model":"mlx-community/...","chosen_model":"mlx-community/...",
      "canonical_model":"local-model-profile",
      "provider":"mlx-lm"
    }
  }
}
```

### `error`

Provider or adapter failure. Always followed by a `done` with
`finish_reason="error"`. HTTP status remains 200 — errors surface on the wire,
not in the status code.

```json
{"seq":3,"timestamp_ms":...,"type":"error","data":{"code":"provider_error","message":"connection refused","retryable":false}}
```

## Conversation, artifact, tool, and approval types

- `conversation_attached` — `{conversation_id}`
- `artifact_started` — `{artifact_id, artifact_type, title?, language?}`
- `artifact_delta` — `{artifact_id, delta}`
- `artifact_completed` — `{artifact_id}`
- `tool_call_started` — `{call_id, name, args_preview}`
- `tool_call_args_delta` — `{call_id, delta}`
- `tool_result` — `{call_id, status, result_preview?, error?}` where `status ∈ {ok, error, rejected}`
- `approval_required` — `{approval_id, call_id, tool, resource_preview?, expires_at_ms}`
- `approval_resolved` — `{approval_id, call_id, decision, reason?}`

## Stream lifecycle

```
[conversation_attached]? # 0..1, only when a persisted conversation is attached
[reasoning_delta ...]?   # 0..n, only if effort != none
[tool/artifact events]*   # 0..n, depending on runtime behavior
[content_delta ...]*     # 0..n; approval/error paths may emit none
[usage]?                 # 0..1, provider-dependent
[error]?                 # 0..1, only on failure; paired with done(error)
done                     # exactly 1, terminal
```

Tool, artifact, reasoning, and content events may interleave while a run is active.
An approval pause ends with `approval_required` and `done(awaiting_approval)`;
a provider/adapter failure ends with `error` and `done(error)`. Neither terminal
branch requires a `content_delta`.
