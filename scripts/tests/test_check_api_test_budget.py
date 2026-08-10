from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "check-api-test-budget.py"
SPEC = importlib.util.spec_from_file_location("check_api_test_budget", MODULE_PATH)
api_budget = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = api_budget
assert SPEC.loader is not None
SPEC.loader.exec_module(api_budget)


def collected(
    nodeid: str,
    *,
    markers: tuple[str, ...] = (),
    fixtures: tuple[str, ...] = (),
):
    return api_budget.CollectedApiTest(
        nodeid=nodeid,
        markers=markers,
        fixture_closure=fixtures,
    )


class ApiTestBudgetCheckerTest(unittest.TestCase):
    def test_classifies_lanes_and_transitive_db_fixture_use(self) -> None:
        report = api_budget.evaluate_api_test_budget(
            [
                collected("tests/test_z.py::test_standard"),
                collected(
                    "tests/test_a.py::test_external",
                    markers=("external_integration",),
                    fixtures=("client", "application_postgres_dsn"),
                ),
                collected(
                    "tests/test_b.py::test_slow",
                    markers=("slow",),
                    fixtures=("application_postgres_state",),
                ),
                collected(
                    "tests/test_c.py::test_migration",
                    markers=("migration",),
                    fixtures=("postgres_dsn",),
                ),
            ]
        )

        self.assertTrue(report["ok"])
        self.assertEqual(
            report["counts"],
            {
                "total": 4,
                "standard": 1,
                "slow": 1,
                "migration": 1,
                "external": 1,
                "dbTestClientFixtureClosure": 3,
            },
        )
        self.assertEqual(
            report["lanes"]["external"],
            ["tests/test_a.py::test_external"],
        )
        self.assertEqual(
            report["dbTestClientFixtureClosure"]["items"],
            [
                "tests/test_a.py::test_external",
                "tests/test_b.py::test_slow",
                "tests/test_c.py::test_migration",
            ],
        )

    def test_reports_every_exceeded_budget_deterministically(self) -> None:
        budgets = {
            "total": 1,
            "standard": 0,
            "slow": 0,
            "migration": 0,
            "external": 0,
            "dbTestClientFixtureClosure": 0,
        }
        report = api_budget.evaluate_api_test_budget(
            [
                collected("tests/test_b.py::test_standard", fixtures=("client",)),
                collected("tests/test_a.py::test_slow", markers=("slow",)),
            ],
            budgets=budgets,
        )

        self.assertFalse(report["ok"])
        self.assertEqual(
            [violation["metric"] for violation in report["violations"]],
            ["total", "standard", "slow", "dbTestClientFixtureClosure"],
        )
        self.assertEqual(
            report["lanes"]["standard"],
            ["tests/test_b.py::test_standard"],
        )

    def test_rejects_lane_overlap_and_collection_failure(self) -> None:
        report = api_budget.evaluate_api_test_budget(
            [
                collected(
                    "tests/test_contract.py::test_one",
                    markers=("slow", "external_integration"),
                )
            ],
            collection_errors=["tests/test_broken.py", "tests/test_broken.py"],
            collection_exit_code=2,
        )

        self.assertFalse(report["ok"])
        self.assertEqual(
            report["laneOverlaps"],
            [
                {
                    "nodeid": "tests/test_contract.py::test_one",
                    "lanes": ["slow", "external"],
                }
            ],
        )
        self.assertEqual(
            report["collection"],
            {"exitCode": 2, "errors": ["tests/test_broken.py"]},
        )
        self.assertEqual(
            [violation["kind"] for violation in report["violations"]],
            ["laneOverlap", "collection"],
        )

    def test_critical_budget_preserves_full_inventory_and_rejects_missing_nodeids(
        self,
    ) -> None:
        items = [
            collected("tests/test_a.py::test_standard"),
            collected(
                "tests/test_b.py::test_external",
                markers=("external_integration",),
            ),
        ]

        original_minimums = api_budget.FULL_INVENTORY_MINIMUMS
        api_budget.FULL_INVENTORY_MINIMUMS = {
            "total": 2,
            "standard": 1,
            "slow": 0,
            "migration": 0,
            "external": 1,
            "dbTestClientFixtureClosure": 0,
        }
        original_critical_minimums = api_budget.DEFAULT_MINIMUMS
        api_budget.DEFAULT_MINIMUMS = {
            "total": 1,
            "standard": 1,
            "slow": 0,
            "migration": 0,
            "external": 0,
            "dbTestClientFixtureClosure": 0,
        }
        try:
            report = api_budget.evaluate_critical_api_test_budget(
                items,
                [
                    "tests/test_a.py::test_standard",
                    "tests/test_missing.py::test_removed",
                ],
            )
        finally:
            api_budget.FULL_INVENTORY_MINIMUMS = original_minimums
            api_budget.DEFAULT_MINIMUMS = original_critical_minimums

        self.assertFalse(report["ok"])
        self.assertEqual(report["counts"]["total"], 1)
        self.assertEqual(report["fullInventory"]["counts"]["total"], 2)
        self.assertEqual(
            report["criticalManifest"]["missingNodeids"],
            ["tests/test_missing.py::test_removed"],
        )
        self.assertEqual(report["violations"], [
            {
                "kind": "manifest",
                "missingNodeids": ["tests/test_missing.py::test_removed"],
            }
        ])


if __name__ == "__main__":
    unittest.main()
