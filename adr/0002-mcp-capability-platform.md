# ADR 0002: MCP-First AI Capability Platform Contracts

- Status: Accepted
- Date: 2026-04-20

## Decision

- Internal capability source: `AiCapabilityDescriptor`.
- MCP manifest is the primary AI-facing artifact.
- OpenAI strict schema and derived OpenAPI are generated from descriptor/MCP.
- Domains register tools through `register_ai_capabilities(registry)` and `AiCapabilityRegistry.register_tool(...)`.
- Tool input uses AI-specific Pydantic DTOs, not human REST request models.
- Tool handler calls application/domain service, not router code.
- Every capability has a `discoverability_predicate_id`.
- Duplicate tool/predicate/preview/handler registration fails fast.
- Discovery filters by platform/workspace entitlement and discoverability.
- Execution repeats discoverability and then domain ACL/service authorization.
- Hidden in discovery means blocked in execution.
- Write capability requires `approval_required=True`, `preview_builder_id`, and `OPEN_WORK_HUB_AI_WRITE_TOOLS_ENABLED=true` for discovery exposure.

## Schema

- Canonical schema subset: JSON Schema 2020-12 object/array/enum/scalar, nullable union, local `$ref` inline.
- Forbidden: `allOf`, `not`, `patternProperties`, conditionals, external `$ref`, non-nullable complex unions.
- Legacy `openai_tool_specs()` is compatibility only.

## Required Tests

- registry compile
- duplicate guard
- schema compatibility
- MCP manifest/derived OpenAPI filtering
- direct invoke
- hidden-tool blocked
- stream/agent loop regression when runtime changes

## Do Not

- Add ad hoc tool specs in routers/agents.
- Hardcode app lists inside AI registry.
- Expose write tools only because handler code exists.
