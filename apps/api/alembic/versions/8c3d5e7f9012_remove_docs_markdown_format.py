"""remove_docs_markdown_format

Revision ID: 8c3d5e7f9012
Revises: 7b2c4d6e8f90
Create Date: 2026-05-18 16:10:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from alembic import op
import sqlalchemy as sa


revision: str = "8c3d5e7f9012"
down_revision: str | Sequence[str] | None = "7b2c4d6e8f90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


docs_native_docs = sa.table(
    "docs_native_docs",
    sa.column("id", sa.String()),
    sa.column("content_format", sa.String()),
)

docs_native_doc_pages = sa.table(
    "docs_native_doc_pages",
    sa.column("id", sa.String()),
    sa.column("doc_id", sa.String()),
    sa.column("content_blocks", sa.JSON()),
    sa.column("content_text", sa.Text()),
)


def _text_node(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def _paragraph_block(text: str) -> dict[str, Any]:
    return {"type": "paragraph", "content": [_text_node(text)]}


def _heading_block(text: str, *, level: int) -> dict[str, Any]:
    return {"type": "heading", "props": {"level": level}, "content": [_text_node(text)]}


def _list_item_block(block_type: str, text: str, *, checked: bool | None = None) -> dict[str, Any]:
    block: dict[str, Any] = {"type": block_type, "content": [_text_node(text)]}
    if checked is not None:
        block["props"] = {"checked": checked}
    return block


def _markdown_to_blocks(content_markdown: str | None) -> list[dict[str, Any]]:
    if not content_markdown:
        return []
    blocks: list[dict[str, Any]] = []
    for raw_line in content_markdown.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("### "):
            blocks.append(_heading_block(line[4:].strip(), level=3))
        elif line.startswith("## "):
            blocks.append(_heading_block(line[3:].strip(), level=2))
        elif line.startswith("# "):
            blocks.append(_heading_block(line[2:].strip(), level=1))
        elif line.startswith("- [ ] "):
            blocks.append(_list_item_block("checkListItem", line[6:].strip(), checked=False))
        elif line.startswith("- [x] ") or line.startswith("- [X] "):
            blocks.append(_list_item_block("checkListItem", line[6:].strip(), checked=True))
        elif line.startswith("- ") or line.startswith("* "):
            blocks.append(_list_item_block("bulletListItem", line[2:].strip()))
        elif len(line) > 3 and line[0].isdigit() and ". " in line[:4]:
            blocks.append(_list_item_block("numberedListItem", line.split(". ", 1)[1].strip()))
        else:
            blocks.append(_paragraph_block(line))
    return blocks


def upgrade() -> None:
    bind = op.get_bind()
    markdown_docs = bind.execute(
        sa.select(docs_native_docs.c.id).where(docs_native_docs.c.content_format == "markdown")
    ).all()
    for (doc_id,) in markdown_docs:
        pages = bind.execute(
            sa.select(
                docs_native_doc_pages.c.id,
                docs_native_doc_pages.c.content_text,
            ).where(docs_native_doc_pages.c.doc_id == doc_id)
        ).all()
        for page_id, content_text in pages:
            bind.execute(
                docs_native_doc_pages.update()
                .where(docs_native_doc_pages.c.id == page_id)
                .values(
                    content_blocks=_markdown_to_blocks(content_text),
                )
            )
    bind.execute(
        docs_native_docs.update()
        .where(docs_native_docs.c.content_format == "markdown")
        .values(content_format="block")
    )

    op.drop_constraint("ck_docs_native_docs_content_format", "docs_native_docs", type_="check")
    op.create_check_constraint(
        "ck_docs_native_docs_content_format",
        "docs_native_docs",
        "content_format IN ('block', 'html')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_docs_native_docs_content_format", "docs_native_docs", type_="check")
    op.create_check_constraint(
        "ck_docs_native_docs_content_format",
        "docs_native_docs",
        "content_format IN ('block', 'html', 'markdown')",
    )
