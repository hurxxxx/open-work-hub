import json
import re
from hashlib import sha256
from pathlib import Path

VALIDATED_SCHEMA_NAMES = (
    "ThreadStartParams",
    "ThreadResumeParams",
    "TurnStartParams",
    "TurnSteerParams",
    "TurnInterruptParams",
    "ModelListParams",
    "CommandExecutionRequestApprovalResponse",
    "FileChangeRequestApprovalResponse",
    "ToolRequestUserInputResponse",
    "PermissionsRequestApprovalResponse",
)
COMPATIBILITY_SCHEMA_NAMES = (
    "InitializeParams",
    "InitializeResponse",
    "GetAccountParams",
    "GetAccountResponse",
    "NullableGetAccountRateLimitsParams",
    "GetAccountRateLimitsResponse",
    "ConfigReadParams",
    "ConfigReadResponse",
    "ModelListParams",
    "ModelListResponse",
    "ThreadStartParams",
    "ThreadStartResponse",
    "ThreadResumeParams",
    "ThreadResumeResponse",
    "ThreadReadParams",
    "ThreadReadResponse",
    "TurnStartParams",
    "TurnStartResponse",
    "TurnSteerParams",
    "TurnSteerResponse",
    "TurnInterruptParams",
    "TurnInterruptResponse",
    "ItemStartedNotification",
    "ItemCompletedNotification",
    "AgentMessageDeltaNotification",
    "PlanDeltaNotification",
    "CommandExecutionOutputDeltaNotification",
    "TurnPlanUpdatedNotification",
    "TurnCompletedNotification",
    "ServerRequestResolvedNotification",
    "CommandExecutionRequestApprovalParams",
    "CommandExecutionRequestApprovalResponse",
    "FileChangeRequestApprovalParams",
    "FileChangeRequestApprovalResponse",
    "ToolRequestUserInputParams",
    "ToolRequestUserInputResponse",
    "PermissionsRequestApprovalParams",
    "PermissionsRequestApprovalResponse",
    "McpServerElicitationRequestParams",
    "McpServerElicitationRequestResponse",
)
_STABLE_VERSION = re.compile(r"codex-cli (0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")


def supports_contract_version(output: str, minimum: str) -> bool:
    installed = _STABLE_VERSION.fullmatch(output.strip())
    required = _STABLE_VERSION.fullmatch(f"codex-cli {minimum}")
    if not installed or not required:
        return False
    return tuple(map(int, installed.groups())) >= tuple(map(int, required.groups()))


def _read_schema(source: Path, name: str) -> dict:
    schema = json.loads(next(source.rglob(name + ".json")).read_text())
    definitions = schema.pop("definitions", {})
    used = {}

    def visit(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "$ref" and item.startswith("#/definitions/"):
                    reference = item.split("/")[-1]
                    if reference not in used:
                        used[reference] = definitions[reference]
                        visit(used[reference])
                else:
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(schema)
    schema["definitions"] = used
    return schema


def _fingerprint(schema: dict) -> str:
    canonical = json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode()).hexdigest()


def build_contract(version: str, source: Path) -> dict:
    schemas = {name: _read_schema(source, name) for name in COMPATIBILITY_SCHEMA_NAMES}
    result = {
        "codexVersion": version,
        "compatibilityHashes": {name: _fingerprint(schema) for name, schema in schemas.items()},
        "schemas": {name: schemas[name] for name in VALIDATED_SCHEMA_NAMES},
    }
    return result


def render_contract(version: str, source: Path) -> str:
    rendered = json.dumps(
        build_contract(version, source), ensure_ascii=False, sort_keys=True, indent=2
    )
    return rendered + "\n"


def schemas_are_compatible(contract: dict, source: Path) -> bool:
    try:
        current = build_contract(contract["codexVersion"], source)
    except (json.JSONDecodeError, KeyError, OSError, StopIteration, TypeError):
        return False
    return current["compatibilityHashes"] == contract.get("compatibilityHashes")
