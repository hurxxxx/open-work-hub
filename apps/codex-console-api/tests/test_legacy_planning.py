from importlib.util import module_from_spec, spec_from_file_location
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from conftest import new_task, send_message
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from codex_console import store
from codex_console.cli import ROOT
from codex_console.models import Operation, Revision, Task


@pytest.mark.parametrize("kind", ["requirements", "plan", "chat"])
@pytest.mark.parametrize("proof", ["turn_id", "client_id", "unrelated"])
def test_pre_structured_migration_recovers_only_original_completed_document(client, kind, proof):
    task = send_message(client, new_task(client)).json()
    engine = client.app.state.factory.kw["bind"]
    spec = spec_from_file_location(
        "planning_migration", ROOT / "migrations/versions/0005_planning.py"
    )
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.connect() as connection, connection.begin() as transaction:
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
            connection.execute(
                text("UPDATE console_tasks SET stage = :kind WHERE id = :id"),
                {"kind": kind, "id": task["id"]},
            )
            connection.execute(
                text("UPDATE console_operations SET kind = :kind WHERE task_id = :id"),
                {"kind": kind, "id": task["id"]},
            )
            migration.upgrade()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
            row = db.get(Task, task["id"])
            operation = db.get(Operation, row.current_operation_id)
            assert row.stage == "plan"
            assert operation.kind == ("legacy_plan" if kind == "plan" else kind)
            if proof != "turn_id":
                row.turn_id = None
            turns = [
                {
                    "id": task["turn_id"],
                    "status": "completed",
                    "items": [
                        {
                            "type": "userMessage",
                            "clientId": operation.id if proof == "client_id" else str(uuid4()),
                        },
                        {
                            "type": "agentMessage",
                            "phase": "final_answer",
                            "text": "# Original Markdown document",
                        },
                    ],
                }
            ]
            store.recover_document(db, row, turns)
            store.recover_document(db, row, turns)
            docs = list(db.scalars(select(Revision).where(Revision.task_id == row.id)))
            expected = kind != "chat" and proof != "unrelated"
            assert len(docs) == int(expected)
            if expected:
                assert docs[0].kind == kind
                assert docs[0].body == "# Original Markdown document"
                assert docs[0].source_turn_id == task["turn_id"]
            assert row.error_code is None
        transaction.rollback()


def test_plain_agent_answer_is_ignored_and_legacy_recovery_preserves_user_edit(client):
    task = send_message(client, new_task(client)).json()
    with client.app.state.factory.begin() as db:
        row = db.get(Task, task["id"])
        turns = [
            {
                "id": row.turn_id,
                "status": "completed",
                "items": [
                    {
                        "type": "agentMessage",
                        "phase": "final_answer",
                        "text": "# Not a structured response",
                    },
                ],
            }
        ]
        store.recover_document(db, row, turns)
        assert row.error_code is None
        assert not list(db.scalars(select(Revision).where(Revision.task_id == row.id)))
        db.get(Operation, row.current_operation_id).kind = "legacy_plan"
        store.save_revision(db, row, "plan", "A later owner edit")
        store.recover_document(db, row, turns)
        assert [r.body for r in db.scalars(select(Revision).where(Revision.task_id == row.id))] == [
            "A later owner edit"
        ]
