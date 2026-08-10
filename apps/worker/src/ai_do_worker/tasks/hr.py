from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache
import logging
from typing import Any
from zoneinfo import ZoneInfo

import pytds
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ai_do_worker.celery_app import celery_app
from ai_do_worker.queue_contract import (
    ERP_HR_SNAPSHOT_TASK_NAME,
    HR_MASTER_TASK_NAME,
)
from ai_do_worker.settings import Settings, get_settings as get_worker_settings
from ai_do_api.domains.hr.erp_snapshot import (
    begin_erp_hr_snapshot_run,
    fail_erp_hr_snapshot_run,
    process_erp_hr_snapshot_run,
)
from ai_do_api.domains.hr.groupware_sync import (
    GroupwareOrgRow,
    GroupwareUserRow,
)
from ai_do_api.domains.hr.history import (
    begin_groupware_hr_sync_run,
    fail_groupware_hr_sync_run,
    process_groupware_hr_sync_run,
    prune_hr_history,
    prune_groupware_hr_history,
)
from ai_do_api.domains.hr.master import (
    build_hr_master_run,
    build_latest_hr_master_run,
    prune_hr_master_history,
)


logger = logging.getLogger(__name__)
_HR_SYNC_TASK_TIME_LIMIT = 900
_HR_SYNC_SOFT_TIME_LIMIT = 840
_ERP_EMPLOYEE_QUERY = """
    SELECT
        [EMP_NO] AS [EMP_NO],
        [NAME] AS [NAME],
        [NAT_NM] AS [NAT_NM],
        [BIRTHDAY] AS [BIRTHDAY],
        [SO_LU] AS [SO_LU],
        [DEPT_NM] AS [DEPT_NM],
        [DEPT_CD] AS [DEPT_CD],
        [OCPT_NM] AS [OCPT_NM],
        [INTERNAL_CD] AS [INTERNAL_CD],
        [ROLL_PSTN] AS [ROLL_PSTN],
        [ROLL_PSTN_NM] AS [ROLL_PSTN_NM],
        [FUNC_NM] AS [FUNC_NM],
        [PAY_GRD1] AS [PAY_GRD1],
        [PAY_GRD1_NM] AS [PAY_GRD1_NM],
        [PAY_GRD2] AS [PAY_GRD2],
        [ENTR_DT] AS [ENTR_DT],
        [GROUP_ENTR_DT] AS [GROUP_ENTR_DT],
        [ORDER_CHANGE_DT] AS [ORDER_CHANGE_DT],
        [PROMOTE_DT] AS [PROMOTE_DT],
        [PLAN_PROMITE_DT] AS [PLAN_PROMITE_DT],
        [RECENT_PROMOTE_DT] AS [RECENT_PROMOTE_DT],
        [EMAIL_ADDR] AS [EMAIL_ADDR],
        [HAND_TEL_NO] AS [HAND_TEL_NO]
    FROM [dbo].[UV_H_EMPLOYEE_LIST_DWC]
    ORDER BY [EMP_NO], [INTERNAL_CD]
"""
_ERP_GROUP_QUERY = """
    SELECT
        [DEPT_CD] AS [DEPT_CD],
        [DEPT_NM] AS [DEPT_NM]
    FROM [dbo].[UV_H_EMPLOYEE_LIST_DWC]
    GROUP BY [DEPT_CD], [DEPT_NM]
    ORDER BY [DEPT_CD], [DEPT_NM]
"""


@lru_cache(maxsize=1)
def _session_factory():
    settings = get_worker_settings()
    engine = create_engine(settings.postgres_dsn, pool_pre_ping=True)
    return sessionmaker(bind=engine, class_=Session)


