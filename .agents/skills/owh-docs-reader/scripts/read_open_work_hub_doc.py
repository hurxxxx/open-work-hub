#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parents[4]
UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,80}$")
MEDIA_RE = re.compile(r"media:([0-9a-fA-F-]{36})")
COMMAND_TIMEOUT_SECONDS = 30
MAX_MEDIA_BYTES = 50 * 1024 * 1024
MAX_MEDIA_COUNT = 20


def run(
    command: list[str],
    *,
    check: bool = True,
    env: dict[str, str] | None = None,
    display_command: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, timeout=COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("local read command timed out") from None
    if check and result.returncode != 0:
        # Driver errors can contain SQL, document contents, DSNs, or credentials.
        raise RuntimeError("local read command failed; inspect local service health without exposing logs")
    return result


def env_file_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        key, separator, value = line.partition("=")
        if separator != "=" or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key.strip()):
            continue
        parsed = value.strip()
        if len(parsed) >= 2 and parsed[0] == parsed[-1] and parsed[0] in {"'", '"'}:
            parsed = parsed[1:-1]
        values[key.strip()] = parsed
    return values


@lru_cache(maxsize=1)
def file_env() -> dict[str, str]:
    # --help and importing the module never read ignored env files.
    return {**env_file_values(ROOT / ".env"), **env_file_values(ROOT / ".env.local")}


def setting(name: str, default: str = "") -> str:
    return os.getenv(name) or file_env().get(name) or default


def local_config() -> dict[str, str]:
    if ROOT.name == "prod" or setting("OPEN_WORK_HUB_ENV_PROFILE", "dev") not in {"local", "dev"}:
        raise RuntimeError("Docs reader requires a local development profile and checkout")
    user = setting("OPEN_WORK_HUB_INFRA_POSTGRES_USER", "open_work_hub_dev")
    password = setting("OPEN_WORK_HUB_INFRA_POSTGRES_PASSWORD", "open_work_hub_dev")
    database = setting("OPEN_WORK_HUB_INFRA_POSTGRES_DB", "open_work_hub_dev")
    port = setting("OPEN_WORK_HUB_INFRA_POSTGRES_PORT", "55433")
    prefix = setting("OPEN_WORK_HUB_INFRA_CONTAINER_PREFIX", "open-work-hub-dev")
    dsn = setting(
        "OPEN_WORK_HUB_POSTGRES_DSN",
        f"postgresql+psycopg://{user}:{password}@127.0.0.1:{port}/{database}",
    )
    parsed = urlparse(dsn.replace("postgresql+psycopg://", "postgresql://", 1))
    # Match the dev identity, not just a loopback address (prod may also be local).
    if (
        prefix != "open-work-hub-dev"
        or database != "open_work_hub_dev"
        or parsed.scheme != "postgresql"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.port != int(port)
        or parsed.port in {5432, 55432}
        or unquote(parsed.path.lstrip("/")) != database
        or parsed.query or parsed.fragment
    ):
        raise RuntimeError("Docs reader refuses a non-dev database identity; use the documented local dev configuration")
    bucket = setting("OPEN_WORK_HUB_MINIO_BUCKET", "open-work-hub-dev")
    if bucket != "open-work-hub-dev":
        raise RuntimeError("Docs reader refuses a non-dev storage bucket")
    return {
        "dsn": dsn,
        "pg_user": user,
        "pg_db": database,
        "pg_container": f"{prefix}-postgres",
        "minio_container": f"{prefix}-minio",
        "bucket": bucket,
    }


def container_running(name: str) -> bool:
    if not shutil.which("docker"):
        return False
    result = run(
        ["docker", "inspect", "-f", '{{.State.Running}}|{{index .Config.Labels "com.docker.compose.project"}}', name],
        check=False,
    )
    if result.returncode != 0:
        return False
    running, _, project = result.stdout.strip().partition("|")
    if project != "open-work-hub-dev":
        raise RuntimeError("Docs reader refuses a container without the dev Compose identity")
    return running == "true"


