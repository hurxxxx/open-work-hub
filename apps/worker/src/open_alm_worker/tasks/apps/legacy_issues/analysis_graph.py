from __future__ import annotations

from open_alm_api.domains.ai_graph.execution_registry import register_ai_graph_executor
from open_alm_api.domains.legacy_issues.analysis_graph.runtime import (
    execute_legacy_issue_analysis_graph,
)
from open_alm_api.domains.legacy_issues.analysis_graph.topology import (
    LEGACY_ISSUE_ANALYSIS_GRAPH_ID,
    LEGACY_ISSUE_ANALYSIS_GRAPH_VERSION,
)


register_ai_graph_executor(
    LEGACY_ISSUE_ANALYSIS_GRAPH_ID,
    LEGACY_ISSUE_ANALYSIS_GRAPH_VERSION,
    execute_legacy_issue_analysis_graph,
)
