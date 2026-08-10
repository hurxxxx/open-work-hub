#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent


ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
DEFAULT_OBJECTS = (
    "infodba.viewpart",
    "infodba.view_control",
    "infodba.view_material",
)
DEFAULT_OJDBC_JAR_CANDIDATES = (
    ROOT / ".runtime/ojdbc11-23.9.0.25.07.jar",
    Path("/tmp/ojdbc11-23.9.0.25.07.jar"),
    ROOT / ".runtime/ojdbc11.jar",
    Path("/tmp/ojdbc11.jar"),
)
FIELD_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]*$")


@dataclass(frozen=True)
class ConnectionInfo:
    host: str
    sid: str
    user: str
    password: str
    port: int

    @property
    def jdbc_url(self) -> str:
        return f"jdbc:oracle:thin:@{self.host}:{self.port}:{self.sid}"


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
            if raw_line.strip().split("=", 1)[1].strip().startswith('"'):
                value = bytes(value, "utf-8").decode("unicode_escape")
            else:
                value = value.replace("\\'", "'")
        values[key] = value
    return values


def env_values() -> dict[str, str]:
    values = parse_env_file(ENV_FILE)
    values.update(os.environ)
    return values


def load_connection_from_env() -> ConnectionInfo:
    values = env_values()
    required_keys = (
        "OPEN_ALM_PLM_ORACLE_HOST",
        "OPEN_ALM_PLM_ORACLE_SID",
        "OPEN_ALM_PLM_ORACLE_USER",
        "OPEN_ALM_PLM_ORACLE_PASSWORD",
    )
    missing = [key for key in required_keys if not values.get(key, "").strip()]
    if missing:
        raise ValueError(f"Missing PLM env keys: {', '.join(missing)}")
    port_text = values.get("OPEN_ALM_PLM_ORACLE_PORT", "1521").strip() or "1521"
    return ConnectionInfo(
        host=values["OPEN_ALM_PLM_ORACLE_HOST"].strip(),
        sid=values["OPEN_ALM_PLM_ORACLE_SID"].strip(),
        user=values["OPEN_ALM_PLM_ORACLE_USER"].strip(),
        password=values["OPEN_ALM_PLM_ORACLE_PASSWORD"],
        port=int(port_text),
    )


def resolve_ojdbc_jar(configured: str | None) -> Path | None:
    values = env_values()
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured).expanduser())
    env_jar = values.get("OPEN_ALM_PLM_OJDBC_JAR", "").strip()
    if env_jar:
        candidates.append(Path(env_jar).expanduser())
    candidates.extend(DEFAULT_OJDBC_JAR_CANDIDATES)
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return None


