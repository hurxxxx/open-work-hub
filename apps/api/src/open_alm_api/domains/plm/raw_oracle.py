"""Read-only PLM Oracle access for raw data inspection."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent

from open_alm_api.core.settings import get_settings

ROOT = Path(__file__).resolve().parents[6]
DEFAULT_OJDBC_JAR_CANDIDATES = (
    ROOT / ".runtime/ojdbc11-23.9.0.25.07.jar",
    Path("/tmp/ojdbc11-23.9.0.25.07.jar"),
    ROOT / ".runtime/ojdbc11.jar",
    Path("/tmp/ojdbc11.jar"),
)
PLM_QUERY_TIMEOUT_SECONDS = 45
PLM_JDBC_QUERY_TIMEOUT_SECONDS = 30
PLM_MAX_LIMIT = 500
PLM_INTERNAL_ROWNUM_COLUMN = "OPEN_ALM_INTERNAL_RN"

_ORACLE_IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]*$")
_SQL_WORD_RE = re.compile(r"[a-z_][a-z0-9_]*")
_FORBIDDEN_RAW_SQL_TOKENS = frozenset(
    {
        "alter",
        "analyze",
        "call",
        "comment",
        "commit",
        "create",
        "delete",
        "drop",
        "execute",
        "grant",
        "insert",
        "merge",
        "revoke",
        "rollback",
        "truncate",
        "update",
    }
)


class PlmRawOracleError(RuntimeError):
    def __init__(self, status_code: int, code: str, **params: object) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.params = params


@dataclass(frozen=True)
class PlmConnectionInfo:
    host: str
    sid: str
    user: str
    password: str
    port: int

    @property
    def jdbc_url(self) -> str:
        return f"jdbc:oracle:thin:@{self.host}:{self.port}:{self.sid}"


@dataclass(frozen=True)
class PlmRawColumn:
    name: str
    type: str


@dataclass(frozen=True)
class PlmRawQueryResult:
    columns: tuple[PlmRawColumn, ...]
    rows: tuple[tuple[str | None, ...], ...]


@dataclass(frozen=True)
class PlmRawRowsResult:
    columns: tuple[PlmRawColumn, ...]
    rows: tuple[tuple[str | None, ...], ...]
    has_more: bool
    limit: int
    offset: int
    sql_preview: str


@dataclass(frozen=True)
class PlmRawTable:
    owner: str
    name: str
    object_type: str


def clamp_limit(limit: int) -> int:
    return min(max(limit, 1), PLM_MAX_LIMIT)


def normalize_offset(offset: int) -> int:
    return max(offset, 0)


def validate_raw_select_sql(sql: str) -> str:
    stripped = sql.strip()
    normalized = " ".join(stripped.lower().split())
    if not normalized.startswith("select "):
        raise PlmRawOracleError(422, "plm.sql_read_only_required")
    if ";" in stripped:
        raise PlmRawOracleError(422, "plm.sql_single_statement_required")
    if "--" in stripped or "/*" in stripped or "*/" in stripped:
        raise PlmRawOracleError(422, "plm.sql_comments_not_allowed")
    forbidden = set(_SQL_WORD_RE.findall(normalized)) & _FORBIDDEN_RAW_SQL_TOKENS
    if forbidden:
        raise PlmRawOracleError(
            422,
            "plm.sql_forbidden_token",
            token=sorted(forbidden)[0],
        )
    return stripped


def validate_oracle_identifier(value: str) -> str:
    if not _ORACLE_IDENTIFIER_RE.fullmatch(value):
        raise PlmRawOracleError(422, "plm.object_name_invalid")
    return value.upper()


def build_object_reference(owner: str, name: str) -> str:
    return f"{validate_oracle_identifier(owner)}.{validate_oracle_identifier(name)}"


def build_paginated_select_sql(base_sql: str, *, limit: int, offset: int) -> str:
    normalized_limit = clamp_limit(limit)
    normalized_offset = normalize_offset(offset)
    upper_bound = normalized_offset + normalized_limit + 1
    return (
        "select * from ("
        f"select open_alm_inner.*, rownum {PLM_INTERNAL_ROWNUM_COLUMN} from ("
        f"{base_sql}"
        f") open_alm_inner where rownum <= {upper_bound}"
        f") where {PLM_INTERNAL_ROWNUM_COLUMN} > {normalized_offset}"
    )


def build_table_rows_sql(owner: str, name: str, *, limit: int, offset: int) -> str:
    return build_paginated_select_sql(
        f"select * from {build_object_reference(owner, name)}",
        limit=limit,
        offset=offset,
    )


def build_raw_query_sql(sql: str, *, limit: int, offset: int) -> str:
    return build_paginated_select_sql(
        validate_raw_select_sql(sql),
        limit=limit,
        offset=offset,
    )


def strip_internal_rownum_column(result: PlmRawQueryResult, limit: int) -> PlmRawRowsResult:
    internal_index = next(
        (
            index
            for index, column in enumerate(result.columns)
            if column.name.upper() == PLM_INTERNAL_ROWNUM_COLUMN
        ),
        None,
    )
    columns = result.columns
    rows = result.rows
    if internal_index is not None:
        columns = tuple(column for index, column in enumerate(columns) if index != internal_index)
        rows = tuple(
            tuple(cell for index, cell in enumerate(row) if index != internal_index) for row in rows
        )
    has_more = len(rows) > limit
    return PlmRawRowsResult(
        columns=columns,
        rows=rows[:limit],
        has_more=has_more,
        limit=limit,
        offset=0,
        sql_preview="",
    )


def load_connection_info() -> PlmConnectionInfo:
    settings = get_settings()
    required_values = {
        "OPEN_ALM_PLM_ORACLE_HOST": settings.plm_oracle_host.strip(),
        "OPEN_ALM_PLM_ORACLE_SID": settings.plm_oracle_sid.strip(),
        "OPEN_ALM_PLM_ORACLE_USER": settings.plm_oracle_user.strip(),
        "OPEN_ALM_PLM_ORACLE_PASSWORD": settings.plm_oracle_password.strip(),
    }
    missing_keys = tuple(key for key, value in required_values.items() if not value)
    if missing_keys:
        raise PlmRawOracleError(
            503,
            "plm.connection_config_missing",
            keys=", ".join(missing_keys),
        )
    return PlmConnectionInfo(
        host=required_values["OPEN_ALM_PLM_ORACLE_HOST"],
        sid=required_values["OPEN_ALM_PLM_ORACLE_SID"],
        user=required_values["OPEN_ALM_PLM_ORACLE_USER"],
        password=required_values["OPEN_ALM_PLM_ORACLE_PASSWORD"],
        port=settings.plm_oracle_port,
    )


def _ojdbc_jar_candidates() -> tuple[Path, ...]:
    configured_path = get_settings().plm_ojdbc_jar.strip()
    if configured_path:
        return (Path(configured_path).expanduser(), *DEFAULT_OJDBC_JAR_CANDIDATES)
    return DEFAULT_OJDBC_JAR_CANDIDATES


def resolve_ojdbc_jar() -> Path:
    candidates = _ojdbc_jar_candidates()
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise PlmRawOracleError(
        503,
        "plm.ojdbc_jar_not_found",
        path=", ".join(str(path) for path in candidates),
    )


def _runner_source() -> str:
    return (
        dedent(
            r"""
        import java.nio.charset.StandardCharsets;
        import java.nio.file.Files;
        import java.nio.file.Path;
        import java.sql.Connection;
        import java.sql.DriverManager;
        import java.sql.ResultSet;
        import java.sql.ResultSetMetaData;
        import java.sql.Statement;
        import java.util.Properties;

        public class PlmRawQueryRunner {
            private static String jsonEscape(String value) {
                if (value == null) {
                    return "";
                }
                StringBuilder builder = new StringBuilder();
                for (int index = 0; index < value.length(); index++) {
                    char current = value.charAt(index);
                    switch (current) {
                        case '"': builder.append("\\\""); break;
                        case '\\': builder.append("\\\\"); break;
                        case '\b': builder.append("\\b"); break;
                        case '\f': builder.append("\\f"); break;
                        case '\n': builder.append("\\n"); break;
                        case '\r': builder.append("\\r"); break;
                        case '\t': builder.append("\\t"); break;
                        default:
                            if (current < 0x20) {
                                builder.append(String.format("\\u%04x", (int) current));
                            } else {
                                builder.append(current);
                            }
                    }
                }
                return builder.toString();
            }

            private static void appendJsonString(StringBuilder builder, String value) {
                builder.append('"').append(jsonEscape(value)).append('"');
            }

            public static void main(String[] args) throws Exception {
                if (args.length != 1) {
                    throw new IllegalArgumentException("query file path is required");
                }
                String url = System.getenv("PLM_JDBC_URL");
                String user = System.getenv("PLM_JDBC_USER");
                String password = System.getenv("PLM_JDBC_PASSWORD");
                String timeoutValue = System.getenv("PLM_JDBC_QUERY_TIMEOUT");
                if (url == null || user == null || password == null) {
                    throw new IllegalStateException("JDBC env is incomplete");
                }
                int queryTimeout = 30;
                if (timeoutValue != null && !timeoutValue.isBlank()) {
                    queryTimeout = Integer.parseInt(timeoutValue);
                }

                DriverManager.setLoginTimeout(10);
                Properties props = new Properties();
                props.put("user", user);
                props.put("password", password);
                String sql = Files.readString(Path.of(args[0]), StandardCharsets.UTF_8);

                try (Connection connection = DriverManager.getConnection(url, props);
                     Statement statement = connection.createStatement()) {
                    statement.setFetchSize(200);
                    statement.setQueryTimeout(queryTimeout);
                    try (ResultSet rows = statement.executeQuery(sql)) {
                        ResultSetMetaData meta = rows.getMetaData();
                        int columnCount = meta.getColumnCount();
                        StringBuilder builder = new StringBuilder();
                        builder.append("{\"columns\":[");
                        for (int index = 1; index <= columnCount; index++) {
                            if (index > 1) {
                                builder.append(',');
                            }
                            builder.append("{\"name\":");
                            appendJsonString(builder, meta.getColumnLabel(index));
                            builder.append(",\"type\":");
                            appendJsonString(builder, meta.getColumnTypeName(index));
                            builder.append('}');
                        }
                        builder.append("],\"rows\":[");
                        int rowIndex = 0;
                        while (rows.next()) {
                            if (rowIndex > 0) {
                                builder.append(',');
                            }
                            builder.append('[');
                            for (int index = 1; index <= columnCount; index++) {
                                if (index > 1) {
                                    builder.append(',');
                                }
                                String value = rows.getString(index);
                                if (rows.wasNull()) {
                                    builder.append("null");
                                } else {
                                    appendJsonString(builder, value);
                                }
                            }
                            builder.append(']');
                            rowIndex++;
                        }
                        builder.append("]}");
                        System.out.println(builder.toString());
                    }
                }
            }
        }
        """
        ).strip()
        + "\n"
    )


def _runner_directory() -> Path:
    return Path(tempfile.gettempdir()) / "open-alm-plm-jdbc"


def ensure_runner_compiled() -> Path:
    runner_dir = _runner_directory()
    runner_dir.mkdir(parents=True, exist_ok=True)
    source_path = runner_dir / "PlmRawQueryRunner.java"
    class_path = runner_dir / "PlmRawQueryRunner.class"
    source = _runner_source()
    if not source_path.exists() or source_path.read_text(encoding="utf-8") != source:
        source_path.write_text(source, encoding="utf-8")
        class_path.unlink(missing_ok=True)
    if class_path.exists():
        return runner_dir
    completed = subprocess.run(
        ["javac", str(source_path)],
        cwd=runner_dir,
        capture_output=True,
        text=True,
        timeout=PLM_QUERY_TIMEOUT_SECONDS,
        check=False,
    )
    if completed.returncode != 0:
        raise PlmRawOracleError(
            503,
            "plm.jdbc_runner_compile_failed",
            error=completed.stderr.strip()[:500] or completed.stdout.strip()[:500],
        )
    return runner_dir


def _redact_error(message: str, connection: PlmConnectionInfo) -> str:
    output = message.replace(connection.jdbc_url, "[JDBC_URL]")
    output = output.replace(connection.user, "[USER]")
    output = output.replace(connection.password, "[PASSWORD]")
    output = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "[IP]", output)
    return output.strip()[:500]


class PlmRawOracleClient:
    def __init__(
        self,
        *,
        ojdbc_jar: Path | None = None,
    ) -> None:
        self.ojdbc_jar = ojdbc_jar

    def execute_grid_query(self, sql: str) -> PlmRawQueryResult:
        connection = load_connection_info()
        runner_dir = ensure_runner_compiled()
        jar_path = self.ojdbc_jar or resolve_ojdbc_jar()
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix="open-alm-plm-query-",
            suffix=".sql",
            delete=False,
        ) as query_file:
            query_file.write(sql)
            query_path = Path(query_file.name)
        try:
            env = {
                **os.environ,
                "PLM_JDBC_URL": connection.jdbc_url,
                "PLM_JDBC_USER": connection.user,
                "PLM_JDBC_PASSWORD": connection.password,
                "PLM_JDBC_QUERY_TIMEOUT": str(PLM_JDBC_QUERY_TIMEOUT_SECONDS),
            }
            completed = subprocess.run(
                [
                    "java",
                    "-cp",
                    f"{jar_path}:{runner_dir}",
                    "PlmRawQueryRunner",
                    str(query_path),
                ],
                capture_output=True,
                text=True,
                timeout=PLM_QUERY_TIMEOUT_SECONDS,
                check=False,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise PlmRawOracleError(504, "plm.query_timeout") from exc
        finally:
            query_path.unlink(missing_ok=True)

        if completed.returncode != 0:
            raw_error = completed.stderr or completed.stdout or "PLM JDBC query failed."
            raise PlmRawOracleError(
                502,
                "plm.query_failed",
                error=_redact_error(raw_error, connection),
            )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise PlmRawOracleError(
                502,
                "plm.query_result_invalid",
                error=completed.stdout.strip()[:500],
            ) from exc
        return PlmRawQueryResult(
            columns=tuple(
                PlmRawColumn(
                    name=str(column.get("name") or ""),
                    type=str(column.get("type") or ""),
                )
                for column in payload.get("columns", [])
                if isinstance(column, dict)
            ),
            rows=tuple(
                tuple(None if cell is None else str(cell) for cell in row)
                for row in payload.get("rows", [])
                if isinstance(row, list)
            ),
        )

    def list_tables(self) -> tuple[PlmRawTable, ...]:
        result = self.execute_grid_query(
            "select * from ("
            "select owner, object_name, object_type from all_objects "
            "where object_type in ('TABLE', 'VIEW', 'SYNONYM') "
            "and owner in (user, 'INFODBA') "
            "order by case when owner = user then 0 else 1 end, owner, object_name"
            ") where rownum <= 500"
        )
        tables: list[PlmRawTable] = []
        seen: set[tuple[str, str]] = set()
        for row in result.rows:
            if len(row) < 3 or row[0] is None or row[1] is None or row[2] is None:
                continue
            owner = row[0].upper()
            name = row[1].upper()
            key = (owner, name)
            if key in seen:
                continue
            seen.add(key)
            tables.append(PlmRawTable(owner=owner, name=name, object_type=row[2]))
        return tuple(tables)

    def fetch_table_rows(
        self,
        *,
        owner: str,
        name: str,
        limit: int,
        offset: int,
    ) -> PlmRawRowsResult:
        normalized_limit = clamp_limit(limit)
        normalized_offset = normalize_offset(offset)
        sql = build_table_rows_sql(
            owner,
            name,
            limit=normalized_limit,
            offset=normalized_offset,
        )
        result = strip_internal_rownum_column(
            self.execute_grid_query(sql),
            normalized_limit,
        )
        return PlmRawRowsResult(
            columns=result.columns,
            rows=result.rows,
            has_more=result.has_more,
            limit=normalized_limit,
            offset=normalized_offset,
            sql_preview=sql,
        )

    def execute_user_query(
        self,
        *,
        sql: str,
        limit: int,
        offset: int,
    ) -> PlmRawRowsResult:
        normalized_limit = clamp_limit(limit)
        normalized_offset = normalize_offset(offset)
        wrapped_sql = build_raw_query_sql(
            sql,
            limit=normalized_limit,
            offset=normalized_offset,
        )
        result = strip_internal_rownum_column(
            self.execute_grid_query(wrapped_sql),
            normalized_limit,
        )
        return PlmRawRowsResult(
            columns=result.columns,
            rows=result.rows,
            has_more=result.has_more,
            limit=normalized_limit,
            offset=normalized_offset,
            sql_preview=wrapped_sql,
        )


def get_plm_raw_client() -> PlmRawOracleClient:
    return PlmRawOracleClient()
