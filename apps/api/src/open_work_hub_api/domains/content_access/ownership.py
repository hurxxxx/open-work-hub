from sqlalchemy.orm import Session

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.access import record_audit_log


def record_ownership_transition(
    db: Session,
    *,
    actor_user_id: str,
    resource_kind: str,
    resource_id: str,
    current_kind: str,
    next_kind: str,
    company_admin_read_acknowledged: bool,
) -> None:
    """The source owner authorizes the operation; publication is explicit and audited."""
    if current_kind not in {"personal", "company"} or next_kind not in {"personal", "company"}:
        raise ValueError("Unsupported content ownership kind")
    if current_kind == next_kind:
        return
    if current_kind == "company":
        raise localized_http_exception(
            status_code=409, code="content.company_ownership_irreversible"
        )
    if not company_admin_read_acknowledged:
        raise localized_http_exception(status_code=409, code="content.company_publication_required")
    record_audit_log(
        db,
        actor_user_id=actor_user_id,
        action="content.publish_to_company",
        entity_kind=resource_kind,
        entity_id=resource_id,
        summary="Published content to company ownership",
        payload={
            "previous_ownership": current_kind,
            "ownership": next_kind,
            "company_admin_read_acknowledged": True,
        },
    )
