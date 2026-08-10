from __future__ import annotations

import uuid
from typing import Any, Callable, TypeVar

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ai_do_api.core.db import get_session_factory
from ai_do_api.domains.meal_invoice_ocr.models import MealInvoiceOcrState

T = TypeVar("T")
_MAX_CREATE_RETRIES = 3


def _supports_for_update(session: Session) -> bool:
    # sqlite(테스트)는 FOR UPDATE 를 지원하지 않는다. Postgres 에서만 행 잠금을 건다
    # (sqlite 는 단일 프로세스 테스트라 락 없이도 안전).
    bind = session.get_bind()
    return getattr(bind.dialect, "name", "") == "postgresql"


def read_state_field(workspace_id: str, field: str, default: T) -> T:
    """워크스페이스 상태 행의 한 필드를 읽는다. 행이 없으면 기본값."""
    session = get_session_factory()()
    try:
        state = session.execute(
            select(MealInvoiceOcrState).where(
                MealInvoiceOcrState.workspace_id == workspace_id
            )
        ).scalar_one_or_none()
        if state is None:
            return default
        value = getattr(state, field)
        return value if value is not None else default
    finally:
        session.close()


def mutate_state(
    workspace_id: str, mutate: Callable[[MealInvoiceOcrState], T]
) -> T:
    """워크스페이스 상태 행을 잠그고(FOR UPDATE) 원자적으로 read-modify-write 한 뒤 커밋한다.

    mutate 는 잠긴 상태 행을 받아 *_json 필드를 새 값으로 '재대입'해야 한다(in-place 변경은
    변경 감지가 안 됨). 반환값이 그대로 함수 결과가 된다. 다중 워커 동시 갱신에도 유실이 없다.
    """
    last_create_error: IntegrityError | None = None
    for _attempt in range(_MAX_CREATE_RETRIES):
        session = get_session_factory()()
        try:
            stmt = select(MealInvoiceOcrState).where(
                MealInvoiceOcrState.workspace_id == workspace_id
            )
            if _supports_for_update(session):
                stmt = stmt.with_for_update()
            state = session.execute(stmt).scalar_one_or_none()
            if state is None:
                state = MealInvoiceOcrState(
                    id=uuid.uuid4().hex,
                    workspace_id=workspace_id,
                    corrections_json=[],
                    catalog_json={},
                    units_json=[],
                    vocab_json=[],
                )
                session.add(state)
                try:
                    session.flush()
                except IntegrityError as exc:
                    session.rollback()
                    last_create_error = exc
                    continue
            result = mutate(state)
            session.commit()
            return result
        finally:
            session.close()
    assert last_create_error is not None
    raise last_create_error


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}
