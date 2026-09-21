"""Backfill completed native plan items that predate direct plan projection."""

import json

from alembic import op
from sqlalchemy import text

revision = "console_0007"
down_revision = "console_0006"
branch_labels = None
depends_on = None


def _plan_body(value: str) -> str:
    try:
        structured = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value
    if not isinstance(structured, dict) or not isinstance(structured.get("answer"), str):
        return value
    documents = structured.get("documents")
    if isinstance(documents, list):
        for document in documents:
            if (
                isinstance(document, dict)
                and document.get("kind") == "plan"
                and isinstance(document.get("body"), str)
                and document["body"].strip()
            ):
                return document["body"]
    return structured["answer"]


def upgrade():
    connection = op.get_bind()
    rows = (
        connection.execute(
            text(
                "SELECT DISTINCT ON (item.task_id) item.task_id, item.turn_id, "
                "item.payload->>'text' AS body "
                "FROM console_items AS item "
                "JOIN console_tasks AS task ON task.id = item.task_id "
                "WHERE task.status = 'idle' "
                "AND item.payload->>'type' = 'plan' "
                "AND length(trim(COALESCE(item.payload->>'text', ''))) > 0 "
                "AND NOT EXISTS ("
                "SELECT 1 FROM console_revisions AS revision "
                "WHERE revision.task_id = item.task_id AND revision.kind = 'plan'"
                ") "
                "ORDER BY item.task_id, item.id DESC"
            )
        )
        .mappings()
        .all()
    )
    for row in rows:
        body = _plan_body(row["body"]).strip()
        if not body:
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
    # A backfilled plan may already have been reviewed or edited. Preserve it.
    pass
