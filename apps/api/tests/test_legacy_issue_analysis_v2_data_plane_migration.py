from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from ai_do_api.domains.legacy_issues.analysis_v2.views import (
    ANALYSIS_VIEW_CONTRACTS,
    CHECKLIST_ITEMS_VIEW_V1,
    CHECKLISTS_VIEW_V1,
    ISSUE_RECORDS_VIEW_V1,
)


_MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "b5f8d3a1c7e4_add_legacy_issue_analysis_v2_data_plane.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "legacy_issue_analysis_v2_data_plane_migration",
        _MIGRATION_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_view_columns_match_the_public_recipe_contracts() -> None:
    migration = _load_migration()

    assert len(migration.ISSUE_VIEW_COLUMNS) == len(
        set(migration.ISSUE_VIEW_COLUMNS)
    )
    assert len(migration.CHECKLIST_VIEW_COLUMNS) == len(
        set(migration.CHECKLIST_VIEW_COLUMNS)
    )
    assert len(migration.CHECKLIST_ITEM_VIEW_COLUMNS) == len(
        set(migration.CHECKLIST_ITEM_VIEW_COLUMNS)
    )
    assert frozenset(migration.ISSUE_VIEW_COLUMNS) == ANALYSIS_VIEW_CONTRACTS[
        ISSUE_RECORDS_VIEW_V1
    ].columns
    assert frozenset(migration.CHECKLIST_VIEW_COLUMNS) == ANALYSIS_VIEW_CONTRACTS[
        CHECKLISTS_VIEW_V1
    ].columns
    assert frozenset(
        migration.CHECKLIST_ITEM_VIEW_COLUMNS
    ) == ANALYSIS_VIEW_CONTRACTS[CHECKLIST_ITEMS_VIEW_V1].columns


def test_migration_is_fail_closed_and_matches_the_llamaindex_table_contract() -> None:
    migration = _load_migration()
    source = _MIGRATION_PATH.read_text(encoding="utf-8")

    assert migration.down_revision == "a4e7c2f9d1b6"
    assert migration.VECTOR_TABLE == "data_analysis_nodes_v1"
    assert migration.VECTOR_DIMENSIONS == 1024
    assert "security_barrier = true, security_invoker = true" in source
    assert "SECURITY DEFINER" in source
    assert (
        "SET search_path = pg_catalog, public, {ANALYSIS_SCHEMA}" in source
    )
    assert '"legacy_issue_records"' in source
    assert '"REVOKE ALL ON TABLE "' in source
    assert "CREATE INDEX data_analysis_nodes_v1_embedding_idx" in source
    assert "chunks.embedding_status = 'embedded'" in source
    assert "chunks.embedding_dimensions = 1024" in source
    assert "try_vector_1024_v1" in source
    assert "must be " in source
    assert "'pre-provisioned before this migration'" in source
