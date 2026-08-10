"""Patent prior-art app identity and registered AI workloads."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_do_api.domains.ai.registry import AiCapabilityRegistry


PATENT_PRIOR_ART_APP_ID = "patent-prior-art"
PATENT_PRIOR_ART_SEARCH_PLAN_WORKLOAD_ID = "patent_prior_art.search_plan"
PATENT_PRIOR_ART_SEARCH_PLAN_TASK_KIND = "patent_prior_art_search_plan"
PATENT_PRIOR_ART_CANDIDATE_ASSESSMENT_WORKLOAD_ID = "patent_prior_art.candidate_assessment"
PATENT_PRIOR_ART_CANDIDATE_ASSESSMENT_TASK_KIND = "patent_prior_art_candidate_assessment"


def register_ai_capabilities(registry: AiCapabilityRegistry) -> None:
    registrations = (
        (
            PATENT_PRIOR_ART_SEARCH_PLAN_WORKLOAD_ID,
            PATENT_PRIOR_ART_SEARCH_PLAN_TASK_KIND,
            "Create a provider-neutral patent search plan from user-supplied invention scope.",
            "patentPriorArtSearchPlan",
        ),
        (
            PATENT_PRIOR_ART_CANDIDATE_ASSESSMENT_WORKLOAD_ID,
            PATENT_PRIOR_ART_CANDIDATE_ASSESSMENT_TASK_KIND,
            "Assess prior-art candidates against the supplied invention using bounded technical evidence.",
            "patentPriorArtCandidateAssessment",
        ),
    )
    for workload_id, task_kind, description, catalog_key in registrations:
        registry.register_llm_workload(
            workload_id=workload_id,
            task_kind=task_kind,
            owner_domain="patent-prior-art",
            app_id=PATENT_PRIOR_ART_APP_ID,
            description=description,
            default_route="local",
            execution_kind="chat",
            allowed_routes=("local", "external"),
            required_capabilities=("chat",),
            model_roles=("default",),
            label_key=(
                f"admin.console.aiSecurity.modelSettings.workloadCatalog.{catalog_key}.label"
            ),
            description_key=(
                f"admin.console.aiSecurity.modelSettings.workloadCatalog.{catalog_key}.description"
            ),
            external_data=True,
            local_max_output_tokens=8_192,
            external_max_output_tokens=8_192,
        )


__all__ = [
    "PATENT_PRIOR_ART_APP_ID",
    "PATENT_PRIOR_ART_CANDIDATE_ASSESSMENT_TASK_KIND",
    "PATENT_PRIOR_ART_CANDIDATE_ASSESSMENT_WORKLOAD_ID",
    "PATENT_PRIOR_ART_SEARCH_PLAN_TASK_KIND",
    "PATENT_PRIOR_ART_SEARCH_PLAN_WORKLOAD_ID",
    "register_ai_capabilities",
]
