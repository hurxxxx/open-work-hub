class LlmRuntimeError(RuntimeError):
    """Provider-neutral failure exposed by high-level LLM helpers."""


class LlmProviderError(LlmRuntimeError):
    """Provider or provider-SDK failure normalized at the adapter seam."""

    def __init__(
        self,
        message: str,
        *,
        pool: str | None = None,
        provider: str | None = None,
    ) -> None:
        super().__init__(message)
        self.pool = pool
        self.provider = provider
