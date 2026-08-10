from __future__ import annotations

from ai_do_api.core.i18n import localized_http_exception

LEGACY_ISSUE_COMPRESSOR_MODULE_KEYS = frozenset(
    {
        "compressor-electric",
        "compressor-mechanical",
    }
)
LEGACY_ISSUE_MODULE_KEYS = frozenset(
    {
        "aircon",
        *LEGACY_ISSUE_COMPRESSOR_MODULE_KEYS,
        "heat-exchanger",
        "interior",
        "cooling-module",
        "electrical-mechanical",
        "electrical-control-hw",
        "electrical-control-sw",
    }
)


def require_compressor_module_enabled(
    module_key: str | None,
    *,
    compressor_enabled: bool,
) -> None:
    """Reject compressor module access when the caller's injected gate is disabled.

    The app domain deliberately accepts the boolean as an argument instead of reading
    runtime settings. Core composition can inject the platform-owned feature flag at
    the API boundary without coupling this module to protected configuration.
    """

    normalized_module_key = (module_key or "").strip()
    if normalized_module_key in LEGACY_ISSUE_COMPRESSOR_MODULE_KEYS and not compressor_enabled:
        raise localized_http_exception(
            status_code=404,
            code="legacy_issues.module_not_found",
        )


def enabled_legacy_issue_module_keys(*, compressor_enabled: bool) -> frozenset[str]:
    if compressor_enabled:
        return LEGACY_ISSUE_MODULE_KEYS
    return LEGACY_ISSUE_MODULE_KEYS.difference(LEGACY_ISSUE_COMPRESSOR_MODULE_KEYS)
