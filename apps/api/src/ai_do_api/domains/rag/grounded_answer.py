from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.orm import Session

from ai_do_api.domains.ai.gateway import (
    AiGatewayContextPack,
    LlmWorkloadContext,
    execute_llm,
)
from ai_do_api.domains.rag.contracts import RagGroundedAnswer, RagGroundedCitation, RagQueryHit
from ai_do_api.domains.rag.grounded_answer_assembly import (
    DEFAULT_GROUNDED_ANSWER_ASSEMBLER,
    GroundedAnswerAssembler,
    clean_text,
    extract_json_object,
    xml_escape,
)


class LlmGroundedAnswerSynthesizer:
    provider_name = "doowon-llm-grounded-answer"

    def __init__(
        self,
        *,
        db: Session,
        workspace_id: str,
        actor_user_id: str | None,
        principal_kind: str,
        principal_id: str | None,
        source: str,
        agent_run_id: str | None = None,
        conversation_id: str | None = None,
        assembler: GroundedAnswerAssembler | None = None,
    ) -> None:
        self._db = db
        self._workspace_id = workspace_id
        self._actor_user_id = actor_user_id
        self._principal_kind = principal_kind
        self._principal_id = principal_id
        self._source = source
        self._agent_run_id = agent_run_id
        self._conversation_id = conversation_id
        self._assembler = assembler or DEFAULT_GROUNDED_ANSWER_ASSEMBLER

    def synthesize(
        self,
        *,
        query: str,
        hits: Sequence[RagQueryHit],
        timeout_ms: int | None = None,
    ) -> RagGroundedAnswer | None:
        if not hits:
            return None

        messages = self._assembler.build_messages(query=query, hits=hits)
        completion = execute_llm(
            "rag_grounded_answer",
            LlmWorkloadContext(
                workspace_id=self._workspace_id,
                source=self._source,
                actor_user_id=self._actor_user_id,
                app_id="rag",
                principal_kind=self._principal_kind,  # type: ignore[arg-type]
                principal_id=self._principal_id,
            ),
            self._db,
            messages=messages,
            context_pack=AiGatewayContextPack(
                messages=messages,
                context_strategy="rag_grounded_answer_evidence",
                source_kinds=_source_kinds_from_hits(hits),
                sensitivity_labels=("internal",),
                content_origin="internal_context",
            ),
            temperature=0,
            reasoning_effort="none",
            timeout_seconds=self._assembler.timeout_seconds_from_ms(timeout_ms),
            agent_run_id=self._agent_run_id,
            conversation_id=self._conversation_id,
        ).completion
        if completion.finish_reason and completion.finish_reason != "stop":
            raise ValueError(
                f"Grounded answer provider did not finish cleanly: {completion.finish_reason}"
            )
        raw_content = completion.text.strip()
        return self._assembler.assemble(raw_content=raw_content, hits=hits)


def _grounded_answer_messages(
    *,
    query: str,
    hits: Sequence[RagQueryHit],
) -> list[dict[str, str]]:
    return DEFAULT_GROUNDED_ANSWER_ASSEMBLER.build_messages(query=query, hits=hits)


def _source_kinds_from_hits(hits: Sequence[RagQueryHit]) -> tuple[str, ...]:
    return tuple(sorted({hit.source_kind for hit in hits if hit.source_kind}))


def _citation_from_hit(hit: RagQueryHit) -> RagGroundedCitation:
    return DEFAULT_GROUNDED_ANSWER_ASSEMBLER.citation_from_hit(hit)


def _extract_json_object(content: str) -> str:
    return extract_json_object(content)


def _clean_text(value: str | None, *, max_chars: int | None = None) -> str:
    return clean_text(value, max_chars=max_chars)


def _xml_escape(value: str) -> str:
    return xml_escape(value)


def _timeout_seconds_from_ms(timeout_ms: int | None) -> float | None:
    return DEFAULT_GROUNDED_ANSWER_ASSEMBLER.timeout_seconds_from_ms(timeout_ms)