def psql_command() -> tuple[list[str], dict[str, str], list[str]]:
    config = local_config()
    if container_running(config["pg_container"]):
        command = [
            "docker",
            "exec",
            "-e",
            "PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=20000",
            config["pg_container"],
            "psql",
            "-U",
            config["pg_user"],
            "-d",
            config["pg_db"],
        ]
        return command, os.environ.copy(), command

    if not shutil.which("psql"):
        raise RuntimeError(
            f"local PostgreSQL container {config['pg_container']!r} is not running "
            "and host psql is unavailable; start local dev infra first"
        )

    parsed = urlparse(config["dsn"].replace("postgresql+psycopg://", "postgresql://", 1))
    host = parsed.hostname or "127.0.0.1"
    port = str(parsed.port or 5432)
    user = unquote(parsed.username or config["pg_user"])
    database = unquote((parsed.path or f"/{config['pg_db']}").lstrip("/"))
    command = ["psql", "-h", host, "-p", port, "-U", user, "-d", database]
    process_env = os.environ.copy()
    process_env["PGOPTIONS"] = "-c default_transaction_read_only=on -c statement_timeout=20000"
    process_env["PGCONNECT_TIMEOUT"] = "5"
    if parsed.password:
        process_env["PGPASSWORD"] = unquote(parsed.password)
    display = ["psql", "-h", host, "-p", port, "-U", user, "-d", database]
    return command, process_env, display


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def validate_uuid(value: str, name: str) -> str:
    if not UUID_RE.fullmatch(value):
        raise ValueError(f"{name} must be a UUID: {value}")
    return value.lower()


def validate_slug(value: str) -> str:
    if not SLUG_RE.fullmatch(value):
        raise ValueError(f"workspace slug is invalid: {value}")
    return value


def parse_target(target: str | None) -> dict[str, str]:
    if not target:
        return {}
    if UUID_RE.fullmatch(target):
        return {"doc_id": target.lower()}
    parsed = urlparse(target)
    match = re.search(r"/w/([^/]+)/docs/([0-9a-fA-F-]{36})", parsed.path or target)
    if not match:
        raise ValueError(
            "target must be a /w/{workspace}/docs/{doc_id}?page={page_id} URL/path or doc UUID"
        )
    values = {
        "workspace": validate_slug(match.group(1)),
        "doc_id": validate_uuid(match.group(2), "doc_id"),
    }
    page_values = parse_qs(parsed.query).get("page")
    if page_values and page_values[0]:
        values["page_id"] = validate_uuid(page_values[0], "page_id")
    return values


def psql_json(sql: str) -> list[dict]:
    command, process_env, display = psql_command()
    result = run(
        [*command, "-X", "-v", "ON_ERROR_STOP=1", "-Atc", sql],
        env=process_env,
        display_command=[*display, "-X", "-v", "ON_ERROR_STOP=1", "-Atc", "<read-only SQL>"],
    )
    raw = result.stdout.strip()
    return json.loads(raw) if raw else []


def read_query(workspace: str, doc_id: str, page_id: str | None) -> str:
    page_clause = f"and p.id = {sql_literal(page_id)}" if page_id else ""
    return f"""
select coalesce(json_agg(row_to_json(t)), '[]'::json)
from (
  select w.key as workspace, d.id as doc_id, d.title as doc_title,
    d.updated_at::text as doc_updated_at, p.id as page_id,
    p.title as page_title, p.content_format, p.content_text, p.content_blocks,
    p.updated_at::text as page_updated_at, p.sort_order
  from docs_native_docs d
  join docs_native_doc_pages p on p.doc_id = d.id
  join workspaces w on w.id = d.workspace_id
  where w.key = {sql_literal(workspace)}
    and d.id = {sql_literal(doc_id)}
    {page_clause}
    and d.trashed_at is null and p.trashed_at is null
  order by p.sort_order, p.created_at
) t;
"""


def updates_query(workspace: str, doc_id: str | None, since: str | None, limit: int) -> str:
    doc_clause = f"and d.id = {sql_literal(doc_id)}" if doc_id else ""
    since_clause = ""
    if since:
        since_clause = (
            "and (d.updated_at >= "
            f"{sql_literal(since)}::timestamp or p.updated_at >= {sql_literal(since)}::timestamp)"
        )
    return f"""
select coalesce(json_agg(row_to_json(t)), '[]'::json)
from (
  select w.key as workspace, d.id as doc_id, d.title as doc_title,
    d.updated_at::text as doc_updated_at, p.id as page_id, p.title as page_title,
    p.content_format, p.updated_at::text as page_updated_at,
    greatest(d.updated_at, p.updated_at)::text as latest_updated_at,
    coalesce(length(p.content_text), 0) as content_text_chars,
    case when json_typeof(p.content_blocks) = 'array'
      then json_array_length(p.content_blocks) else 0 end as block_count
  from docs_native_docs d
  join docs_native_doc_pages p on p.doc_id = d.id
  join workspaces w on w.id = d.workspace_id
  where w.key = {sql_literal(workspace)} {doc_clause} {since_clause}
    and d.trashed_at is null and p.trashed_at is null
  order by greatest(d.updated_at, p.updated_at) desc
  limit {max(1, min(limit, 200))}
) t;
"""


