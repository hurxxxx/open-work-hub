from __future__ import annotations

import json
import re
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from aidoo_api.core.llm import LlmTaskContext, complete_chat
from aidoo_api.domains.rag.contracts import RagGroundedAnswer, RagGroundedCitation, RagQueryHit


class _GroundedAnswerStatement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=1)
    citation_indexes: list[int] = Field(default_factory=list)


class _GroundedAnswerEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statements: list[_GroundedAnswerStatement] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)


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
    ) -> None:
        self._db = db
        self._workspace_id = workspace_id
        self._actor_user_id = actor_user_id
        self._principal_kind = principal_kind
        self._principal_id = principal_id
        self._source = source
        self._agent_run_id = agent_run_id
        self._conversation_id = conversation_id

    def synthesize(
        self,
        *,
        query: str,
        hits: Sequence[RagQueryHit],
        timeout_ms: int | None = None,
    ) -> RagGroundedAnswer | None:
        if not hits:
            return None

        response, _decision, _config = complete_chat(
            LlmTaskContext(
                source=self._source,
                workspace_id=self._workspace_id,
                task_kind="rag_grounded_answer",
                actor_user_id=self._actor_user_id,
                principal_kind=self._principal_kind,
                principal_id=self._principal_id,
            ),
            self._db,
            messages=_grounded_answer_messages(query=query, hits=hits),
            temperature=0,
            max_tokens=1200,
            reasoning_effort="none",
            timeout_seconds=_timeout_seconds_from_ms(timeout_ms),
            agent_run_id=self._agent_run_id,
            conversation_id=self._conversation_id,
        )
        raw_content = (response.choices[0].message.content or "").strip()
        parsed = _GroundedAnswerEnvelope.model_validate(
            json.loads(_extract_json_object(raw_content))
        )

        statements: list[str] = []
        used_indexes: list[int] = []
        seen_indexes: set[int] = set()
        for statement in parsed.statements:
            cleaned_text = _clean_text(statement.text)
            indexes = [
                index
                for index in statement.citation_indexes
                if isinstance(index, int) and 1 <= index <= len(hits)
            ]
            if not cleaned_text or not indexes:
                continue
            statements.append(cleaned_text)
            for index in indexes:
                if index in seen_indexes:
                    continue
                seen_indexes.add(index)
                used_indexes.append(index)

        if not statements or not used_indexes:
            return None

        citations = [_citation_from_hit(hits[index - 1]) for index in used_indexes]
        return RagGroundedAnswer(
            text="\n".join(statements),
            citations=citations,
            unsupported_claims=[
                cleaned
                for claim in parsed.unsupported_claims
                if (cleaned := _clean_text(claim))
            ],
            sources_used=sorted({citation.source_kind for citation in citations}),
        )


def _grounded_answer_messages(
    *,
    query: str,
    hits: Sequence[RagQueryHit],
) -> list[dict[str, str]]:
    evidence_blocks: list[str] = []
    for index, hit in enumerate(hits[:8], start=1):
        evidence_blocks.append(
            "\n".join(
                [
                    f"<evidence index=\"{index}\">",
                    f"<source_kind>{_xml_escape(hit.source_kind)}</source_kind>",
                    f"<resource_id>{_xml_escape(hit.resource_id)}</resource_id>",
                    f"<title>{_xml_escape(_clean_text(hit.title or ''))}</title>",
                    f"<summary>{_xml_escape(_clean_text(hit.summary or ''))}</summary>",
                    f"<citation>{_xml_escape(_clean_text(hit.citation or ''))}</citation>",
                    "</evidence>",
                ]
            )
        )

    return [
        {
            "role": "system",
            "content": (
                "You write grounded answers from retrieval evidence only. "
                "Never add facts that are not explicitly supported by the evidence. "
                "Return JSON only with this schema: "
                '{"statements":[{"text":"...","citation_indexes":[1]}],'
                '"unsupported_claims":["..."]}. '
                "Each statement must have at least one citation index. "
                "If a claim is not fully supported, omit it from statements and place it in unsupported_claims."
            ),
        },
        {
            "role": "user",
            "content": "\n".join(
                [
                    "<query>",
                    _xml_escape(_clean_text(query)),
                    "</query>",
                    "<evidence_set>",
                    *evidence_blocks,
                    "</evidence_set>",
                ]
            ),
        },
    ]


def _citation_from_hit(hit: RagQueryHit) -> RagGroundedCitation:
    return RagGroundedCitation(
        resource_id=hit.resource_id,
        source_kind=hit.source_kind,
        quote=_clean_text(hit.summary or hit.title or hit.resource_id),
        locator=hit.citation,
    )


def _extract_json_object(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", stripped)
        stripped = re.sub(r"\n?```$", "", stripped)
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Grounded answer provider did not return a JSON object.")
    return stripped[start : end + 1]


def _clean_text(value: str) -> str:
    return " ".join(value.replace("\u0000", " ").split()).strip()


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _timeout_seconds_from_ms(timeout_ms: int | None) -> float | None:
    if timeout_ms is None or timeout_ms <= 0:
        return None
    return max(timeout_ms / 1000, 0.001)
