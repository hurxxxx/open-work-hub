from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ai_do_api.core.db import Base
from ai_do_api.domains.lawsearch import schemas, service
from ai_do_api.domains.lawsearch.models import LawPart, LawPartGroup, LawRegion, LawType


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def _seed_master_data(db: Session) -> None:
    db.add(LawPartGroup(id="grp", name_ko="부품", icon="", sort_order=1))
    db.add(
        LawPart(
            id="compressor",
            group_id="grp",
            name_ko="컴프레서",
            name_en="Compressor",
            icon="",
            sort_order=1,
        )
    )
    db.add(
        LawRegion(
            id="eu",
            name_ko="EU",
            name_en="EU",
            flag="",
            sort_order=1,
        )
    )
    db.add(
        LawType(
            id="regulation",
            name_ko="규제",
            name_en="Regulation",
            icon="",
            description="",
            sort_order=1,
        )
    )
    db.commit()


def _payload(source_url: str) -> schemas.LawItemWriteIn:
    return schemas.LawItemWriteIn(
        name="REACH",
        type="regulation",
        part_ids=["compressor"],
        region_ids=["eu"],
        source_url=source_url,
    )


def test_lawsearch_write_validation_accepts_http_source_urls() -> None:
    with _session() as db:
        _seed_master_data(db)

        assert service.validate_payload(db, _payload("https://echa.europa.eu/reach")) == []
        assert service.validate_payload(db, _payload("http://example.test/reach")) == []
        assert service.validate_payload(db, _payload("")) == []


def test_lawsearch_write_validation_rejects_unsafe_source_urls() -> None:
    with _session() as db:
        _seed_master_data(db)

        errors = service.validate_payload(db, _payload("javascript:alert(1)"))

        assert errors == ["source_url은 http 또는 https URL이어야 합니다"]
