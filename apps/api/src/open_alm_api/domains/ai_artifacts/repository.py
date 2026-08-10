from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session, selectinload

from open_alm_api.domains.ai_artifacts.contracts import (
    AiArtifactCreate,
    AiArtifactIndexGenerationCreate,
    AiArtifactQueryCreate,
    AiArtifactSourceCreate,
    AiIndexGenerationCreate,
    ArtifactVisibility,
)
from open_alm_api.domains.ai_artifacts.models import (
    AiArtifact,
    AiArtifactIndexGeneration,
    AiArtifactQuery,
    AiArtifactSource,
    AiIndexGeneration,
)


class AiArtifactNotFoundError(LookupError):
    pass


class AiArtifactImmutableError(ValueError):
    pass


_NUMBER_PREFIX = {"report": "AIR", "analysis": "AIA"}
_NUMBER_SEQUENCE = {
    "report": "ai_report_artifact_number_seq",
    "analysis": "ai_analysis_artifact_number_seq",
}


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _content_bytes(artifact: AiArtifact) -> bytes:
    return _canonical_json_bytes(
        {
            "contentText": artifact.content_text,
            "payload": artifact.payload_json,
        }
    )


def _query_bytes(request: AiArtifactQueryCreate) -> bytes:
    return _canonical_json_bytes(
        {
            "familyId": request.family_id,
            "queryKind": request.query_kind,
            "querySpec": request.query_spec,
            "statementText": request.statement_text,
            "typedParams": request.typed_params,
        }
    )