def _require_groupware_db_settings(settings: Settings) -> None:
    missing = [
        key
        for key, value in {
            "AI_DO_HR_GROUPWARE_DB_HOST": settings.hr_groupware_db_host,
            "AI_DO_HR_GROUPWARE_DB_USERNAME": settings.hr_groupware_db_username,
            "AI_DO_HR_GROUPWARE_DB_PASSWORD": settings.hr_groupware_db_password,
        }.items()
        if not value.strip()
    ]
    if missing:
        raise RuntimeError("Missing Groupware HR DB settings: " + ", ".join(missing))


def _require_erp_db_settings(settings: Settings) -> None:
    missing = [
        key
        for key, value in {
            "AI_DO_ERP_DB_IP": settings.erp_db_ip,
            "AI_DO_ERP_DB_NAME": settings.erp_db_name,
            "AI_DO_ERP_DB_ID": settings.erp_db_id,
            "AI_DO_ERP_DB_PW": settings.erp_db_pw,
        }.items()
        if not value.strip()
    ]
    if missing:
        raise RuntimeError("Missing ERP HR DB settings: " + ", ".join(missing))


def _fetch_rows(cursor: Any, query: str) -> list[dict[str, Any]]:
    cursor.execute(query)
    return list(cursor.fetchall())


def _fetch_groupware_rows(
    settings: Settings,
) -> tuple[list[GroupwareOrgRow], list[GroupwareUserRow]]:
    _require_groupware_db_settings(settings)
    with pytds.connect(
        server=settings.hr_groupware_db_host,
        port=settings.hr_groupware_db_port,
        database=settings.hr_groupware_db_name,
        user=settings.hr_groupware_db_username,
        password=settings.hr_groupware_db_password,
        timeout=settings.hr_groupware_db_timeout_seconds,
        login_timeout=settings.hr_groupware_db_timeout_seconds,
        as_dict=True,
    ) as connection:
        with connection.cursor() as cursor:
            department_rows = _fetch_rows(
                cursor,
                """
                SELECT
                    [도메인번호] AS domain_num,
                    [부서코드] AS org_code,
                    [부서이름] AS org_depart,
                    [상위부서코드] AS p_org_code,
                    [부서정렬] AS org_order,
                    NULL AS org_level
                FROM [dbo].[ldepart_View2]
                WHERE [도메인번호] = 1
                ORDER BY [도메인번호], [부서코드]
                """,
            )
            user_rows = _fetch_rows(
                cursor,
                """
                SELECT
                    CAST(1 AS int) AS domain_num,
                    user_num,
                    user_id,
                    EMP_NAME AS kor_name,
                    EMP_STATE AS com_state,
                    email,
                    EMP_NO AS com_num,
                    POSITION AS com_position,
                    org_code1,
                    org_code2,
                    org_code3,
                    org_code4,
                    org_code5,
                    org_code6,
                    org_level,
                    NULL AS user_order
                FROM [dbo].[V_USER_INFO]
                ORDER BY [user_num], [EMP_NO]
                """,
            )

    departments = [GroupwareOrgRow(**dict(row)) for row in department_rows]
    users = [GroupwareUserRow(**dict(row)) for row in user_rows]
    return departments, users


