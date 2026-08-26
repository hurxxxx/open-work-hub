# Agent Event Envelope

Wire format for `POST /api/v1/workspaces/{workspace_slug}/chatbot/chat/stream`.

## Envelope

Every SSE frame:

| Field | Type | Rule |
| --- | --- | --- |
| `seq` | int | monotone, starts at 0 per stream |
| `timestamp_ms` | int | server wall clock ms |
| `type` | string | discriminator |
| `data` | object | event-specific payload |

- Consumers ignore unknown `type`.
- Event type versions the union.
- SSE frame format: `event: <type>\ndata: <json>\n\n`.
- Ping interval: 25 seconds; ignore comment frames.

## Core Types

```json
{"seq":1,"timestamp_ms":1700000000123,"type":"content_delta","data":{"text":"Hello"}}
```

```json
{"seq":0,"timestamp_ms":1700000000100,"type":"reasoning_delta","data":{"text":"..."}}
```

`reasoning_delta` emits only when `reasoning_effort != "none"` and `stream_reasoning=true`.

```json
{"seq":5,"timestamp_ms":1700000000200,"type":"usage","data":{"prompt_tokens":12,"completion_tokens":42,"total_tokens":54}}
```

Usage fields are provider-dependent and optional.

```json
{"seq":6,"timestamp_ms":1700000000300,"type":"done","data":{"finish_reason":"stop","audit_id":null,"meta":{}}}
```

`done` is terminal. `finish_reason`: `stop`, `length`, `cancelled`, `error`, `awaiting_approval`.

```json
{"seq":3,"timestamp_ms":1700000000250,"type":"error","data":{"code":"provider_error","message":"connection refused","retryable":false}}
```

`error` is followed by `done(error)`. HTTP status remains 200.

## Other Types

- `conversation_attached`: `{conversation_id}`
- `artifact_started`: `{artifact_id, artifact_type, title?, language?}`
- `artifact_delta`: `{artifact_id, delta}`
- `artifact_completed`: `{artifact_id}`
- `tool_call_started`: `{call_id, name, args_preview}`
- `tool_call_args_delta`: `{call_id, delta}`
- `tool_result`: `{call_id, status, result_preview?, error?}`, `status` is `ok`, `error`, or `rejected`
- `approval_required`: `{approval_id, call_id, tool, resource_preview?, expires_at_ms}`
- `approval_resolved`: `{approval_id, call_id, decision, reason?}`

## Lifecycle

```text
[conversation_attached]?
[reasoning_delta ...]?
[tool/artifact events]*
[content_delta ...]*
[usage]?
[error]?
done
```

- Tool, artifact, reasoning, and content events may interleave.
- Approval pause ends with `approval_required` and `done(awaiting_approval)`.
- Provider/adapter failure ends with `error` and `done(error)`.
- Approval/error paths may emit no `content_delta`.
