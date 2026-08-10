from __future__ import annotations

import runpy
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE = runpy.run_path(str(ROOT / "scripts" / "check-alembic-state.py"))


class CheckAlembicStateTest(unittest.TestCase):
    def write_migration(
        self,
        api_root: Path,
        filename: str,
        revision: str,
        down_revision: str,
    ) -> None:
        versions = api_root / "alembic" / "versions"
        versions.mkdir(parents=True, exist_ok=True)
        (versions / filename).write_text(
            f'revision: str = "{revision}"\n'
            f"down_revision: str | tuple[str, ...] | None = {down_revision}\n"
            "branch_labels: str | tuple[str, ...] | None = None\n"
            "depends_on: str | tuple[str, ...] | None = None\n",
            encoding="utf-8",
        )

    def test_parse_revision_assignment_supports_typed_assignment(self) -> None:
        parse_revision_assignment = MODULE["parse_revision_assignment"]

        self.assertEqual(
            parse_revision_assignment('revision: str = "d9f0a1b2c3d4"\n'),
            "d9f0a1b2c3d4",
        )

    def test_collect_revision_files_reports_duplicate_ids(self) -> None:
        validate_unique_revision_ids = MODULE["validate_unique_revision_ids"]

        with tempfile.TemporaryDirectory() as directory:
            api_root = Path(directory)
            versions = api_root / "alembic" / "versions"
            versions.mkdir(parents=True)
            (versions / "a_first.py").write_text('revision = "abc123"\n', encoding="utf-8")
            (versions / "b_second.py").write_text('revision: str = "abc123"\n', encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "Duplicate Alembic revision"):
                validate_unique_revision_ids(api_root)

    def test_extract_revision_lines_ignores_alembic_info_logs(self) -> None:
        extract_revision_lines = MODULE["extract_revision_lines"]

        self.assertEqual(
            extract_revision_lines(
                "\n".join(
                    [
                        "INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.",
                        "d9f0a1b2c3d4 (head)",
                    ]
                )
            ),
            ["d9f0a1b2c3d4"],
        )

    def test_static_graph_accepts_linear_chain_and_merge_revision(self) -> None:
        validate_static_revision_graph = MODULE["validate_static_revision_graph"]

        with tempfile.TemporaryDirectory() as directory:
            api_root = Path(directory)
            self.write_migration(api_root, "a.py", "a1", "None")
            self.write_migration(api_root, "b.py", "b1", '"a1"')
            self.write_migration(api_root, "c.py", "c1", '"a1"')
            self.write_migration(api_root, "merge.py", "d1", '("b1", "c1")')

            self.assertEqual(validate_static_revision_graph(api_root), "d1")

    def test_static_graph_rejects_multiple_heads(self) -> None:
        validate_static_revision_graph = MODULE["validate_static_revision_graph"]

        with tempfile.TemporaryDirectory() as directory:
            api_root = Path(directory)
            self.write_migration(api_root, "a.py", "a1", "None")
            self.write_migration(api_root, "b.py", "b1", '"a1"')
            self.write_migration(api_root, "c.py", "c1", '"a1"')

            with self.assertRaisesRegex(RuntimeError, "exactly one static Alembic head"):
                validate_static_revision_graph(api_root)

    def test_static_graph_rejects_missing_parent(self) -> None:
        validate_static_revision_graph = MODULE["validate_static_revision_graph"]

        with tempfile.TemporaryDirectory() as directory:
            api_root = Path(directory)
            self.write_migration(api_root, "a.py", "a1", '"missing"')

            with self.assertRaisesRegex(RuntimeError, "missing revisions"):
                validate_static_revision_graph(api_root)

    def test_static_graph_rejects_cycle(self) -> None:
        validate_static_revision_graph = MODULE["validate_static_revision_graph"]

        with tempfile.TemporaryDirectory() as directory:
            api_root = Path(directory)
            self.write_migration(api_root, "a.py", "a1", '"b1"')
            self.write_migration(api_root, "b.py", "b1", '"a1"')

            with self.assertRaisesRegex(RuntimeError, "cycle detected"):
                validate_static_revision_graph(api_root)

    def test_static_graph_rejects_missing_dependency(self) -> None:
        validate_static_revision_graph = MODULE["validate_static_revision_graph"]

        with tempfile.TemporaryDirectory() as directory:
            api_root = Path(directory)
            self.write_migration(api_root, "a.py", "a1", "None")
            migration = api_root / "alembic" / "versions" / "a.py"
            migration.write_text(
                migration.read_text(encoding="utf-8").replace(
                    "depends_on: str | tuple[str, ...] | None = None",
                    'depends_on: str | tuple[str, ...] | None = "missing"',
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(RuntimeError, "depends_on: missing"):
                validate_static_revision_graph(api_root)

    def test_static_graph_rejects_branch_labels(self) -> None:
        validate_static_revision_graph = MODULE["validate_static_revision_graph"]

        with tempfile.TemporaryDirectory() as directory:
            api_root = Path(directory)
            self.write_migration(api_root, "a.py", "a1", "None")
            migration = api_root / "alembic" / "versions" / "a.py"
            migration.write_text(
                migration.read_text(encoding="utf-8").replace(
                    "branch_labels: str | tuple[str, ...] | None = None",
                    'branch_labels: str | tuple[str, ...] | None = "shared"',
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(RuntimeError, "branch_labels must be None"):
                validate_static_revision_graph(api_root)


if __name__ == "__main__":
    unittest.main()
