from __future__ import annotations

from typing import Final


# This is an explicit platform retirement contract, not runtime configuration.
# True records that both legacy Knowledge registries have been removed and keeps
# the protected exact-membership checks aligned with that completed transition.
KNOWLEDGE_SOURCE_REGISTRY_RETIRED: Final[bool] = True


__all__ = ["KNOWLEDGE_SOURCE_REGISTRY_RETIRED"]
