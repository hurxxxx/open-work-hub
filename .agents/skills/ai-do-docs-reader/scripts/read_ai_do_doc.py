#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


ENVIRONMENTS = {
    "dev": {
        "pg_host": "127.0.0.1",
        "pg_port": "5432",
        "pg_user": "ai_do_dev",
        "pg_db": "ai_do_dev",
        "minio_container": "ai-do-dev-minio",
        "bucket": "ai-do-dev",
    },
    "prod": {
        "pg_host": "127.0.0.1",
        "pg_port": "5432",
        "pg_user": "ai_do_prod",
        "pg_db": "ai_do_prod",
        "minio_container": "ai-do-prod-minio",
        "bucket": "ai-do-prod",
    },
}

CHECKOUTS = {
    "dev": Path("/projects/ai-do/dev"),
    "prod": Path("/projects/ai-do/prod"),
}

UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,80}$")
MEDIA_RE = re.compile(r"media:([0-9a-fA-F-]{36})")


def run(
    cmd: list[str],
    *,
    check: bool = True,
    env: dict[str, str] | None = None,
    display_cmd: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    if check and result.returncode != 0:
        shown = display_cmd or cmd
        raise RuntimeError(
            f"command failed: {' '.join(shlex.quote(part) for part in shown)}\n{result.stderr.strip()}"
        )
    return result


def env_file_value(path: Path, name: str) -> str | None:
    if not path.exists():
        return None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        key, separator, value = line.partition("=")
        if separator != "=" or key.strip() != name:
            continue
        parsed = value.strip()
        if len(parsed) >= 2 and parsed[0] == parsed[-1] and parsed[0] in {"'", '"'}:
            parsed = parsed[1:-1]
        return parsed
    return None


def postgres_dsn(env: str) -> str | None:
    configured = os.getenv(f"AI_DO_DOCS_READER_{env.upper()}_POSTGRES_DSN")
    if configured:
        return configured
    profile = os.getenv("AI_DO_ENV_PROFILE")
    if profile == env and os.getenv("AI_DO_POSTGRES_DSN"):
        return os.getenv("AI_DO_POSTGRES_DSN")
    checkout = CHECKOUTS[env]
    for env_file in (checkout / ".env", checkout / ".env.local"):
        configured = env_file_value(env_file, "AI_DO_POSTGRES_DSN")
        if configured:
            return configured
    return None


def psql_connection(env: str) -> tuple[list[str], dict[str, str]]:
    cfg = ENVIRONMENTS[env]
    dsn = postgres_dsn(env)
    env_values = os.environ.copy()
    if not dsn:
        return (
            [
                "psql",
                "-h",
                cfg["pg_host"],
                "-p",
                cfg["pg_port"],
                "-U",
                cfg["pg_user"],
                "-d",
                cfg["pg_db"],
            ],
            env_values,
        )

    parsed = urlparse(dsn.replace("postgresql+psycopg://", "postgresql://", 1))
    host = parsed.hostname or cfg["pg_host"]
    port = str(parsed.port or cfg["pg_port"])
    user = unquote(parsed.username or cfg["pg_user"])
    database = unquote((parsed.path or f"/{cfg['pg_db']}").lstrip("/"))
    if parsed.password:
        env_values["PGPASSWORD"] = unquote(parsed.password)
    return (["psql", "-h", host, "-p", port, "-U", user, "-d", database], env_values)


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def validate_uuid(value: str, name: str) -> str:
    if not UUID_RE.match(value):
        raise ValueError(f"{name} must be a UUID: {value}")
    return value.lower()


def validate_slug(value: str) -> str:
    if not SLUG_RE.match(value):
        raise ValueError(f"workspace slug is invalid: {value}")
    return value


def parse_target(target: str | None) -> dict[str, str]:
    if not target:
        return {}
    if UUID_RE.match(target):
        return {"doc_id": target.lower()}

    parsed = urlparse(target)
    path = parsed.path or target
    match = re.search(r"/w/([^/]+)/docs/([0-9a-fA-F-]{36})", path)
    if not match:
        raise ValueError(
            "target must be a /w/{workspace}/docs/{doc_id}?page={page_id} URL/path or a doc UUID"
        )

    values = {
        "workspace": validate_slug(match.group(1)),
        "doc_id": validate_uuid(match.group(2), "doc_id"),
    }
    page_values = parse_qs(parsed.query).get("page")
    if page_values and page_values[0]:
        values["page_id"] = validate_uuid(page_values[0], "page_id")
    return values


def env_names(selection: str) -> list[str]:
    if selection == "all":
        return ["dev", "prod"]
    return [selection]


def psql_json(env: str, sql: str) -> list[dict]:
    psql, psql_env = psql_connection(env)
    result = run(
        [
            *psql,
            "-X",
            "-v",
            "ON_ERROR_STOP=1",
            "-Atc",
            sql,
        ],
        env=psql_env,
    )
    raw = result.stdout.strip()
    if not raw:
        return []
    return json.loads(raw)


def read_query(workspace: str, doc_id: str, page_id: str | None) -> str:
    page_clause = f"and p.id = {sql_literal(page_id)}" if page_id else ""
    return f"""
select coalesce(json_agg(row_to_json(t)), '[]'::json)
from (
  select
    w.key as workspace,
    d.id as doc_id,
    d.title as doc_title,
    d.updated_at::text as doc_updated_at,
    p.id as page_id,
    p.title as page_title,
    p.content_format,
    p.content_text,
    p.content_blocks,
    p.updated_at::text as page_updated_at,
    p.sort_order
  from docs_native_docs d
  join docs_native_doc_pages p on p.doc_id = d.id
  join workspaces w on w.id = d.workspace_id
  where w.key = {sql_literal(workspace)}
    and d.id = {sql_literal(doc_id)}
    {page_clause}
    and d.trashed_at is null
    and p.trashed_at is null
  order by p.sort_order, p.created_at
) t;
"""


def updates_query(workspace: str, doc_id: str | None, since: str | None, limit: int) -> str:
    doc_clause = f"and d.id = {sql_literal(doc_id)}" if doc_id else ""
    since_clause = ""
    if since:
        since_clause = f"and (d.updated_at >= {sql_literal(since)}::timestamp or p.updated_at >= {sql_literal(since)}::timestamp)"
    return f"""
select coalesce(json_agg(row_to_json(t)), '[]'::json)
from (
  select
    w.key as workspace,
    d.id as doc_id,
    d.title as doc_title,
    d.updated_at::text as doc_updated_at,
    p.id as page_id,
    p.title as page_title,
    p.content_format,
    p.updated_at::text as page_updated_at,
    greatest(d.updated_at, p.updated_at)::text as latest_updated_at,
    coalesce(length(p.content_text), 0) as content_text_chars,
    case
      when json_typeof(p.content_blocks) = 'array' then json_array_length(p.content_blocks)
      else 0
    end as block_count
  from docs_native_docs d
  join docs_native_doc_pages p on p.doc_id = d.id
  join workspaces w on w.id = d.workspace_id
  where w.key = {sql_literal(workspace)}
    {doc_clause}
    {since_clause}
    and d.trashed_at is null
    and p.trashed_at is null
  order by greatest(d.updated_at, p.updated_at) desc
  limit {max(1, min(limit, 200))}
) t;
"""


def media_query(media_ids: list[str]) -> str:
    values = ", ".join(sql_literal(validate_uuid(item, "media_id")) for item in media_ids)
    return f"""
select coalesce(json_agg(row_to_json(t)), '[]'::json)
from (
  select
    id,
    filename,
    content_type,
    size_bytes,
    storage_key,
    resource_type,
    resource_id,
    created_at::text as created_at
  from media_files
  where id in ({values})
  order by created_at, filename
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
            name = props.get("name") or "image"
            url = props.get("url") or ""
            line = f"{prefix}[image: {name} {url}]".rstrip()
        else:
            text = inline_text(block.get("content"))
            if block_type == "bulletListItem" and text:
                line = f"{prefix}- {text}"
            elif block_type == "numberedListItem" and text:
                start = props.get("start") or 1
                line = f"{prefix}{start}. {text}"
            else:
                line = f"{prefix}{text}"
        if line.strip():
            lines.append(line)
        children = block.get("children")
        if children:
            lines.extend(blocks_to_lines(children, indent + 2))
    return lines


def media_ids_from_pages(pages: list[dict]) -> list[str]:
    found: set[str] = set()
    for page in pages:
        payload = json.dumps(page.get("content_blocks"), ensure_ascii=False)
        payload += "\n" + (page.get("content_text") or "")
        for match in MEDIA_RE.finditer(payload):
            if UUID_RE.match(match.group(1)):
                found.add(match.group(1).lower())
    return sorted(found)


def render_page(env: str, page: dict, media_rows: list[dict]) -> str:
    lines = [
        f"# {page['page_title']}",
        "",
        f"- env: {env}",
        f"- workspace: {page['workspace']}",
        f"- doc: {page['doc_title']} ({page['doc_id']})",
        f"- page: {page['page_title']} ({page['page_id']})",
        f"- doc_updated_at: {page['doc_updated_at']}",
        f"- page_updated_at: {page['page_updated_at']}",
        f"- content_format: {page['content_format']}",
        "",
        "## Content",
    ]
    content_text = page.get("content_text")
    content_lines = [content_text] if content_text else blocks_to_lines(page.get("content_blocks"))
    lines.extend(content_lines or ["(empty)"])
    if media_rows:
        lines.extend(["", "## Embedded Media"])
        for media in media_rows:
            lines.append(
                "- {filename} media:{id} {content_type} {size_bytes} bytes storage_key={storage_key}".format(
                    **media
                )
            )
            copied_to = media.get("copied_to")
            if copied_to:
                lines.append(f"  copied_to={copied_to}")
    return "\n".join(lines)


def render_updates(env: str, rows: list[dict]) -> str:
    lines = [f"# AI-DO Docs Updates ({env})", ""]
    if not rows:
        lines.append("(no matching updates)")
        return "\n".join(lines)
    for row in rows:
        lines.append(
            "- {latest_updated_at} | {doc_title} / {page_title} | doc={doc_id} page={page_id} | "
            "doc_updated={doc_updated_at} page_updated={page_updated_at} | blocks={block_count} text_chars={content_text_chars}".format(
                **row
            )
        )
    return "\n".join(lines)


def copy_media(env: str, rows: list[dict], destination: Path) -> list[dict]:
    cfg = ENVIRONMENTS[env]
    destination.mkdir(parents=True, exist_ok=True)
    copied: list[dict] = []
    for media in rows:
        filename = os.path.basename(media["filename"]) or f"{media['id']}.bin"
        local_name = f"{env}-{media['id']}-{filename}"
        container_tmp = f"/tmp/{local_name}"
        source = f"local/{cfg['bucket']}/{media['storage_key']}"
        shell_cmd = (
            'mc alias set local http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null'
            f" && mc cp {shlex.quote(source)} {shlex.quote(container_tmp)} >/dev/null"
        )
        run(["docker", "exec", cfg["minio_container"], "/bin/sh", "-lc", shell_cmd])
        host_path = destination / local_name
        run(["docker", "cp", f"{cfg['minio_container']}:{container_tmp}", str(host_path)])
        updated = dict(media)
        updated["copied_to"] = str(host_path)
        copied.append(updated)
    return copied


def read_doc(args: argparse.Namespace) -> int:
    target_values = parse_target(args.target)
    workspace = validate_slug(args.workspace or target_values.get("workspace") or "")
    doc_id = validate_uuid(args.doc_id or target_values.get("doc_id") or "", "doc_id")
    page_id = args.page_id or target_values.get("page_id")
    if page_id:
        page_id = validate_uuid(page_id, "page_id")

    found = False
    for env in env_names(args.env):
        try:
            pages = psql_json(env, read_query(workspace, doc_id, page_id))
        except Exception as exc:
            print(f"[{env}] {exc}", file=sys.stderr)
            continue
        if not pages:
            continue
        found = True
        media_ids = media_ids_from_pages(pages)
        media_rows = psql_json(env, media_query(media_ids)) if media_ids else []
        if args.copy_media and media_rows:
            media_rows = copy_media(env, media_rows, Path(args.copy_media))
        for index, page in enumerate(pages):
            if index:
                print("\n---\n")
            print(render_page(env, page, media_rows))
    if not found:
        print("No matching document/page found.", file=sys.stderr)
        return 1
    return 0


def list_updates(args: argparse.Namespace) -> int:
    target_values = parse_target(args.target)
    workspace = validate_slug(args.workspace or target_values.get("workspace") or "")
    doc_id = args.doc_id or target_values.get("doc_id")
    if doc_id:
        doc_id = validate_uuid(doc_id, "doc_id")

    found_any = False
    for env in env_names(args.env):
        try:
            rows = psql_json(env, updates_query(workspace, doc_id, args.since, args.limit))
        except Exception as exc:
            print(f"[{env}] {exc}", file=sys.stderr)
            continue
        if rows:
            found_any = True
        print(render_updates(env, rows))
        if env != env_names(args.env)[-1]:
            print("\n---\n")
    return 0 if found_any else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read AI-DO Docs pages or list recently updated Docs pages."
    )
    parser.add_argument(
        "target",
        nargs="?",
        help="/w/{workspace}/docs/{doc_id}?page={page_id}, full URL, or doc UUID",
    )
    parser.add_argument(
        "--env", choices=["all", "dev", "prod"], default="all", help="environment to query"
    )
    parser.add_argument("--workspace", help="workspace slug, e.g. ai-tft")
    parser.add_argument("--doc-id", help="doc UUID")
    parser.add_argument("--page-id", help="page UUID")
    parser.add_argument(
        "--updates",
        action="store_true",
        help="list recently updated pages instead of reading content",
    )
    parser.add_argument("--since", help="filter updates on or after a timestamp, e.g. 2026-05-20")
    parser.add_argument("--limit", type=int, default=20, help="max update rows per environment")
    parser.add_argument("--copy-media", help="copy embedded media files to this host directory")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.updates:
            return list_updates(args)
        return read_doc(args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