class AiArtifactRepository:
    """Build then atomically complete an immutable AI artifact aggregate."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _allocate_number(self, artifact_type: str) -> str:
        prefix = _NUMBER_PREFIX[artifact_type]
        bind = self.db.get_bind()
        if bind.dialect.name == "postgresql":
            sequence_name = _NUMBER_SEQUENCE[artifact_type]
            number = int(self.db.scalar(text(f"SELECT nextval('{sequence_name}')")))
        else:
            latest = self.db.scalar(
                select(AiArtifact.artifact_number)
                .where(AiArtifact.artifact_number.like(f"{prefix}-%"))
                .order_by(AiArtifact.artifact_number.desc())
                .limit(1)
            )
            number = int(latest.rsplit("-", 1)[1]) + 1 if latest else 1
        date_key = _utcnow_naive().strftime("%Y%m%d")
        return f"{prefix}-{date_key}-{number:010d}"

    def create_building(self, request: AiArtifactCreate) -> AiArtifact:
        if request.supersedes_artifact_id is not None:
            superseded = self.require(request.supersedes_artifact_id)
            if (
                superseded.workspace_id != request.workspace_id
                or superseded.artifact_type != request.artifact_type
                or superseded.status != "completed"
            ):
                raise ValueError(
                    "superseded artifact must be a completed artifact of the same workspace/type"
                )
        artifact = AiArtifact(
            id=str(uuid4()),
            artifact_number=self._allocate_number(request.artifact_type),
            workspace_id=request.workspace_id,
            owner_user_id=request.owner_user_id,
            graph_run_id=request.graph_run_id,
            conversation_id=request.conversation_id,
            conversation_turn_id=request.conversation_turn_id,
            supersedes_artifact_id=request.supersedes_artifact_id,
            app_id=request.app_id,
            artifact_type=request.artifact_type,
            title=request.title,
            content_type=request.content_type,
            content_text=request.content_text,
            payload_json=request.payload,
            schema_version=request.schema_version,
            visibility=request.visibility,
            status="building",
        )
        self.db.add(artifact)
        self.db.flush()
        return artifact

    def create_pending(self, request: AiArtifactCreate) -> AiArtifact:
        artifact = self.create_building(request)
        artifact.status = "pending"
        self.db.add(artifact)
        self.db.flush()
        return artifact

    def start_building(self, artifact: AiArtifact) -> AiArtifact:
        if artifact.status != "pending":
            raise AiArtifactImmutableError("only pending artifacts can start building")
        artifact.status = "building"
        self.db.add(artifact)
        self.db.flush()
        return artifact

    def update_building(
        self,
        artifact: AiArtifact,
        *,
        content_text: str | None,
        payload: dict[str, Any] | list[Any] | None,
        title: str | None = None,
        content_type: str | None = None,
    ) -> AiArtifact:
        self._ensure_building(artifact)
        artifact.content_text = content_text
        artifact.payload_json = payload
        if title is not None:
            artifact.title = title
        if content_type is not None:
            artifact.content_type = content_type
        self.db.add(artifact)
        self.db.flush()
        return artifact

    def fail(self, artifact: AiArtifact, *, error_code: str) -> AiArtifact:
        if artifact.status not in {"pending", "building"}:
            raise AiArtifactImmutableError("only pending/building artifacts can fail")
        artifact.status = "failed"
        artifact.error_code = error_code[:128]
        self.db.add(artifact)
        self.db.flush()
        return artifact

    def get(self, identifier: str, *, eager: bool = False) -> AiArtifact | None:
        statement = select(AiArtifact).where(
            or_(AiArtifact.id == identifier, AiArtifact.artifact_number == identifier)
        )
        if eager:
            statement = statement.options(
                selectinload(AiArtifact.sources),
                selectinload(AiArtifact.queries),
                selectinload(AiArtifact.index_generations),
            )
        return self.db.scalar(statement)

    def require(self, identifier: str, *, eager: bool = False) -> AiArtifact:
        artifact = self.get(identifier, eager=eager)
        if artifact is None:
            raise AiArtifactNotFoundError(identifier)
        return artifact

    def get_visible(
        self,
        identifier: str,
        *,
        workspace_id: str,
        user_id: str,
        eager: bool = False,
    ) -> AiArtifact | None:
        statement = select(AiArtifact).where(
            or_(AiArtifact.id == identifier, AiArtifact.artifact_number == identifier),
            AiArtifact.workspace_id == workspace_id,
            or_(
                AiArtifact.owner_user_id == user_id,
                AiArtifact.visibility == "workspace",
            ),
        )
        if eager:
            statement = statement.options(
                selectinload(AiArtifact.sources),
                selectinload(AiArtifact.queries),
                selectinload(AiArtifact.index_generations),
            )
        return self.db.scalar(statement)

    def list_visible(
        self,
        *,
        workspace_id: str,
        user_id: str,
        artifact_type: str | None = None,
        status: str | None = "completed",
        app_id: str | None = None,
        graph_run_id: str | None = None,
        conversation_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AiArtifact], int]:
        predicates = [
            AiArtifact.workspace_id == workspace_id,
            or_(
                AiArtifact.owner_user_id == user_id,
                AiArtifact.visibility == "workspace",
            ),
        ]
        if artifact_type:
            predicates.append(AiArtifact.artifact_type == artifact_type)
        if status:
            predicates.append(AiArtifact.status == status)
        if app_id:
            predicates.append(AiArtifact.app_id == app_id)
        if graph_run_id:
            predicates.append(AiArtifact.graph_run_id == graph_run_id)
        if conversation_id:
            predicates.append(AiArtifact.conversation_id == conversation_id)
        total = int(
            self.db.scalar(select(func.count()).select_from(AiArtifact).where(*predicates)) or 0
        )
        items = list(
            self.db.scalars(
                select(AiArtifact)
                .where(*predicates)
                .order_by(AiArtifact.created_at.desc(), AiArtifact.id.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        return items, total

    def set_completed_visibility(
        self,
        identifier: str,
        *,
        workspace_id: str,
        owner_user_id: str,
        visibility: ArtifactVisibility,
        expected_app_id: str | None = None,
        expected_artifact_type: str | None = None,
    ) -> tuple[AiArtifact, bool]:
        """Change only the access scope of an owned, completed artifact."""

        if visibility not in {"private", "workspace"}:
            raise ValueError("artifact visibility must be private or workspace")
        predicates = [
            or_(
                AiArtifact.id == identifier,
                AiArtifact.artifact_number == identifier,
            ),
            AiArtifact.workspace_id == workspace_id,
            AiArtifact.owner_user_id == owner_user_id,
            AiArtifact.status == "completed",
        ]
        if expected_app_id is not None:
            predicates.append(AiArtifact.app_id == expected_app_id)
        if expected_artifact_type is not None:
            predicates.append(AiArtifact.artifact_type == expected_artifact_type)
        artifact = self.db.scalar(
            select(AiArtifact)
            .where(*predicates)
            .with_for_update()
        )
        if artifact is None:
            raise AiArtifactNotFoundError(identifier)
        if artifact.visibility == visibility:
            return artifact, False
        artifact.visibility = visibility
        self.db.add(artifact)
        self.db.flush()
        return artifact, True

    @staticmethod
    def _ensure_building(artifact: AiArtifact) -> None:
        if artifact.status != "building":
            raise AiArtifactImmutableError(
                f"artifact {artifact.artifact_number} is completed and immutable"
            )

    def _next_ordinal(self, model: type, artifact_id: str) -> int:
        value = self.db.scalar(
            select(func.coalesce(func.max(model.ordinal), -1)).where(
                model.artifact_id == artifact_id
            )
        )
        return int(value if value is not None else -1) + 1

    def add_source(
        self,
        artifact: AiArtifact,
        request: AiArtifactSourceCreate,
    ) -> AiArtifactSource:
        self._ensure_building(artifact)
        source = AiArtifactSource(
            id=str(uuid4()),
            artifact_id=artifact.id,
            ordinal=self._next_ordinal(AiArtifactSource, artifact.id),
            source_kind=request.source_kind,
            source_ref=request.source_ref,
            source_version=request.source_version,
            title=request.title,
            locator_json=request.locator,
            metadata_json=request.metadata,
            content_sha256=request.content_sha256,
            grid_columns_json=request.grid_columns,
            grid_rows_json=request.grid_rows,
            row_count=request.row_count,
            truncated=request.truncated,
        )
        self.db.add(source)
        self.db.flush()
        return source

    def add_query(
        self,
        artifact: AiArtifact,
        request: AiArtifactQueryCreate,
    ) -> AiArtifactQuery:
        self._ensure_building(artifact)
        query = AiArtifactQuery(
            id=str(uuid4()),
            artifact_id=artifact.id,
            ordinal=self._next_ordinal(AiArtifactQuery, artifact.id),
            query_kind=request.query_kind,
            title=request.title,
            family_id=request.family_id,
            query_spec_json=request.query_spec,
            statement_text=request.statement_text,
            typed_params_json=request.typed_params,
            execution_status=request.execution_status,
            error_code=request.error_code,
            result_schema_json=request.result_schema,
            result_rows_json=request.result_rows,
            query_sha256=hashlib.sha256(_query_bytes(request)).hexdigest(),
            result_sha256=request.result_sha256,
            row_count=request.row_count,
            duration_ms=request.duration_ms,
            truncated=request.truncated,
            payload_bytes=request.payload_bytes,
            exactness=request.exactness,
        )
        self.db.add(query)
        self.db.flush()
        return query

    def add_index_generation(
        self,
        artifact: AiArtifact,
        request: AiArtifactIndexGenerationCreate,
    ) -> AiArtifactIndexGeneration:
        self._ensure_building(artifact)
        generation = AiArtifactIndexGeneration(
            id=str(uuid4()),
            artifact_id=artifact.id,
            ordinal=self._next_ordinal(AiArtifactIndexGeneration, artifact.id),
            index_generation_id=request.index_generation_id,
            metadata_json=request.metadata,
        )
        self.db.add(generation)
        self.db.flush()
        return generation

    def complete(self, artifact: AiArtifact) -> AiArtifact:
        self._ensure_building(artifact)
        if artifact.content_text is None and artifact.payload_json is None:
            raise ValueError("completed artifact must contain text or structured payload")
        content = _content_bytes(artifact)
        artifact.content_sha256 = hashlib.sha256(content).hexdigest()
        artifact.content_size_bytes = len(content)
        artifact.completed_at = _utcnow_naive()
        artifact.status = "completed"
        self.db.add(artifact)
        self.db.flush()
        return artifact

    def create_completed(
        self,
        request: AiArtifactCreate,
        *,
        sources: tuple[AiArtifactSourceCreate, ...] = (),
        queries: tuple[AiArtifactQueryCreate, ...] = (),
        index_generations: tuple[AiArtifactIndexGenerationCreate, ...] = (),
    ) -> AiArtifact:
        artifact = self.create_building(request)
        for source in sources:
            self.add_source(artifact, source)
        for query in queries:
            self.add_query(artifact, query)
        for generation in index_generations:
            self.add_index_generation(artifact, generation)
        return self.complete(artifact)


class AiIndexGenerationRepository:
    """Stage, validate and atomically cut over shared retrieval generations."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_staging(self, request: AiIndexGenerationCreate) -> AiIndexGeneration:
        generation = AiIndexGeneration(
            id=str(uuid4()),
            workspace_id=request.workspace_id,
            app_id=request.app_id,
            generation_key=request.generation_key,
            status="staging",
            backend=request.backend,
            source_namespace=request.source_namespace,
            schema_version=request.schema_version,
            embedding_provider=request.embedding_provider,
            embedding_model=request.embedding_model,
            embedding_dimensions=request.embedding_dimensions,
            source_count=request.source_count,
            document_count=request.document_count,
            chunk_count=request.chunk_count,
            corpus_sha256=request.corpus_sha256,
            validation_status="pending",
            created_by_user_id=request.created_by_user_id,
        )
        self.db.add(generation)
        self.db.flush()
        return generation

    def require(self, generation_id: str) -> AiIndexGeneration:
        generation = self.db.get(AiIndexGeneration, generation_id)
        if generation is None:
            raise LookupError(generation_id)
        return generation

    def record_validation(
        self,
        generation_id: str,
        *,
        passed: bool,
        validation: dict[str, Any],
    ) -> AiIndexGeneration:
        generation = self.require(generation_id)
        if generation.status != "staging":
            raise ValueError("only staging generations can be validated")
        generation.validation_status = "passed" if passed else "failed"
        generation.validation_json = validation
        generation.validated_at = _utcnow_naive()
        if not passed:
            generation.status = "failed"
        self.db.add(generation)
        self.db.flush()
        return generation

    def activate(self, generation_id: str) -> AiIndexGeneration:
        generation = self.require(generation_id)
        if generation.status != "staging" or generation.validation_status != "passed":
            raise ValueError("generation must pass validation before cutover")
        now = _utcnow_naive()
        current = self.db.scalar(
            select(AiIndexGeneration)
            .where(
                AiIndexGeneration.workspace_id == generation.workspace_id,
                AiIndexGeneration.app_id == generation.app_id,
                AiIndexGeneration.backend == generation.backend,
                AiIndexGeneration.source_namespace == generation.source_namespace,
                AiIndexGeneration.status == "active",
            )
            .with_for_update()
        )
        if current is not None:
            current.status = "retired"
            current.retired_at = now
            self.db.add(current)
        generation.status = "active"
        generation.cutover_at = now
        self.db.add(generation)
        self.db.flush()
        return generation

    def retire(self, generation_id: str) -> AiIndexGeneration:
        generation = self.require(generation_id)
        if generation.status != "active":
            raise ValueError("only active generations can be retired")
        generation.status = "retired"
        generation.retired_at = _utcnow_naive()
        self.db.add(generation)
        self.db.flush()
        return generation
