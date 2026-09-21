"""Recover structured answers from accepted legacy plan operations."""

import json

from alembic import op
from sqlalchemy import text

revision = "console_0008"
down_revision = "console_0007"
branch_labels = None
depends_on = None


def _unwrap_proposed_plan(value: str) -> str:
    opening = "<proposed_plan>"
    closing = "</proposed_plan>"
    candidate = value.strip()
    if not candidate.startswith(opening) or not candidate.endswith(closing):
        return value
    body = candidate[len(opening) : -len(closing)].strip()
    return body or value


def _plan_body(value: str) -> str | None:
    try:
        structured = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None
    if (
        not isinstance(structured, dict)
        or set(structured) != {"answer", "documents"}
        or not isinstance(structured["answer"], str)
        or not isinstance(structured["documents"], list)
    ):
        return None
    for document in structured["documents"]:
        if (
            isinstance(document, dict)
            and document.get("kind") == "plan"
            and isinstance(document.get("body"), str)
            and document["body"].strip()
        ):
            return _unwrap_proposed_plan(document["body"])
    if structured["documents"]:
        return None
    answer = structured["answer"].strip()
    return _unwrap_proposed_plan(answer) if answer else None


def upgrade():
    connection = op.get_bind()
    rows = (
        connection.execute(
            text(
                "SELECT DISTINCT ON (task.id) task.id AS task_id, final.turn_id, "
                "final.payload->>'text' AS body "
                "FROM console_tasks AS task "
                "JOIN console_operations AS operation "
                "ON operation.task_id = task.id "
                "AND operation.kind = 'plan' AND operation.state = 'accepted' "
                "JOIN console_items AS request "
                "ON request.task_id = task.id "
                "AND request.payload->>'type' = 'userMessage' "
                "AND request.payload->>'clientId' = operation.id "
                "JOIN console_items AS final "
                "ON final.task_id = task.id AND final.turn_id = request.turn_id "
                "AND final.payload->>'type' = 'agentMessage' "
                "AND final.payload->>'phase' = 'final_answer' "
                "WHERE task.stage = 'plan' AND task.status = 'idle' "
                "AND length(trim(COALESCE(final.payload->>'text', ''))) > 0 "
                "AND NOT EXISTS ("
                "SELECT 1 FROM console_revisions AS revision "
                "WHERE revision.task_id = task.id AND revision.kind = 'plan'"
                ") "
                "ORDER BY task.id, final.id DESC"
            )
        )
        .mappings()
        .all()
    )
    for row in rows:
        body = _plan_body(row["body"])
        if body is None:
            continue
        connection.execute(
            text(
                "INSERT INTO console_revisions "
                "(task_id, kind, version, body, source_turn_id, created_at) "
                "VALUES (:task_id, 'plan', 1, :body, :turn_id, CURRENT_TIMESTAMP)"
            ),
            {
                "task_id": row["task_id"],
                "body": body[:100000],
                "turn_id": row["turn_id"],
            },
        )


def downgrade():
    # The recovered plan may already have been reviewed or edited. Preserve it.
    pass
