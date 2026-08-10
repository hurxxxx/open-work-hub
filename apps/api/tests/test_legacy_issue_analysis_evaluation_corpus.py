from legacy_issue_analysis_evaluation_corpus import QUESTIONS


def test_evaluation_corpus_has_balanced_required_coverage() -> None:
    assert len(QUESTIONS) == 120
    categories = {item.category for item in QUESTIONS}
    assert categories == {
        "checklist",
        "hybrid",
        "safety",
        "scope",
        "semantic",
        "statistics",
        "trend",
    }
    assert sum(item.report for item in QUESTIONS) >= 10
    assert sum("sql" in item.sources for item in QUESTIONS) >= 50
    assert sum(
        "semantic" in item.sources or "hybrid" in item.sources for item in QUESTIONS
    ) >= 30
    assert sum("checklist" in item.sources for item in QUESTIONS) >= 15
