"""Files retrieval activation gates.

The process-local operator gate admits Files adapters and projection hooks.
Every query and write still has to resolve one independently validated,
partition-aware OpenSearch/Qdrant generation pair from PostgreSQL. Keeping the
gates separate makes emergency shutdown immediate after a process restart while
preventing a legacy backend fallback when the control plane is incomplete.
"""

from open_work_hub_api.core.settings import get_settings


def files_retrieval_active_for_environment(
    *,
    environment: str,
    env_profile: str,
    rag_enabled: bool,
    operator_enabled: bool = False,
    partition_generation_ready: bool = False,
) -> bool:
    # Retain the environment arguments for the public activation-test helper,
    # but do not special-case development: production uses the same two-gate
    # contract and is closed by default through the operator setting.
    del environment, env_profile
    return operator_enabled and partition_generation_ready and rag_enabled


_settings = get_settings()
FILES_RETRIEVAL_ACTIVE = files_retrieval_active_for_environment(
    environment=_settings.environment,
    env_profile=_settings.env_profile,
    rag_enabled=_settings.rag_enabled,
    operator_enabled=_settings.files_retrieval_enabled,
    # Adapter registration is the process-local operator admission gate. The
    # dynamic PostgreSQL generation pair is required again by query/write
    # composition roots before any backend access.
    partition_generation_ready=True,
)
FILES_RAG_SOURCE_KIND = "files"


__all__ = [
    "FILES_RAG_SOURCE_KIND",
    "FILES_RETRIEVAL_ACTIVE",
    "files_retrieval_active_for_environment",
]
