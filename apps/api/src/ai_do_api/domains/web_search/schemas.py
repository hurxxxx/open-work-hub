from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class WebSearchAskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(..., min_length=1, max_length=4000)
    max_uses: int = Field(default=5, ge=1, le=20)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=36)


class WebSearchCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    title: str
    cited_text: str | None = None


class WebSearchUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: int | None = None
    output_tokens: int | None = None
    web_search_requests: int | None = None


class WebSearchAnswerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    answer: str
    citations: list[WebSearchCitation] = Field(default_factory=list)
    model: str
    usage: WebSearchUsage | None = None
    conversation_id: str | None = None
