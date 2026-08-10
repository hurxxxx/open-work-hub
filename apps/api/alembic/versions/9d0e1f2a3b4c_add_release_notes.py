"""add_release_notes

Revision ID: 9d0e1f2a3b4c
Revises: 8b9c0d1e2f3a
Create Date: 2026-06-15 00:00:00.000000

"""

from __future__ import annotations

from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9d0e1f2a3b4c"
down_revision: Union[str, Sequence[str], None] = "8b9c0d1e2f3a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RELEASE_NOTE_ID = "20260615-0000-4000-8000-000000000001"
RELEASE_KEY = "2026-06-15-prod"


def upgrade() -> None:
    op.create_table(
        "release_notes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("release_key", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("release_key", name="uq_release_notes_release_key"),
    )
    op.create_index(
        "ix_release_notes_status_published",
        "release_notes",
        ["status", "published_at"],
    )
    op.create_table(
        "release_note_reads",
        sa.Column("release_note_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("dismissed_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["release_note_id"],
            ["release_notes.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("release_note_id", "user_id"),
    )
    op.create_index(
        "ix_release_note_reads_user_dismissed",
        "release_note_reads",
        ["user_id", "dismissed_at"],
    )

    release_notes = sa.table(
        "release_notes",
        sa.column("id", sa.String()),
        sa.column("release_key", sa.String()),
        sa.column("title", sa.String()),
        sa.column("summary", sa.String()),
        sa.column("body", sa.Text()),
        sa.column("status", sa.String()),
        sa.column("published_at", sa.DateTime()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    now = datetime(2026, 6, 15, 0, 0, 0)
    op.bulk_insert(
        release_notes,
        [
            {
                "id": RELEASE_NOTE_ID,
                "release_key": RELEASE_KEY,
                "title": "2026년 6월 15일 업데이트",
                "summary": "PMS 간트 사용성, 태스크 등록자 표시, 첨부파일 다운로드 안정성을 개선했습니다.",
                "body": "\n".join(
                    [
                        "📌 PMS 간트차트에서 상위/하위 태스크를 더 쉽게 구분할 수 있습니다.",
                        "하위 태스크가 있는 항목은 접어서 필요한 일정만 볼 수 있습니다.",
                        "업무 진행 상태를 간트 바 색상으로 더 쉽게 확인할 수 있습니다.",
                        "간트 일정 기간을 드래그로 조정할 때 화면이 잠시 되돌아가 보이던 현상을 개선했습니다.",
                        "간트 화면에서 태스크 이름이나 일정 바를 클릭하면 상세 내용을 바로 확인하고 편집할 수 있습니다.",
                        "PMS 목록에서 태스크를 등록한 사용자를 확인할 수 있습니다.",
                        "📎 PMS와 회의에서 첨부파일 다운로드가 되지 않던 현상을 개선했습니다.",
                    ]
                ),
                "status": "published",
                "published_at": now,
                "created_at": now,
                "updated_at": now,
            }
        ],
    )


def downgrade() -> None:
    op.execute(
        sa.text("delete from release_notes where release_key = :release_key").bindparams(
            release_key=RELEASE_KEY
        )
    )
    op.drop_index(
        "ix_release_note_reads_user_dismissed",
        table_name="release_note_reads",
    )
    op.drop_table("release_note_reads")
    op.drop_index("ix_release_notes_status_published", table_name="release_notes")
    op.drop_table("release_notes")