def _fetch_erp_rows(
    settings: Settings,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    _require_erp_db_settings(settings)
    with pytds.connect(
        server=settings.erp_db_ip,
        port=settings.erp_db_port,
        database=settings.erp_db_name,
        user=settings.erp_db_id,
        password=settings.erp_db_pw,
        timeout=settings.erp_db_timeout_seconds,
        login_timeout=settings.erp_db_timeout_seconds,
        as_dict=True,
    ) as connection:
        with connection.cursor() as cursor:
            employee_rows = _fetch_rows(cursor, _ERP_EMPLOYEE_QUERY)
            group_rows = _fetch_rows(cursor, _ERP_GROUP_QUERY)
    return (
        [dict(row) for row in employee_rows],
        [dict(row) for row in group_rows],
    )


@celery_app.task(
    name="hr.sync_groupware",
    bind=True,
    acks_late=True,
    task_time_limit=_HR_SYNC_TASK_TIME_LIMIT,
    task_soft_time_limit=_HR_SYNC_SOFT_TIME_LIMIT,
)
def sync_groupware_hr_task(self, force: bool = False) -> str:
    settings = get_worker_settings()
    if not settings.hr_groupware_sync_enabled and not force:
        return "disabled"

    session = _session_factory()()
    task_id = str(getattr(self.request, "id", "") or "") or None
    try:
        run = begin_groupware_hr_sync_run(
            session,
            idempotency_key=task_id,
            trigger_kind="manual" if force else "scheduled",
        )
    except Exception:
        session.close()
        raise
    if run.status in {"succeeded", "rejected", "failed", "skipped"}:
        session.close()
        return f"{run.status}:run_id={run.id}"

    try:
        departments, users = _fetch_groupware_rows(settings)
    except Exception as exc:
        fail_groupware_hr_sync_run(
            session,
            run_id=run.id,
            phase="fetch",
            error=exc,
        )
        session.close()
        logger.exception("groupware HR source fetch failed (run_id=%s)", run.id)
        raise

    try:
        completed_run = process_groupware_hr_sync_run(
            session,
            run_id=run.id,
            departments=departments,
            users=users,
            allow_large_changes=force,
        )
        try:
            prune_groupware_hr_history(session)
        except Exception:
            session.rollback()
            logger.exception("groupware HR history retention cleanup failed")
        result = completed_run.result_payload or {}
        logger.info(
            "groupware HR sync completed (run_id=%s, status=%s): %s",
            completed_run.id,
            completed_run.status,
            result,
        )
        return (
            f"{completed_run.status}:run_id={completed_run.id},"
            f"departments={completed_run.org_row_count},"
            f"users={completed_run.user_row_count},"
            f"created={result.get('users_created', 0)},"
            f"updated={result.get('users_updated', 0)},"
            f"suspended={result.get('users_suspended', 0)}"
        )
    except Exception as exc:
        fail_groupware_hr_sync_run(
            session,
            run_id=run.id,
            phase="apply",
            error=exc,
        )
        logger.exception("groupware HR sync failed (run_id=%s)", run.id)
        raise
    finally:
        session.close()


@celery_app.task(
    name=ERP_HR_SNAPSHOT_TASK_NAME,
    bind=True,
    acks_late=True,
    task_time_limit=_HR_SYNC_TASK_TIME_LIMIT,
    task_soft_time_limit=_HR_SYNC_SOFT_TIME_LIMIT,
)
def capture_erp_hr_snapshot_task(self, force: bool = False) -> str:
    settings = get_worker_settings()
    if not settings.erp_hr_snapshot_enabled and not force:
        return "disabled"

    session = _session_factory()()
    task_id = str(getattr(self.request, "id", "") or "") or None
    try:
        run = begin_erp_hr_snapshot_run(
            session,
            idempotency_key=task_id,
            trigger_kind="manual" if force else "scheduled",
        )
    except Exception:
        session.close()
        raise
    if run.status in {"succeeded", "rejected", "failed", "skipped"}:
        session.close()
        return f"{run.status}:run_id={run.id}"

    rows: list[dict[str, Any]] = []
    group_rows: list[dict[str, Any]] = []
    if run.captured_at is None:
        try:
            rows, group_rows = _fetch_erp_rows(settings)
        except Exception as exc:
            safe_error = RuntimeError(f"ERP HR source fetch failed ({type(exc).__name__})")
            fail_erp_hr_snapshot_run(
                session,
                run_id=run.id,
                phase="fetch",
                error=safe_error,
            )
            session.close()
            logger.error(
                "ERP HR source fetch failed (run_id=%s, error_type=%s)",
                run.id,
                type(exc).__name__,
            )
            raise safe_error from None

    try:
        completed_run = process_erp_hr_snapshot_run(
            session,
            run_id=run.id,
            rows=rows,
            group_rows=group_rows,
            # A manual run only bypasses the disabled flag. It must not bypass
            # completeness, identity, or large-volume validation.
            allow_large_changes=False,
        )
        try:
            prune_hr_history(session)
        except Exception:
            session.rollback()
            logger.error("HR snapshot retention cleanup failed after ERP capture")
        result = completed_run.result_payload or {}
        logger.info(
            "ERP HR snapshot completed (run_id=%s, status=%s, rows=%s, groups=%s, distinct=%s)",
            completed_run.id,
            completed_run.status,
            completed_run.user_row_count,
            completed_run.org_row_count,
            result.get("distinct_employee_codes", 0),
        )
        return (
            f"{completed_run.status}:run_id={completed_run.id},"
            f"rows={completed_run.user_row_count},"
            f"distinct_employee_codes={result.get('distinct_employee_codes', 0)}"
        )
    except Exception as exc:
        safe_error = RuntimeError(f"ERP HR snapshot failed ({type(exc).__name__})")
        fail_erp_hr_snapshot_run(
            session,
            run_id=run.id,
            phase="capture",
            error=safe_error,
        )
        logger.error(
            "ERP HR snapshot failed (run_id=%s, error_type=%s)",
            run.id,
            type(exc).__name__,
        )
        raise safe_error from None
    finally:
        session.close()


@celery_app.task(
    name=HR_MASTER_TASK_NAME,
    bind=True,
    acks_late=True,
    task_time_limit=_HR_SYNC_TASK_TIME_LIMIT,
    task_soft_time_limit=_HR_SYNC_SOFT_TIME_LIMIT,
)
def build_hr_master_task(
    self,
    force: bool = False,
    erp_run_id: str | None = None,
    groupware_run_id: str | None = None,
) -> str:
    settings = get_worker_settings()
    if not settings.hr_master_sync_enabled and not force:
        return "disabled"

    now = datetime.now(ZoneInfo(settings.hr_groupware_sync_timezone))
    session = _session_factory()()
    task_id = str(getattr(self.request, "id", "") or "") or None
    try:
        if (erp_run_id is None) != (groupware_run_id is None):
            raise RuntimeError("source_pair_incomplete")
        run = (
            build_hr_master_run(
                session,
                erp_run_id=erp_run_id,
                groupware_run_id=groupware_run_id,
                idempotency_key=task_id,
                built_at=datetime.now(UTC).replace(tzinfo=None),
            )
            if erp_run_id is not None and groupware_run_id is not None
            else build_latest_hr_master_run(
                session,
                now=now,
                idempotency_key=task_id,
            )
        )
        if run is None:
            logger.info("integrated HR master build skipped (source_pair_unavailable)")
            return "skipped:source_pair_unavailable"
        if run.status != "succeeded":
            logger.error(
                "integrated HR master build did not succeed (run_id=%s, status=%s, error_code=%s)",
                run.id,
                run.status,
                getattr(run, "error_code", None),
            )
            raise RuntimeError(f"hr_master_run_{run.status}")

        try:
            prune_hr_master_history(session)
        except Exception:
            session.rollback()
            logger.error("integrated HR master retention cleanup failed")
        result = run.result_payload or {}
        people = getattr(run, "person_row_count", result.get("person_row_count", 0))
        groups = getattr(run, "group_row_count", result.get("group_row_count", 0))
        conflicts = getattr(
            run,
            "conflict_row_count",
            result.get("conflict_row_count", 0),
        )
        logger.info(
            "integrated HR master build completed "
            "(run_id=%s, status=%s, people=%s, groups=%s, conflicts=%s)",
            run.id,
            run.status,
            people,
            groups,
            conflicts,
        )
        return f"{run.status}:run_id={run.id},people={people},groups={groups},conflicts={conflicts}"
    except Exception as exc:
        logger.error(
            "integrated HR master build failed (error_type=%s)",
            type(exc).__name__,
        )
        raise RuntimeError(f"Integrated HR master build failed ({type(exc).__name__})") from None
    finally:
        session.close()
