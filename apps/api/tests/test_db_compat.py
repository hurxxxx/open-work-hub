from types import SimpleNamespace

from aidoo_api.core.db import _apply_postgres_schema_compat


class _FakeConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, clause) -> None:
        self.statements.append(str(clause))


class _FakeBeginContext:
    def __init__(self, connection: _FakeConnection) -> None:
        self.connection = connection

    def __enter__(self) -> _FakeConnection:
        return self.connection

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class _FakeEngine:
    def __init__(self, dialect_name: str) -> None:
        self.dialect = SimpleNamespace(name=dialect_name)
        self.connection = _FakeConnection()

    def begin(self) -> _FakeBeginContext:
        return _FakeBeginContext(self.connection)


def test_postgres_schema_compat_adds_team_id_guards() -> None:
    engine = _FakeEngine("postgresql")

    _apply_postgres_schema_compat(engine)

    statements = engine.connection.statements
    assert any(
        "ALTER TABLE pms_projects ADD COLUMN IF NOT EXISTS team_id VARCHAR(36)" in statement
        for statement in statements
    )
    assert any(
        "CREATE INDEX IF NOT EXISTS ix_pms_projects_team_id ON pms_projects (team_id)" in statement
        for statement in statements
    )
    assert any(
        "ADD CONSTRAINT pms_projects_team_id_fkey" in statement
        for statement in statements
    )
    assert any(
        "ALTER TABLE teams ADD COLUMN IF NOT EXISTS trashed_at TIMESTAMP" in statement
        for statement in statements
    )
    assert any(
        "CREATE INDEX IF NOT EXISTS ix_teams_trashed_at ON teams (trashed_at)" in statement
        for statement in statements
    )


def test_postgres_schema_compat_skips_non_postgres() -> None:
    engine = _FakeEngine("sqlite")

    _apply_postgres_schema_compat(engine)

    assert engine.connection.statements == []