def write_java_source(path: Path) -> None:
    path.write_text(
        dedent(
            r"""
            import java.nio.file.Files;
            import java.nio.file.Path;
            import java.sql.Connection;
            import java.sql.DriverManager;
            import java.sql.ResultSet;
            import java.sql.ResultSetMetaData;
            import java.sql.SQLException;
            import java.sql.Statement;
            import java.util.Properties;
            import java.util.regex.Pattern;

            public class PlmJdbcSmoke {
                private static String redact(String input) {
                    if (input == null) {
                        return "";
                    }
                    String output = input;
                    String url = System.getenv("PLM_JDBC_URL");
                    String user = System.getenv("PLM_JDBC_USER");
                    String password = System.getenv("PLM_JDBC_PASSWORD");
                    if (url != null && !url.isBlank()) {
                        output = output.replace(url, "[JDBC_URL]");
                    }
                    if (user != null && !user.isBlank()) {
                        output = output.replace(user, "[USER]");
                    }
                    if (password != null && !password.isBlank()) {
                        output = output.replace(password, "[PASSWORD]");
                    }
                    return output.replaceAll("\\b(?:\\d{1,3}\\.){3}\\d{1,3}\\b", "[IP]");
                }

                private static void printSqlError(String label, SQLException error) {
                    System.out.println(
                        "[plm] " + label + "=failed"
                        + " vendor_code=" + error.getErrorCode()
                        + " sql_state=" + error.getSQLState()
                        + " error=" + redact(error.getMessage())
                    );
                }

                public static void main(String[] args) throws Exception {
                    if (args.length != 1) {
                        throw new IllegalArgumentException("query file path is required");
                    }
                    String url = System.getenv("PLM_JDBC_URL");
                    String user = System.getenv("PLM_JDBC_USER");
                    String password = System.getenv("PLM_JDBC_PASSWORD");
                    if (url == null || user == null || password == null) {
                        throw new IllegalStateException("JDBC env is incomplete");
                    }

                    DriverManager.setLoginTimeout(10);
                    Properties props = new Properties();
                    props.put("user", user);
                    props.put("password", password);

                    try (Connection connection = DriverManager.getConnection(url, props)) {
                        System.out.println("[plm] jdbc_connect=ok");
                        try (Statement statement = connection.createStatement()) {
                            statement.setQueryTimeout(15);
                            try (ResultSet rows = statement.executeQuery("select 1 from dual")) {
                                rows.next();
                                System.out.println("[plm] dual_select=ok value=" + rows.getInt(1));
                            }
                        }

                        for (String line : Files.readAllLines(Path.of(args[0]))) {
                            if (line.isBlank() || line.startsWith("#")) {
                                continue;
                            }
                            String[] parts = line.split("\\t", 3);
                            if (parts.length != 3) {
                                continue;
                            }
                            String kind = parts[0];
                            String name = parts[1];
                            String sql = parts[2];
                            try (Statement statement = connection.createStatement()) {
                                statement.setQueryTimeout(30);
                                if ("FIELD_CHECK".equals(kind)) {
                                    String[] expectedFields = sql.isBlank() ? new String[0] : sql.split(",");
                                    try (ResultSet describeRows = statement.executeQuery("select * from " + name + " where rownum <= 1")) {
                                            ResultSetMetaData meta = describeRows.getMetaData();
                                            java.util.Set<String> actualColumns = new java.util.HashSet<>();
                                            java.util.List<String> actualColumnList = new java.util.ArrayList<>();
                                            for (int index = 1; index <= meta.getColumnCount(); index++) {
                                                String columnName = meta.getColumnName(index);
                                                actualColumns.add(columnName.toUpperCase());
                                                actualColumnList.add(columnName);
                                            }
                                        java.util.List<String> missing = new java.util.ArrayList<>();
                                        for (String field : expectedFields) {
                                            if (!field.isBlank() && !actualColumns.contains(field.toUpperCase())) {
                                                missing.add(field);
                                            }
                                        }
                                        boolean hasRow = describeRows.next();
                                        System.out.println(
                                            "[plm] " + name + " field_check=ok"
                                            + " actual_columns=" + meta.getColumnCount()
                                                + " expected_fields=" + expectedFields.length
                                                + " missing_fields=" + missing.size()
                                                + " first_row_present=" + hasRow
                                                + " actual=" + String.join(",", actualColumnList)
                                                + (missing.isEmpty() ? "" : " missing=" + String.join(",", missing))
                                            );
                                    }
                                } else try (ResultSet rows = statement.executeQuery(sql)) {
                                    if ("SAMPLE_COUNT".equals(kind)) {
                                        rows.next();
                                        System.out.println(
                                            "[plm] " + name + " sample_count=ok rows_up_to_limit=" + rows.getInt(1)
                                        );
                                    } else if ("FULL_COUNT".equals(kind)) {
                                        rows.next();
                                        System.out.println(
                                            "[plm] " + name + " full_count=ok rows=" + rows.getLong(1)
                                        );
                                    } else if ("COLUMN_CHECK".equals(kind)) {
                                        ResultSetMetaData meta = rows.getMetaData();
                                        boolean hasRow = rows.next();
                                        System.out.println(
                                            "[plm] " + name + " column_check=ok"
                                            + " columns=" + meta.getColumnCount()
                                            + " first_row_present=" + hasRow
                                        );
                                    } else if ("BOM_QUERY".equals(kind)) {
                                        rows.next();
                                        System.out.println(
                                            "[plm] " + name + " bom_query=ok rows_up_to_limit=" + rows.getInt(1)
                                        );
                                    } else if ("OBJECT_DISCOVERY".equals(kind)) {
                                        int count = 0;
                                        StringBuilder builder = new StringBuilder();
                                        while (rows.next()) {
                                            if (count > 0) {
                                                builder.append(";");
                                            }
                                            builder.append(rows.getString(1))
                                                .append(".")
                                                .append(rows.getString(2))
                                                .append(":")
                                                .append(rows.getString(3));
                                            count++;
                                        }
                                        System.out.println(
                                            "[plm] " + name + " object_discovery=ok"
                                            + " rows=" + count
                                            + (count == 0 ? "" : " objects=" + builder.toString())
                                        );
                                    } else if ("SCALAR_ROW".equals(kind)) {
                                        if (rows.next()) {
                                            ResultSetMetaData meta = rows.getMetaData();
                                            StringBuilder builder = new StringBuilder();
                                            for (int index = 1; index <= meta.getColumnCount(); index++) {
                                                if (index > 1) {
                                                    builder.append(" ");
                                                }
                                                builder.append(meta.getColumnLabel(index))
                                                    .append("=")
                                                    .append(rows.getString(index));
                                            }
                                            System.out.println(
                                                "[plm] " + name + " scalar_row=ok " + builder.toString()
                                            );
                                        } else {
                                            System.out.println("[plm] " + name + " scalar_row=ok rows=0");
                                        }
                                    }
                                }
                            } catch (SQLException error) {
                                printSqlError(name + " " + kind.toLowerCase(), error);
                            }
                        }
                    } catch (SQLException error) {
                        printSqlError("jdbc_connect", error);
                        System.exit(2);
                    }
                }
            }
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )


def validate_object_name(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_$#]*(?:\.[A-Za-z][A-Za-z0-9_$#]*)?", name):
        raise ValueError(f"Unsafe Oracle object name: {name!r}")
    return name


def query_lines(
    objects: tuple[str, ...],
    max_sample_rows: int,
    discover_objects: bool,
    discover_constraints: bool,
    profile_keys: bool,
    full_count: bool,
) -> list[str]:
    lines: list[str] = []
    safe_objects = tuple(validate_object_name(name) for name in objects)
    for view_name in sorted(safe_objects):
        safe_view = validate_object_name(view_name)
        lines.append(
            "\t".join(
                [
                    "FULL_COUNT" if full_count else "SAMPLE_COUNT",
                    safe_view,
                    (
                        f"select count(*) from {safe_view}"
                        if full_count
                        else f"select count(*) from (select 1 from {safe_view} where rownum <= {max_sample_rows})"
                    ),
                ]
            )
        )
        lines.append(
            "\t".join(
                [
                    "COLUMN_CHECK",
                    safe_view,
                    f"select * from {safe_view} where rownum <= 1",
                ]
            )
        )
    if discover_objects:
        object_terms = sorted(
            {
                "BOM",
                "CONTROL",
                "MATERIAL",
                "OCCUR",
                "PART",
                *(
                    object_name.split(".", 1)[-1].upper().replace("VIEW_", "")
                    for object_name in safe_objects
                ),
            }
        )
        object_filters = " or ".join(f"upper(object_name) like '%{term}%'" for term in object_terms)
        synonym_filters = " or ".join(
            f"upper(synonym_name) like '%{term}%'" for term in object_terms
        )
        lines.append(
            "\t".join(
                [
                    "OBJECT_DISCOVERY",
                    "ACCESSIBLE_OBJECTS",
                    (
                        "select * from ("
                        "select owner, object_name, object_type from all_objects "
                        f"where {object_filters} "
                        "order by owner, object_name"
                        ") where rownum <= 80"
                    ),
                ]
            )
        )
        lines.append(
            "\t".join(
                [
                    "OBJECT_DISCOVERY",
                    "ACCESSIBLE_SYNONYMS",
                    (
                        "select * from ("
                        "select owner, synonym_name, table_owner || '.' || table_name from all_synonyms "
                        f"where {synonym_filters} "
                        "order by owner, synonym_name"
                        ") where rownum <= 80"
                    ),
                ]
            )
        )
        owners = sorted({view.split(".", 1)[0].upper() for view in safe_objects if "." in view})
        for owner in owners:
            if not FIELD_NAME_RE.fullmatch(owner):
                continue
            lines.append(
                "\t".join(
                    [
                        "OBJECT_DISCOVERY",
                        f"OWNER_VIEWS:{owner}",
                        (
                            "select * from ("
                            "select owner, object_name, object_type from all_objects "
                            f"where owner = '{owner}' and object_type in ('VIEW', 'SYNONYM') "
                            "order by object_name"
                            ") where rownum <= 120"
                        ),
                    ]
                )
            )
    if discover_constraints:
        target_pairs = [
            tuple(part.upper() for part in view.split(".", 1))
            for view in sorted(safe_objects)
            if "." in view
        ]
        if target_pairs:
            owners = sorted({owner for owner, _ in target_pairs})
            table_names = sorted({table for _, table in target_pairs})
            owner_filter = ", ".join(f"'{owner}'" for owner in owners)
            table_filter = ", ".join(f"'{table}'" for table in table_names)
            target_filter = f"owner in ({owner_filter}) and table_name in ({table_filter})"
            child_filter = (
                f"child.owner in ({owner_filter}) and child.table_name in ({table_filter})"
            )
            parent_filter = (
                f"parent.owner in ({owner_filter}) and parent.table_name in ({table_filter})"
            )
            lines.append(
                "\t".join(
                    [
                        "OBJECT_DISCOVERY",
                        "TARGET_CONSTRAINTS",
                        (
                            "select * from ("
                            "select owner, table_name, "
                            "constraint_type || ':' || constraint_name || "
                            "case when r_constraint_name is null then '' "
                            "else ' -> ' || r_owner || '.' || r_constraint_name end "
                            "from all_constraints "
                            f"where {target_filter} "
                            "order by owner, table_name, constraint_type, constraint_name"
                            ") where rownum <= 120"
                        ),
                    ]
                )
            )
            lines.append(
                "\t".join(
                    [
                        "OBJECT_DISCOVERY",
                        "TARGET_FK_LINKS",
                        (
                            "select * from ("
                            "select child.owner, child.table_name, "
                            "child.constraint_name || ' -> ' || parent.owner || '.' || parent.table_name "
                            "from all_constraints child "
                            "join all_constraints parent "
                            "on child.r_owner = parent.owner "
                            "and child.r_constraint_name = parent.constraint_name "
                            "where child.constraint_type = 'R' and ("
                            f"({child_filter}) or ({parent_filter})"
                            ") order by child.owner, child.table_name, child.constraint_name"
                            ") where rownum <= 120"
                        ),
                    ]
                )
            )
    if profile_keys:
        key_profiles = {
            "infodba.view_control": ('"부품번호"', '"리비전"', '"약어"'),
            "infodba.view_material": ('"MATERIAL_NO"', '"리비전"', '"약어"'),
            "infodba.viewpart": ('"부품번호"', '"리비전"', '"약어"'),
        }
        for view_name, (id_column, revision_column, acronym_column) in key_profiles.items():
            if view_name not in {name.lower() for name in safe_objects}:
                continue
            safe_view = validate_object_name(view_name)
            key_expr = f"{id_column} || chr(31) || {revision_column}"
            type_key_expr = (
                f"{acronym_column} || chr(31) || {id_column} || chr(31) || {revision_column}"
            )
            lines.append(
                "\t".join(
                    [
                        "SCALAR_ROW",
                        f"KEY_PROFILE:{safe_view}",
                        (
                            "select "
                            "count(*) total_rows, "
                            f"count(distinct {id_column}) distinct_id, "
                            f"count(distinct {key_expr}) distinct_id_revision, "
                            f"count(distinct {type_key_expr}) distinct_type_id_revision, "
                            f"sum(case when {id_column} is null then 1 else 0 end) null_id, "
                            f"sum(case when {revision_column} is null then 1 else 0 end) null_revision "
                            f"from {safe_view}"
                        ),
                    ]
                )
            )
        overlap_queries = [
            (
                "OVERLAP:viewpart_view_control_id",
                "select count(*) overlap_ids from ("
                'select distinct "부품번호" item_id from infodba.viewpart '
                "intersect "
                'select distinct "부품번호" item_id from infodba.view_control'
                ")",
            ),
            (
                "OVERLAP:viewpart_view_control_id_revision",
                "select count(*) overlap_id_revisions from ("
                'select distinct "부품번호" || chr(31) || "리비전" item_key from infodba.viewpart '
                "intersect "
                'select distinct "부품번호" || chr(31) || "리비전" item_key from infodba.view_control'
                ")",
            ),
            (
                "OVERLAP:viewpart_view_material_id",
                "select count(*) overlap_ids from ("
                'select distinct "부품번호" item_id from infodba.viewpart '
                "intersect "
                'select distinct "MATERIAL_NO" item_id from infodba.view_material'
                ")",
            ),
        ]
        for label, sql in overlap_queries:
            lines.append("\t".join(["SCALAR_ROW", label, sql]))
    return lines


def run_smoke(args: argparse.Namespace) -> int:
    ojdbc_jar = resolve_ojdbc_jar(args.ojdbc_jar)
    if ojdbc_jar is None:
        print("[plm] ojdbc_jar=missing", file=sys.stderr)
        return 2
    objects = tuple(args.object or DEFAULT_OBJECTS)
    try:
        connection = load_connection_from_env()
        safe_objects = tuple(validate_object_name(name) for name in objects)
    except ValueError as error:
        print(f"[plm] config=invalid error={error}", file=sys.stderr)
        return 2
    if not ojdbc_jar.exists():
        print(f"[plm] ojdbc_jar=missing path={ojdbc_jar}", file=sys.stderr)
        return 2

    print(f"[plm] config=parse_ok objects={len(safe_objects)}")

    with tempfile.TemporaryDirectory(prefix="plm-jdbc-smoke-") as temp_root:
        temp_dir = Path(temp_root)
        java_file = temp_dir / "PlmJdbcSmoke.java"
        query_file = temp_dir / "queries.tsv"
        write_java_source(java_file)
        query_file.write_text(
            "\n".join(
                query_lines(
                    safe_objects,
                    args.max_sample_rows,
                    args.discover_objects,
                    args.discover_constraints,
                    args.profile_keys,
                    args.full_count,
                )
            )
            + "\n",
            encoding="utf-8",
        )

        compile_result = subprocess.run(
            ["javac", "-cp", str(ojdbc_jar), str(java_file)],
            text=True,
            capture_output=True,
            check=False,
        )
        if compile_result.returncode != 0:
            print("[plm] javac=failed", file=sys.stderr)
            print(compile_result.stderr, file=sys.stderr)
            return compile_result.returncode

        env = os.environ.copy()
        env.update(
            {
                "PLM_JDBC_URL": connection.jdbc_url,
                "PLM_JDBC_USER": connection.user,
                "PLM_JDBC_PASSWORD": connection.password,
            }
        )
        run_result = subprocess.run(
            [
                "java",
                "-cp",
                f"{ojdbc_jar}:{temp_dir}",
                "PlmJdbcSmoke",
                str(query_file),
            ],
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )
        print(run_result.stdout, end="")
        if run_result.stderr:
            print(run_result.stderr, file=sys.stderr, end="")
        return run_result.returncode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a redacted read-only PLM Oracle JDBC smoke check from OPEN_ALM_PLM_* env."
    )
    parser.add_argument("--ojdbc-jar")
    parser.add_argument(
        "--object",
        action="append",
        help="Oracle object to inspect. Defaults to the known read-only PLM views.",
    )
    parser.add_argument("--max-sample-rows", type=int, default=100)
    parser.add_argument(
        "--full-count",
        action="store_true",
        help="Run exact count(*) on configured objects instead of row-limited sample counts.",
    )
    parser.add_argument(
        "--discover-objects",
        action="store_true",
        help="Search accessible object and synonym metadata for PLM/BOM candidate names.",
    )
    parser.add_argument(
        "--discover-constraints",
        action="store_true",
        help="Search accessible Oracle constraint metadata for configured objects.",
    )
    parser.add_argument(
        "--profile-keys",
        action="store_true",
        help="Count distinct candidate business keys and overlaps across accessible views.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run_smoke(parse_args()))