def media_query(media_ids: list[str]) -> str:
    values = ", ".join(sql_literal(validate_uuid(item, "media_id")) for item in media_ids)
    return f"""
select coalesce(json_agg(row_to_json(t)), '[]'::json)
from (
  select id, filename, content_type, size_bytes, storage_key, resource_type,
    resource_id, created_at::text as created_at
  from media_files where id in ({values}) order by created_at, filename
) t;
"""


def inline_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif "content" in item:
                    parts.append(inline_text(item["content"]))
            else:
                parts.append(inline_text(item))
        return "".join(parts)
    return ""


def blocks_to_lines(blocks: object, indent: int = 0) -> list[str]:
    if not isinstance(blocks, list):
        return []
    lines: list[str] = []
    prefix = " " * indent
    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        props = block.get("props") if isinstance(block.get("props"), dict) else {}
        if block_type == "image":
            line = f"{prefix}[image: {props.get('name') or 'image'} {props.get('url') or ''}]".rstrip()
        else:
            value = inline_text(block.get("content"))
            if block_type == "bulletListItem" and value:
                line = f"{prefix}- {value}"
            elif block_type == "numberedListItem" and value:
                line = f"{prefix}{props.get('start') or 1}. {value}"
            else:
                line = f"{prefix}{value}"
        if line.strip():
            lines.append(line)
        lines.extend(blocks_to_lines(block.get("children"), indent + 2))
    return lines


def media_ids_from_pages(pages: list[dict]) -> list[str]:
    found: set[str] = set()
    for page in pages:
        payload = json.dumps(page.get("content_blocks"), ensure_ascii=False)
        payload += "\n" + (page.get("content_text") or "")
        for match in MEDIA_RE.finditer(payload):
            if UUID_RE.fullmatch(match.group(1)):
                found.add(match.group(1).lower())
    return sorted(found)


def copy_media(rows: list[dict], destination: Path) -> list[dict]:
    if len(rows) > MAX_MEDIA_COUNT:
        raise ValueError("too many media files; request a narrower document/page")
    for media in rows:
        validate_uuid(media["id"], "media_id")
        if not isinstance(media.get("size_bytes"), int) or not 0 <= media["size_bytes"] <= MAX_MEDIA_BYTES:
            raise ValueError("media file exceeds the 50 MiB local copy limit")
        key = media.get("storage_key", "")
        if not key or key.startswith("/") or any(part in {"", ".", ".."} for part in key.split("/")):
            raise ValueError("invalid storage object key")
    config = local_config()
    container = config["minio_container"]
    if not container_running(container):
        raise RuntimeError(f"local MinIO container is not running: {container}")
    destination.mkdir(parents=True, exist_ok=True)
    copied: list[dict] = []
    for media in rows:
        filename = os.path.basename(media["filename"]) or f"{media['id']}.bin"
        local_name = f"local-{media['id']}-{filename}"
        host_path = destination / local_name
        if host_path.exists() or host_path.is_symlink():
            raise ValueError("media copy destination already exists; choose an empty output directory")
        container_dir = run(["docker", "exec", container, "mktemp", "-d", "/tmp/owh-doc-media.XXXXXXXX"]).stdout.strip()
        if not re.fullmatch(r"/tmp/owh-doc-media\.[A-Za-z0-9]{8}", container_dir):
            raise RuntimeError("unexpected container temporary directory")
        container_tmp = f"{container_dir}/object"
        source = f"local/{config['bucket']}/{media['storage_key']}"
        # Official global option: https://min.io/docs/minio/linux/reference/minio-mc.html
        mc = f"mc --config-dir {shlex.quote(container_dir + '/config')}"
        try:
            # Isolated mc config, bounded output file, no shared alias mutation.
            shell_command = (
                f"ulimit -f {MAX_MEDIA_BYTES // 512}; "
                f'{mc} alias set local http://127.0.0.1:9000 "$MINIO_ROOT_USER" '
                '"$MINIO_ROOT_PASSWORD" >/dev/null'
                f" && {mc} cp {shlex.quote(source)} {shlex.quote(container_tmp)} >/dev/null"
            )
            run(["docker", "exec", container, "/bin/sh", "-lc", shell_command])
            with tempfile.TemporaryDirectory(prefix="owh-doc-media-", dir=destination) as staging:
                staged = Path(staging) / "object"
                run(["docker", "cp", f"{container}:{container_tmp}", str(staged)])
                if staged.is_symlink() or not staged.is_file() or staged.stat().st_size > MAX_MEDIA_BYTES:
                    raise ValueError("copied media is invalid or oversized")
                # Atomic no-clobber publication; never follow an existing target symlink.
                staged.chmod(0o600)
                os.link(staged, host_path)
        finally:
            run(["docker", "exec", container, "rm", "-rf", "--", container_dir])
        updated = dict(media)
        updated["copied_to"] = str(host_path)
        copied.append(updated)
    return copied


