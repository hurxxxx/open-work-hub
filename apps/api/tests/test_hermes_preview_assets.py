from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from open_work_hub_api.domains.hermes import files, file_router
from open_work_hub_api.domains.hermes.models import HermesFileRevision
from open_work_hub_api.domains.hermes.repository import utcnow_naive
from test_hermes_runtime import seed, session_for, stage, admit_runtime_apps


@pytest.mark.parametrize("interrupt_checkpoint", [False, True])
def test_preview_assets_use_owned_immutable_snapshot_without_fallback(
    application_postgres_dsn,
    monkeypatch,
    interrupt_checkpoint,
):
    objects = {}
    monkeypatch.setattr(files, "ensure_bucket", lambda: None)
    monkeypatch.setattr(
        files,
        "get_minio_client",
        lambda: SimpleNamespace(
            put_object=lambda bucket, key, stream, size, **kwargs: objects.update(
                {key: stream.read()}
            )
        ),
    )
    monkeypatch.setattr(file_router, "read_file", lambda row: objects[row.object_key])
    monkeypatch.setattr(files, "read_file", lambda row: objects[row.object_key])
    engine = create_engine(application_postgres_dsn)
    try:
        with Session(engine) as db:
            user, binding = seed(db)
            admit_runtime_apps(db, user.id)
            session = session_for(db, binding)
            run = stage(db, binding, session)
            db.commit()

            def save(path, data):
                row = files.save_file(
                    db, session=session, path=path, data=data, execution_run_id=run.id
                )
                return db.scalar(
                    select(HermesFileRevision).where(
                        HermesFileRevision.file_id == row.id,
                        HermesFileRevision.object_key == row.object_key,
                    )
                )

            dependency = save("demo/app.js", b"old dependency")
            save("demo/other.html", b"<script src='app.js'></script>")
            anchor = save("demo/index.html", b"<script src='app.js'></script>")
            save("demo/app.js", b"new dependency")
            result = file_router.preview_file_asset(anchor.id, path="demo/app.js", db=db, user=user)
            assert result.body == b"old dependency"
            assert result.headers["cache-control"] == "no-store"
            assert result.headers["content-disposition"] == "attachment"
            if interrupt_checkpoint:
                save_file = files.save_file
                attempts = []

                def interrupted_save(*args, **kwargs):
                    attempts.append(kwargs["path"])
                    if len(attempts) == 2:
                        raise OSError("synthetic interruption between entries")
                    return save_file(*args, **kwargs)

                with monkeypatch.context() as interrupted:
                    interrupted.setattr(files, "save_file", interrupted_save)
                    with pytest.raises(OSError, match="synthetic interruption"):
                        files.checkpoint_previews(db, session=session, run_id=run.id)
                assert files.checkpoint_previews(db, session=session, run_id=run.id) == 1
            else:
                assert files.checkpoint_previews(db, session=session, run_id=run.id) == 2
            new_anchor = db.scalar(
                select(HermesFileRevision)
                .where(HermesFileRevision.file_id == anchor.file_id)
                .order_by(HermesFileRevision.created_at.desc())
            )
            assert new_anchor.id != anchor.id and new_anchor.object_key != anchor.object_key
            assert new_anchor.sha256 == anchor.sha256
            assert (
                file_router.preview_file_asset(
                    new_anchor.id, path="demo/app.js", db=db, user=user
                ).body
                == b"new dependency"
            )
            assert files.checkpoint_previews(db, session=session, run_id=run.id) == 0
            for path in ["../app.js", "/etc/passwd", "demo/missing.js", ".owh-runtime/state"]:
                with pytest.raises(HTTPException) as error:
                    file_router.preview_file_asset(anchor.id, path=path, db=db, user=user)
                assert error.value.status_code == 404
            with pytest.raises(HTTPException) as error:
                file_router.preview_file_asset(
                    anchor.id, path="demo/app.js", db=db, user=SimpleNamespace(id="other-user")
                )
            assert error.value.status_code == 404
            dependency.expires_at = utcnow_naive() - timedelta(seconds=1)
            db.commit()
            with pytest.raises(HTTPException) as error:
                file_router.preview_file_asset(anchor.id, path="demo/app.js", db=db, user=user)
            assert error.value.status_code == 404
    finally:
        engine.dispose()
