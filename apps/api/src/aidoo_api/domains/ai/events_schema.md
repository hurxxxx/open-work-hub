# Agent Event Envelope

Wire format for `POST /api/v1/ai/chat/stream` (Server-Sent Events).

## Envelope shape

Every frame has the same top-level fields:

| field         | type   | notes                                         |
|---------------|--------|-----------------------------------------------|
| `seq`         | int    | monotone, starts at 0 per stream              |
| `timestamp_ms`| int    | server wall clock, ms since epoch             |
| `type`        | string | discriminator                                 |
| `data`        | object | shape determined by `type`                    |

Consumers **must ignore unknown `type` values**. Phase 2 publishes five types;
tool-calling (Phase 3) and approval (Phase 4) types are reserved.

SSE framing: each frame is `event: <type>\ndata: <json>\n\n`. Server emits
a `: keepalive` comment every 25 s to defeat idle proxies.

## Phase 2 published types

### `content_delta`
```json
{"seq":1,"timestamp_ms":1700000000123,"type":"content_delta","data":{"text":"Hello"}}
```

### `reasoning_delta`
Only emitted when `reasoning_effort != "none"` and `stream_reasoning=true`.
```json
{"seq":0,"timestamp_ms":1700000000100,"type":"reasoning_delta","data":{"text":"Let me think…"}}
```

### `usage`
Provider-reported token counts. Any field may be missing.
```json
{"seq":5,"timestamp_ms":...,"type":"usage","data":{"prompt_tokens":12,"completion_tokens":42,"total_tokens":54}}
```

### `done`
Terminal frame. `finish_reason` values: `stop`, `length`, `cancelled`, `error`.
`meta` carries the same policy/pool badges the sync `/ai/chat` response does.
`audit_id` is reserved (always `null` in Phase 2).
```json
{
  "seq":6,"timestamp_ms":...,"type":"done",
  "data":{
    "finish_reason":"stop","audit_id":null,
    "meta":{
      "policy":"external","chosen_pool":"local","decision_reason":"pii_detected",
      "forced_local":true,"pii_hits":["email"],
      "model":"mlx-community/...","chosen_model":"mlx-community/...",
      "canonical_model":"qwen3-next-80b",
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

## Reserved types (not emitted in Phase 2)

- `tool_call_started` — `{call_id, name, args_preview}` (P3)
- `tool_call_args_delta` — `{call_id, delta}` (P3)
- `tool_result` — `{call_id, status, result_preview?, error?}` (P3)
- `approval_required` — `{approval_id, tool, resource_preview?}` (P4)
- `approval_resolved` — `{approval_id, decision}` (P4)

## Stream lifecycle

```
[reasoning_delta ...]?   # 0..n, only if effort != none
[content_delta ...]+     # 1..n
[usage]?                 # 0..1, provider-dependent
[error]?                 # 0..1, only on failure; paired with done(error)
done                     # exactly 1, terminal
```