def render_page(page: dict, media_rows: list[dict]) -> str:
    lines = [
        f"# {page['page_title']}", "", "- environment: local",
        f"- workspace: {page['workspace']}",
        f"- doc: {page['doc_title']} ({page['doc_id']})",
        f"- page: {page['page_title']} ({page['page_id']})",
        f"- doc_updated_at: {page['doc_updated_at']}",
        f"- page_updated_at: {page['page_updated_at']}",
        f"- content_format: {page['content_format']}", "", "## Content",
    ]
    lines.extend(
        [page["content_text"]]
        if page.get("content_text")
        else blocks_to_lines(page.get("content_blocks")) or ["(empty)"]
    )
    if media_rows:
        lines.extend(["", "## Embedded Media"])
        for media in media_rows:
            lines.append(
                "- {filename} media:{id} {content_type} {size_bytes} bytes".format(**media)
            )
            if media.get("copied_to"):
                lines.append(f"  copied_to={media['copied_to']}")
    return "\n".join(lines)


def read_doc(args: argparse.Namespace) -> int:
    target = parse_target(args.target)
    workspace = validate_slug(args.workspace or target.get("workspace") or "")
    doc_id = validate_uuid(args.doc_id or target.get("doc_id") or "", "doc_id")
    page_id = args.page_id or target.get("page_id")
    if page_id:
        page_id = validate_uuid(page_id, "page_id")
    pages = psql_json(read_query(workspace, doc_id, page_id))
    if not pages:
        print("No matching local document/page found.", file=sys.stderr)
        return 1
    media_ids = media_ids_from_pages(pages)
    media_rows = psql_json(media_query(media_ids)) if media_ids else []
    if args.copy_media and media_rows:
        media_rows = copy_media(media_rows, Path(args.copy_media))
    for index, page in enumerate(pages):
        if index:
            print("\n---\n")
        print(render_page(page, media_rows))
    return 0


def list_updates(args: argparse.Namespace) -> int:
    target = parse_target(args.target)
    workspace = validate_slug(args.workspace or target.get("workspace") or "")
    doc_id = args.doc_id or target.get("doc_id")
    if doc_id:
        doc_id = validate_uuid(doc_id, "doc_id")
    rows = psql_json(updates_query(workspace, doc_id, args.since, args.limit))
    print("# Open Work Hub Docs Updates (local)\n")
    if not rows:
        print("(no matching updates)")
        return 1
    for row in rows:
        print(
            "- {latest_updated_at} | {doc_title} / {page_title} | "
            "doc={doc_id} page={page_id} | doc_updated={doc_updated_at} "
            "page_updated={page_updated_at} | blocks={block_count} "
            "text_chars={content_text_chars}".format(**row)
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read local Open Work Hub Docs pages or list recently updated pages."
    )
    parser.add_argument(
        "target", nargs="?",
        help="/w/{workspace}/docs/{doc_id}?page={page_id}, full URL, or doc UUID",
    )
    parser.add_argument("--workspace", help="workspace slug, for example general")
    parser.add_argument("--doc-id", help="doc UUID")
    parser.add_argument("--page-id", help="page UUID")
    parser.add_argument("--updates", action="store_true", help="list updates instead of content")
    parser.add_argument("--since", help="filter updates on or after an ISO timestamp")
    parser.add_argument("--limit", type=int, default=20, help="maximum update rows")
    parser.add_argument("--copy-media", help="copy embedded media to this local directory")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return list_updates(args) if args.updates else read_doc(args)
    except Exception:
        print("error: local Docs read failed; check the dev profile, local service health, input IDs, and media limits. No connection details or raw logs were emitted.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
