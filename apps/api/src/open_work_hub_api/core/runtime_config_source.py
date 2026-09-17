"""Pydantic's public settings-source extension for repository defaults."""

from pathlib import Path
from typing import Any

from pydantic.fields import FieldInfo
from pydantic_settings import PydanticBaseSettingsSource

from open_work_hub_api.core.runtime_config import runtime_defaults


class RuntimeConfigSettingsSource(PydanticBaseSettingsSource):
    def __init__(self, settings_cls, root: Path):
        super().__init__(settings_cls)
        self.root = root

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        # __call__ resolves the complete, validated config in one read.
        raise NotImplementedError

    def __call__(self) -> dict[str, Any]:
        profile = str(
            self.current_state.get(
                "OPEN_WORK_HUB_ENV_PROFILE", self.current_state.get("env_profile", "")
            )
        )
        values = runtime_defaults(self.root, profile)
        prefix = self.config.get("env_prefix", "")
        result = {}
        for name, field in self.settings_cls.model_fields.items():
            alias = field.validation_alias
            key = alias if isinstance(alias, str) else f"{prefix}{name.upper()}"
            if key in values:
                result[alias if isinstance(alias, str) else name] = values[key]
        return result
