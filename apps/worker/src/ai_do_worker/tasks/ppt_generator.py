"""PPT 자동 생성 워커 태스크.

HTML 우선 흐름: 미리보기는 프론트가 slides_spec 을 HTML 로 렌더하고, .pptx 는
'PPT로 전환'(finalize) 단계에서만 빌드한다. 따라서 generate/chat_edit 은 더 이상
LibreOffice 변환·PNG 렌더를 수행하지 않는다.

  - ppt_generator.generate  : 주제/자료 → LLM 슬라이드 JSON → slides_spec 저장 (완료)
  - ppt_generator.chat_edit : 챗봇 수정 한 턴 → slides_spec 1장 갱신 (프론트가 HTML 재렌더)
  - ppt_generator.finalize  : slides_spec → .pptx 빌드 → MinIO 업로드 (다운로드 활성)
"""

from __future__ import annotations

import base64
import copy
import io
import logging
import math
import os
import re
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from celery.signals import worker_ready
from sqlalchemy import text as _sa_text

from ai_do_worker.celery_app import celery_app
from ai_do_worker.runtime import (
    db_session_scope as _db_session_scope,
    ensure_api_src_on_path as _ensure_api_src_on_path,
    minio_client as _minio_client,
)
from ai_do_worker.settings import get_settings

_ensure_api_src_on_path()

from pptx import Presentation  # noqa: E402
from sqlalchemy.orm.attributes import flag_modified  # noqa: E402

from ai_do_api.core.llm import LlmTaskContext  # noqa: E402
from ai_do_api.domains.ai.external_gateway import (  # noqa: E402
    AiExternalCapabilityPolicyViolation,
    AiExternalCapabilityRequest,
    begin_external_capability,
)
from ai_do_api.domains.ai.gateway import (  # noqa: E402
    LlmWorkloadContext,
    execute_llm,
    resolve_llm_workload_route,
)
from ai_do_api.domains.conversations import app_persistence  # noqa: E402
from ai_do_api.domains.conversations.models import Conversation  # noqa: E402
from ai_do_api.domains.ppt_generator import parsing, prompts  # noqa: E402
from ai_do_api.domains.ppt_generator import (  # noqa: E402
    PPT_DESIGN_WORKLOAD_ID,
    PPT_RESEARCH_WORKLOAD_ID,
)
from ai_do_api.domains.ppt_generator.anthropic_search_adapter import (  # noqa: E402
    AnthropicWebResearchAuthenticationError,
    run_anthropic_web_research,
)
from ai_do_api.domains.ppt_generator import service as ppt_service  # noqa: E402
from ai_do_api.domains.ppt_generator import source_images as src_images  # noqa: E402
from ai_do_api.domains.ppt_generator import ole_embed as ole  # noqa: E402
from ai_do_api.domains.ppt_generator.families import resolve_family  # noqa: E402
from ai_do_api.domains.ppt_generator.models import PptJob  # noqa: E402

logger = logging.getLogger(__name__)

_PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
_CHAT_EDIT_ERROR_ANSWER = "수정 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
_MAX_TEMPLATE_REFERENCE_BYTES = 8 * 1024 * 1024
_MAX_TEMPLATE_REFERENCE_PIXELS = 20_000_000


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _chat_edit_error_result(chat_result: dict | None) -> dict:
    cr = dict(chat_result or {})
    cr.update(status="error", answer=_CHAT_EDIT_ERROR_ANSWER, intent="chat")
    return cr


def _hex_color(rgb: tuple[int, int, int]) -> str:
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"


def _summarize_svg_reference(data: bytes, filename: str, index: int) -> str | None:
    import re

    try:
        text = data[:200_000].decode("utf-8", errors="ignore")
    except Exception:
        return None
    size_match = re.search(
        r"<svg[^>]*(?:width=['\"]?([0-9.]+)[a-z%]*['\"]?)?"
        r"[^>]*(?:height=['\"]?([0-9.]+)[a-z%]*['\"]?)?",
        text,
        flags=re.IGNORECASE,
    )
    colors = []
    for color in re.findall(r"#[0-9A-Fa-f]{3}(?:[0-9A-Fa-f]{3})?\b", text):
        normalized = color.upper()
        if normalized not in colors:
            colors.append(normalized)
        if len(colors) >= 6:
            break
    size = ""
    if size_match:
        width, height = size_match.group(1), size_match.group(2)
        if width and height:
            size = f", {width}x{height}"
    palette = ", ".join(colors) if colors else "색상 추출 불가"
    return f"- 예시 {index}({filename or 'SVG'}): SVG{size}, 주요 색상 {palette}."


def _summarize_raster_reference(data: bytes, filename: str, index: int) -> str | None:
    try:
        from PIL import Image, ImageStat

        with Image.open(io.BytesIO(data)) as im:
            if im.width * im.height > _MAX_TEMPLATE_REFERENCE_PIXELS:
                return None
            width, height = im.width, im.height
            image = im.convert("RGB")
            thumb = image.copy()
            thumb.thumbnail((96, 96))
            paletted = thumb.convert("P", palette=Image.ADAPTIVE, colors=6)
            palette = paletted.getpalette() or []
            raw_colors = paletted.getcolors(thumb.width * thumb.height) or []
            total = sum(count for count, _idx in raw_colors) or 1
            colors: list[str] = []
            for count, color_index in sorted(raw_colors, reverse=True)[:5]:
                offset = int(color_index) * 3
                rgb = tuple(palette[offset : offset + 3])
                if len(rgb) != 3:
                    continue
                colors.append(
                    f"{_hex_color((rgb[0], rgb[1], rgb[2]))} {round(count / total * 100)}%"
                )
            stat = ImageStat.Stat(thumb)
            brightness = sum(stat.mean) / 3
            mood = (
                "밝은 배경"
                if brightness >= 190
                else "중간 톤"
                if brightness >= 95
                else "어두운 배경"
            )
            aspect = "가로형" if width >= height else "세로형"
            return (
                f"- 예시 {index}({filename or '이미지'}): {width}x{height} {aspect}, "
                f"{mood}, 주요 색상 {', '.join(colors) or '추출 불가'}."
            )
    except Exception:
        return None


def _summarize_template_reference_image(data: bytes, ref: dict, index: int) -> str | None:
    filename = str(ref.get("filename") or "").strip()
    content_type = str(ref.get("content_type") or "").lower()
    if len(data) > _MAX_TEMPLATE_REFERENCE_BYTES:
        return None
    if "svg" in content_type or filename.lower().endswith(".svg"):
        return _summarize_svg_reference(data, filename, index)
    if content_type and not content_type.startswith("image/"):
        return None
    return _summarize_raster_reference(data, filename, index)


def _template_reference_block(job: PptJob, params: dict) -> str:
    refs = params.get("template_preview_images")
    if not isinstance(refs, list):
        return ""
    lines: list[str] = []
    for ref in refs[:4]:
        if not isinstance(ref, dict):
            continue
        storage_key = str(ref.get("storage_key") or "")
        if not storage_key:
            continue
        data = ppt_service.fetch_object_bytes(storage_key)
        if not data:
            continue
        summary = _summarize_template_reference_image(data, ref, len(lines) + 1)
        if summary:
            lines.append(summary)
    if not lines:
        return ""
    return (
        "[템플릿 미리보기 참고]\n"
        "아래 내용은 관리자가 등록한 이 템플릿 예시 이미지를 서버 내부에서 분석한 요약입니다. "
        "색감, 여백, 밀도, 강조 방식은 참고하되 입력 자료에 없는 사실이나 수치는 만들지 마세요.\n"
        + "\n".join(lines)
    )


# ============================================================
# LLM
# ============================================================
def _call_freeform_llm(
    session,
    job: PptJob,
    messages,
    *,
    temperature=0.6,
    max_tokens=None,
    json_mode: bool = True,
    presence_penalty: float = 1.5,
    workload_id: str = "ppt_generate",
) -> str:
    """Run PPT free-form generation through the shared local LLM contract."""

    extra_body: dict[str, object] = {
        "top_p": 0.8,
        "presence_penalty": presence_penalty,
    }
    if json_mode:
        extra_body["response_format"] = {"type": "json_object"}
    return _call_llm(
        session,
        job,
        messages,
        temperature=temperature,
        max_tokens=max_tokens,
        extra_body=extra_body,
        workload_id=workload_id,
    )


@dataclass(frozen=True)
class _JobResearchRef:
    """병렬 검색 스레드로 넘길 PptJob 스칼라 스냅샷.

    커밋된 PptJob 을 ThreadPoolExecutor 스레드에서 직접 참조하면, 세션 커밋 시
    expire_on_commit=True(기본값)로 만료된 속성을 여러 스레드가 공유 Session 에서
    동시에 lazy load 하게 된다. SQLAlchemy Session/Connection 은 thread-safe 하지
    않아 'concurrent operations' 오류나 상태 오염이 날 수 있다. 그래서 검색 경로가
    읽는 스칼라(아래 4개)만 메인 스레드에서 미리 스냅샷해 넘긴다.
    """

    id: str
    workspace_id: str
    user_id: str | None
    family: str

    @classmethod
    def of(cls, job: PptJob) -> _JobResearchRef:
        # 메인 스레드에서 호출 — 만료된 속성이면 여기서 한 번만(순차) lazy load 된다.
        return cls(
            id=job.id,
            workspace_id=job.workspace_id,
            user_id=job.user_id,
            family=job.family,
        )


def _ppt_external_capability_request(
    *,
    job: PptJob | _JobResearchRef | None,
    source: str,
    task_kind: str,
    capability: str,
    input_text: str,
    provider: str = "anthropic",
    model: str | None = None,
    metadata: dict[str, object] | None = None,
) -> AiExternalCapabilityRequest:
    return AiExternalCapabilityRequest(
        source=source,
        workspace_id=job.workspace_id if job is not None else "unknown",
        actor_user_id=job.user_id if job is not None else None,
        principal_kind="user" if job is not None else "system",
        principal_id=job.user_id if job is not None else None,
        task_kind=task_kind,
        capability=capability,
        provider=provider,
        input_texts=[input_text],
        entity_id=job.id if job is not None else None,
        metadata={
            "job_id": job.id if job is not None else None,
            "family": job.family if job is not None else None,
            "model": model,
            **(metadata or {}),
        },
    )


def _call_claude_design(
    session,
    system: str,
    user: str,
    *,
    max_tokens=64000,
    effort: str = "xhigh",
    thinking: bool = True,
    job: PptJob | None = None,
) -> str:
    """등록된 PPT 설계 워크로드를 관리자 선택 경로·모델로 호출한다."""

    del thinking
    result = execute_llm(
        PPT_DESIGN_WORKLOAD_ID,
        LlmWorkloadContext(
            source="worker.ppt_generator.design",
            workspace_id=job.workspace_id if job is not None else "unknown",
            actor_user_id=job.user_id if job is not None else None,
            principal_kind="user" if job is not None else "system",
            principal_id=job.user_id if job is not None else None,
            app_id="ppt-assistant",
        ),
        session,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
        reasoning_effort=effort,
        stream_reasoning=False,
        audit_entity_id=job.id if job is not None else None,
    )
    return result.completion.text.strip()


def _extract_html(raw: str) -> str:
    """Claude 응답에서 완전한 HTML 문서만 추출(코드블록/잡담 제거)."""
    import re

    text = (raw or "").strip()
    fence = re.search(r"```(?:html)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    m = re.search(r"<!DOCTYPE html.*?</html>", text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(0)
    m2 = re.search(r"<html.*?</html>", text, re.DOTALL | re.IGNORECASE)
    return m2.group(0) if m2 else text


def _strip_data_uris(html: str) -> tuple[str, list[str]]:
    """base64 data URI(주로 로고)를 placeholder 로 치환 — LLM 편집 시 입출력 토큰을
    줄이고 base64 가 깨지는 것을 막는다. (치환된 HTML, 원본 URI 목록) 반환."""
    import re

    uris: list[str] = []

    def _repl(m):
        uris.append(m.group(0))
        return f"__DATAURI_{len(uris) - 1}__"

    stripped = re.sub(r"data:image/[^\"')\s]+", _repl, html)
    return stripped, uris


def _restore_data_uris(html: str, uris: list[str]) -> str:
    for i, u in enumerate(uris):
        html = html.replace(f"__DATAURI_{i}__", u)
    return html


class _PptResearchAuthGate:
    """Allow one credential probe, then stop this job's research calls after a 401."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._state = "unknown"

    def acquire(self) -> bool:
        with self._condition:
            while self._state == "probing":
                self._condition.wait()
            if self._state == "open":
                return False
            if self._state == "unknown":
                self._state = "probing"
            return True

    def record_success(self) -> None:
        with self._condition:
            if self._state == "probing":
                self._state = "ready"
            self._condition.notify_all()

    def record_non_auth_failure(self) -> None:
        # Transient/provider failures must not disable independent optional searches.
        self.record_success()

    def record_auth_failure(self) -> None:
        with self._condition:
            self._state = "open"
            self._condition.notify_all()


def _claude_research_after_auth_gate(
    topic: str,
    *,
    extra_context: str = "",
    job: PptJob | _JobResearchRef | None = None,
    auth_gate: _PptResearchAuthGate | None = None,
) -> tuple[str, list[dict]]:
    """외부 Anthropic 웹 검색으로 공개 웹 최신 정보를 검색·종합한다.

    **외부 Claude 로 나가는 데이터 = 주제 + 비기밀 검색 힌트(extra_context)뿐**
    — 첨부 파일·본문·기타 참고사항은 절대 안 감. extra_context 는 라우터가 좌측
    비기밀 입력(용도/대상·발표 대상·참고 URL)만 모아 만든 텍스트다.
    모델은 호출부가 아니라 등록 워크로드의 관리자 설정에서 결정한다.
    실패하면 (빈 문자열, [])를 반환해 생성이 계속되게 한다(검색은 보조 수단).

    반환: (종합 텍스트, 출처 리스트[{"url","title"}]). 출처는 web_search 결과·인용에서 수집.
    """
    topic = (topic or "").strip()
    extra_context = (extra_context or "").strip()
    if not topic:
        return "", []

    research_input = f"주제: {topic}\n" + (f"{extra_context}\n" if extra_context else "")
    try:
        with _db_session_scope() as route_db:
            route = resolve_llm_workload_route(PPT_RESEARCH_WORKLOAD_ID, route_db)
    except Exception as exc:  # noqa: BLE001 - research is optional
        if auth_gate is not None:
            auth_gate.record_non_auth_failure()
        logger.warning("PPT research route resolution failed: %s", exc)
        return "", []

    base = route.endpoint_url.rstrip("/")
    key = route.api_key.get_secret_value() if route.api_key is not None else ""
    model = route.model_key
    if not base or not key:
        if auth_gate is not None:
            auth_gate.record_auth_failure()
        logger.warning("PPT external research provider is not configured")
        return "", []
    try:
        with _db_session_scope() as security_db:
            gateway_execution = begin_external_capability(
                _ppt_external_capability_request(
                    job=job,
                    source="worker.ppt_generator.research",
                    task_kind="ppt_research",
                    capability="ppt_web_search",
                    input_text=research_input,
                    model=model,
                    metadata={"max_uses": 5},
                ),
                db=security_db,
            )
    except AiExternalCapabilityPolicyViolation as exc:
        if auth_gate is not None:
            auth_gate.record_non_auth_failure()
        logger.warning("Claude research blocked by gateway policy: %s", exc.reason_code)
        return "", []
    except Exception as exc:  # noqa: BLE001 - research is optional
        if auth_gate is not None:
            auth_gate.record_non_auth_failure()
        logger.warning("PPT research gateway initialization failed: %s", exc)
        return "", []
    try:
        provider_research_input = gateway_execution.sanitized_text(
            fallback=research_input
        ).strip()
    except Exception as exc:  # noqa: BLE001 - research is optional
        if auth_gate is not None:
            auth_gate.record_non_auth_failure()
        logger.warning("PPT research gateway sanitization failed: %s", exc)
        return "", []
    try:
        result = run_anthropic_web_research(
            base_url=base,
            api_key=key,
            model=model,
            research_input=provider_research_input,
            max_tokens=route.max_output_tokens,
            max_uses=5,
        )
    except AnthropicWebResearchAuthenticationError as exc:
        if auth_gate is not None:
            auth_gate.record_auth_failure()
        gateway_execution.record_error(exc)
        logger.warning("Claude research 인증 실패(이 작업의 후속 외부 검색 중단)")
        return "", []
    except Exception as e:  # noqa: BLE001 — 검색 실패는 무시하고 생성 계속
        gateway_execution.record_error(e)
        if auth_gate is not None:
            auth_gate.record_non_auth_failure()
        logger.warning("Claude research 실패(무시): %s", e)
        return "", []
    gateway_execution.record_success(
        metadata={"model": model, "sdk": "raw-http", "sources": len(result.sources)}
    )
    if auth_gate is not None:
        auth_gate.record_success()
    return result.text, result.sources


def _claude_research(
    topic: str,
    *,
    extra_context: str = "",
    job: PptJob | _JobResearchRef | None = None,
    auth_gate: _PptResearchAuthGate | None = None,
) -> tuple[str, list[dict]]:
    """Run optional research while guaranteeing that credential-probe waiters are released."""

    topic = (topic or "").strip()
    if not topic:
        return "", []
    if auth_gate is not None and not auth_gate.acquire():
        return "", []
    try:
        return _claude_research_after_auth_gate(
            topic,
            extra_context=extra_context,
            job=job,
            auth_gate=auth_gate,
        )
    finally:
        # Covers property access, secret unwrap, audit recording, and any future exception path.
        # record_non_auth_failure does not reopen an auth-failed (open) gate.
        if auth_gate is not None:
            auth_gate.record_non_auth_failure()


def _research_block(
    session,
    job: PptJob,
    *,
    auth_gate: _PptResearchAuthGate | None = None,
) -> str:
    """params['topic'](≤100자)로 외부 최신정보 검색 → 내부 LLM 참고 블록 문자열."""
    topic = ((job.params or {}).get("topic") or "").strip()
    if not topic:
        return ""
    # 좌측 비기밀 메타(용도/대상·발표 대상·참고 URL)만 외부 검색 힌트로 덧붙인다.
    # 기밀 첨부·기타 참고사항(job.content)은 절대 포함하지 않는다.
    ctx = (job.params or {}).get("external_context") or {}
    hint_parts: list[str] = []
    if ctx.get("purpose"):
        hint_parts.append(f"용도/대상: {ctx['purpose']}")
    if ctx.get("audience"):
        hint_parts.append(f"발표 대상: {ctx['audience']}")
    if ctx.get("reference_url"):
        hint_parts.append(f"참고 URL: {ctx['reference_url']}")
    extra_context = "\n".join(hint_parts)
    _set(session, job, message="최신 정보 검색 중...")
    research, sources = _claude_research(
        topic,
        extra_context=extra_context,
        job=job,
        auth_gate=auth_gate,
    )
    # 수집한 출처를 job.params 에 저장 → API 가 노출 → 미리보기 우측에 표시.
    if sources:
        try:
            params = dict(job.params or {})
            params["research_sources"] = sources[:20]
            job.params = params
            flag_modified(job, "params")
            session.commit()
        except Exception as e:  # noqa: BLE001 — 출처 저장 실패는 비치명적
            session.rollback()
            logger.info("ppt_generator %s 출처 저장 실패(무시): %s", job.id, e)
    if not research:
        return ""
    return f"[최신 참고 정보 — 외부 웹 검색 결과]\n{research}\n\n"


_MAX_SECTION_SEARCHES = 12  # 비용/지연 상한 — 초과 섹션은 검색 생략(로그 남김)


def _collect_house_sections(slides: list[dict]) -> list[str]:
    """house 슬라이드에서 보강 대상 섹션 제목을 위→아래 순서로 수집(중복 제거).

    슬라이드 제목(data.title) + 각 블록/row 자식의 section 을 모은다.
    """
    seen: set[str] = set()
    out: list[str] = []

    def _add(t: object) -> None:
        s = str(t or "").strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)

    for sl in slides:
        if not isinstance(sl, dict) or sl.get("layout") != "house-report":
            continue
        data = sl.get("data") if isinstance(sl.get("data"), dict) else {}
        _add(data.get("title"))
        for b in data.get("blocks") or []:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "row":
                for k in b.get("blocks") or []:
                    if isinstance(k, dict):
                        _add(k.get("section"))
            else:
                _add(b.get("section"))
    return out


def _house_section_queries(session, job: PptJob, sections: list[str]) -> list[tuple[str, str]]:
    """내부 LLM으로 섹션 제목 → 외부 일반화 검색어 매핑. (section, query) 리스트(빈 query 제외).

    섹션 제목엔 사내 모델명 등 기밀이 섞이므로, 내부 Qwen 이 **기밀 식별자를 제거한 일반 검색어**만
    만들고(=이 출력만 외부행), 빈 문자열로 표시된 사내 전용 섹션은 검색에서 제외한다.
    """
    if not sections:
        return []
    topic = ((job.params or {}).get("topic") or "").strip()
    try:
        raw = _call_llm(
            session,
            job,
            prompts.build_house_section_keywords_messages(sections, topic),
            temperature=0.2,
        )
        obj = parsing.parse_json_object(raw)
    except Exception as e:  # noqa: BLE001 — 키워드 생성 실패는 비치명적(보강 생략)
        logger.info("ppt_generator %s house 검색어 생성 실패(보강 생략): %s", job.id, e)
        return []
    pairs: list[tuple[str, str]] = []
    seen_q: set[str] = set()
    for item in obj.get("queries") or []:
        if not isinstance(item, dict):
            continue
        sec = str(item.get("section") or "").strip()
        q = str(item.get("query") or "").strip()
        if not sec or not q:
            continue
        key = q.lower()
        if key in seen_q:  # 동일 검색어 중복 제거(비용 절감)
            continue
        seen_q.add(key)
        pairs.append((sec, q))
    return pairs


def _enrich_house_with_research(
    session,
    job: PptJob,
    slides: list[dict],
    *,
    auth_gate: _PptResearchAuthGate | None = None,
) -> list[dict]:
    """house 슬라이드의 **전 섹션**을 외부 웹 검색 결과로 보강해 새 슬라이드를 반환.

    흐름: 섹션 수집 → (내부 Qwen) 기밀 제거 일반 검색어 → (외부 Claude) 섹션별 병렬 검색 →
    (내부 Qwen) 검색 자료로 전 섹션 보강. 외부로 나가는 건 **일반화 검색어뿐**(첨부/본문 X).
    어느 단계든 실패하거나 검색 결과가 없으면 원본 slides 를 그대로 반환한다(보강은 보조 수단).
    """
    sections = _collect_house_sections(slides)
    pairs = _house_section_queries(session, job, sections)
    if not pairs:
        return slides
    dropped = 0
    if len(pairs) > _MAX_SECTION_SEARCHES:
        dropped = len(pairs) - _MAX_SECTION_SEARCHES
        pairs = pairs[:_MAX_SECTION_SEARCHES]
        logger.info(
            "ppt_generator %s house 섹션 검색 상한(%d) 초과 → %d개 섹션 검색 생략",
            job.id,
            _MAX_SECTION_SEARCHES,
            dropped,
        )

    _set(
        session,
        job,
        message=f"섹션별 최신 정보 검색 중... ({len(pairs)}개 주제)",
    )

    # 외부 검색은 DB 세션을 건드리지 않으므로(_claude_research 는 게이트웨이 db=None) 병렬 호출 가능.
    # 단, 커밋된 job 을 스레드에서 직접 참조하면 만료 속성의 동시 lazy load 위험이 있어
    # (위 _set 가 커밋 → expire_on_commit=True) 스칼라 스냅샷만 메인 스레드에서 떠서 넘긴다.
    from concurrent.futures import ThreadPoolExecutor

    job_ref = _JobResearchRef.of(job)

    def _one(pair: tuple[str, str]) -> tuple[str, str, list[dict]]:
        sec, q = pair
        text, srcs = _claude_research(q, job=job_ref, auth_gate=auth_gate)
        return sec, text, srcs

    results: list[tuple[str, str, list[dict]]] = []
    try:
        with ThreadPoolExecutor(max_workers=min(5, len(pairs))) as ex:
            results = list(ex.map(_one, pairs))
    except Exception as e:  # noqa: BLE001 — 검색 실패는 비치명적
        logger.info("ppt_generator %s house 섹션 검색 실패(보강 생략): %s", job.id, e)
        return slides

    notes: list[str] = []
    all_sources: list[dict] = []
    for sec, text, srcs in results:
        if text:
            notes.append(f"■ {sec}\n{text}")
        all_sources.extend(srcs or [])
    if not notes:
        return slides

    # 수집한 출처를 기존 research_sources 뒤에 합쳐 저장(미리보기 우측 참고 출처에 노출).
    if all_sources:
        try:
            params = dict(job.params or {})
            prev = params.get("research_sources") or []
            by_url = {s.get("url"): s for s in prev if isinstance(s, dict) and s.get("url")}
            for s in all_sources:
                u = s.get("url") if isinstance(s, dict) else None
                if u and u not in by_url:
                    by_url[u] = s
            params["research_sources"] = list(by_url.values())[:40]
            job.params = params
            flag_modified(job, "params")
            session.commit()
        except Exception as e:  # noqa: BLE001 — 출처 저장 실패는 비치명적
            session.rollback()
            logger.info("ppt_generator %s 섹션 출처 저장 실패(무시): %s", job.id, e)

    _set(session, job, message="검색 자료로 내용 보강 중... (내부 LLM)")
    language = (job.params or {}).get("language") or "Korean"
    schema = prompts._FAMILY_SCHEMAS.get(job.family) or prompts._HOUSE_SCHEMA
    try:
        raw = _call_llm(
            session,
            job,
            prompts.build_house_enrich_messages(slides, "\n\n".join(notes), language, schema),
        )
        enriched = parsing.parse_slides_json(raw, job.family)
        if enriched:
            logger.info(
                "ppt_generator %s house 섹션 보강 완료(검색 %d개, 출처 %d개)",
                job.id,
                len(notes),
                len(all_sources),
            )
            return enriched
    except Exception as e:  # noqa: BLE001 — 보강 파싱 실패 시 원본 유지
        logger.info("ppt_generator %s house 섹션 보강 실패(원본 유지): %s", job.id, e)
    return slides


def _generate_brandlogy_spec(
    session, job: PptJob, family_key: str, params: dict
) -> tuple[dict, int]:
    """자유 양식(Brandlogy) 생성 — Claude 단독으로 슬라이드 덱을 HTML 문서로 직접 출력.

    반환: (slides_spec, n_slides). Claude 키가 없으면 기존 Qwen 요소 JSON 경로로 폴백.
    """
    language = params.get("language") or "Korean"
    tone = params.get("tone") or "default"
    instructions = params.get("instructions")
    content = job.content or ""
    n_slides = max(1, min(12, job.n_slides or 6))

    use_external_design = (
        resolve_llm_workload_route(PPT_DESIGN_WORKLOAD_ID, session).route == "external"
    )

    if not use_external_design:
        logger.info("ppt_generator %s: 등록된 로컬 PPT 설계 경로 사용", job.id)
        messages = prompts.build_messages(
            content,
            n_slides,
            language,
            tone,
            instructions,
            bool(params.get("include_title_slide", True)),
            bool(params.get("include_toc", False)),
            family_key,
        )
        raw = _call_freeform_llm(
            session,
            job,
            messages,
            workload_id=PPT_DESIGN_WORKLOAD_ID,
        )
        try:
            slides = parsing.parse_slides_json(raw, family_key)
        except Exception as e:  # noqa: BLE001
            retry = prompts.build_retry_messages(messages, raw, str(e))
            slides = parsing.parse_slides_json(
                _call_freeform_llm(
                    session,
                    job,
                    retry,
                    workload_id=PPT_DESIGN_WORKLOAD_ID,
                ),
                family_key,
            )
        return {"family": family_key, "slides": slides}, len(slides)

    # Claude 단독 — 슬라이드 덱을 HTML 문서로 직접 생성
    _set(session, job, message="Claude가 슬라이드 디자인·작성 중...")
    sys_p, user_p = prompts.build_brandlogy_html_prompt(
        content, n_slides, language, tone, instructions
    )
    html = _extract_html(_call_claude_design(session, sys_p, user_p, max_tokens=64000, job=job))
    if "<section" not in html and "slide" not in html:
        # 형식이 깨졌으면 1회 재시도
        _set(session, job, message="재시도 중...")
        html = _extract_html(
            _call_claude_design(
                session,
                sys_p,
                user_p + "\n\n반드시 <!DOCTYPE html> 로 시작하는 완전한 HTML 문서만 출력하세요.",
                max_tokens=64000,
                job=job,
            )
        )
    spec = {
        "family": family_key,
        "format": "html",
        "html": html,
        "slide_w": prompts.BRANDLOGY_HTML_SLIDE_W,
        "slide_h": prompts.BRANDLOGY_HTML_SLIDE_H,
    }
    return spec, n_slides


# "명칭: 설명" 형태의 항목 불릿을 표로 바꿀 때 라벨/설명 분리.
# 라벨은 짧아야 한다(문장 안에 우연히 든 콜론은 변환 대상에서 제외).
_LABEL_DESC_RE = re.compile(
    r"^\s*(?:[-•▪◦·*∎]\s*|\d+[.)]\s*)?(?P<label>[^:：]{1,24}?)\s*[:：]\s*(?P<desc>.+\S)\s*$"
)


def _bullets_to_table_block(block: dict) -> dict | None:
    """text 블록의 bullets(2개 이상)를 표 블록으로 변환.

    - 모두 '명칭: 설명' → 2열 표(구분|내용).
    - 그 외 일반 서술 불릿 → **섹션이 있을 때만** 헤더 없는 단일 열 표(■ 섹션 줄은 유지).
      섹션 없는 떠다니는 불릿은 변환하지 않는다(불릿 유지).
    """
    bullets = block.get("bullets")
    if not isinstance(bullets, list) or len(bullets) < 2:
        return None
    if not all(isinstance(b, str) and b.strip() for b in bullets):
        return None

    # 1) 전부 '명칭: 설명' → 2열 표
    ld_rows: list[list[str]] = []
    all_label_desc = True
    for b in bullets:
        m = _LABEL_DESC_RE.match(b)
        if not m:
            all_label_desc = False
            break
        ld_rows.append([m.group("label").strip(), m.group("desc").strip()])
    if all_label_desc:
        tbl: dict = {
            "type": "table",
            "header": ["구분", "내용"],
            "colW": [6.5, 19.4],  # 합 25.9
            "align": ["l", "l"],
            "rows": ld_rows,
        }
        if block.get("section"):
            tbl["section"] = block["section"]
        return tbl

    # 2) 일반 서술 불릿 → 섹션이 있으면 헤더 없는 **1행1열 큰 표** 하나에 담고,
    #    그 셀 안에서 항목을 '- ' 로 구분한다(따로 행으로 쪼개지 않음 — 사내 요청).
    if not block.get("section"):
        return None
    dashed = [f"- {b.strip()}" for b in bullets]
    tbl = {
        "type": "table",
        "colW": [25.9],
        "align": ["l"],
        "rows": [[{"lines": dashed, "al": "l"}]],
        "section": block["section"],
    }
    return tbl


def _house_textlists_to_tables(slides: list[dict]) -> None:
    """house 본문에서 '명칭: 설명' 나열형 text 블록을 표로 바꾼다(in-place, row 자식 포함).

    사내 요청: 하나의 주제 아래 '명칭: 설명' 항목이 여러 개면 불릿 대신 표(구분|내용)로 정리.
    """

    def _conv(blocks: list) -> None:
        for i, b in enumerate(blocks):
            if not isinstance(b, dict):
                continue
            if str(b.get("type")) == "row":
                kids = b.get("blocks")
                if isinstance(kids, list):
                    _conv(kids)
                continue
            if str(b.get("type")) == "text":
                t = _bullets_to_table_block(b)
                if t is not None:
                    blocks[i] = t

    for sl in slides:
        if isinstance(sl, dict) and sl.get("layout") == "house-report":
            data = sl.get("data")
            if isinstance(data, dict) and isinstance(data.get("blocks"), list):
                _conv(data["blocks"])


def _timeline_has_dates(block: dict) -> bool:
    """타임라인 노드에 **실제 날짜**가 2개 이상 있으면 진짜 일정/진행 타임라인으로 본다."""
    nodes = block.get("nodes")
    if not isinstance(nodes, list):
        return False
    dated = sum(1 for nd in nodes if isinstance(nd, dict) and str(nd.get("date") or "").strip())
    return dated >= 2


def _prune_dateless_timelines(slides: list[dict]) -> None:
    """날짜 없는 timeline 블록을 제거한다(in-place, row 자식 포함). 사내 요청: 화살표 진행도는

    날짜별 진행상황·계획이 있을 때만 — 단순 단계 나열을 타임라인으로 남발하지 않는다. compare 그리드
    안의 일정 셀(타임라인)은 의도된 것이므로 건드리지 않는다(top-level/row 의 독립 timeline 만).
    """

    def _prune(blocks: list) -> None:
        kept = []
        for b in blocks:
            if (
                isinstance(b, dict)
                and str(b.get("type")) == "timeline"
                and not _timeline_has_dates(b)
            ):
                continue  # 날짜 없는 타임라인 → 제거
            if isinstance(b, dict) and str(b.get("type")) == "row":
                kids = b.get("blocks")
                if isinstance(kids, list):
                    _prune(kids)
                    # row 자식이 1개만 남으면 row 껍데기를 벗겨 그 블록을 직접 둔다.
                    if len(kids) == 1:
                        kept.append(kids[0])
                        continue
                    if not kids:
                        continue
            kept.append(b)
        blocks[:] = kept

    for sl in slides:
        if isinstance(sl, dict) and sl.get("layout") == "house-report":
            data = sl.get("data")
            if isinstance(data, dict) and isinstance(data.get("blocks"), list):
                _prune(data["blocks"])


def _compare_to_table_if_no_timeline(slides: list[dict]) -> None:
    """타임라인 셀이 없는 compare 블록을 **일반 다열 table** 로 바꾼다(in-place, row 자식 포함).

    사내 요청: compare(커스텀 격자)는 '구분 열'이 별도 표처럼 어긋나 보인다. 셀에 타임라인(일정)이
    하나도 없는 단순 열 비교는 한 표에 여러 열로 합쳐야 한다 → header=compare.headers,
    각 row=[label, *cells]. 타임라인 셀이 하나라도 있으면 compare 그대로 둔다(격자가 필요).
    """

    def _has_timeline(rows: list) -> bool:
        for r in rows:
            for cell in (r.get("cells") or []) if isinstance(r, dict) else []:
                if isinstance(cell, dict) and str(cell.get("type")) == "timeline":
                    return True
        return False

    def _cell_to_value(cell: object) -> object:
        # 표 셀이 그대로 받는 형태(문자열 / {lines} / {t})만 통과, 그 외는 문자열화.
        if isinstance(cell, (str, int, float)):
            return cell
        if isinstance(cell, dict) and ("lines" in cell or "t" in cell or "runs" in cell):
            return cell
        return str(cell) if cell is not None else ""

    def _conv(blocks: list) -> None:
        for i, b in enumerate(blocks):
            if not isinstance(b, dict):
                continue
            if str(b.get("type")) == "row":
                kids = b.get("blocks")
                if isinstance(kids, list):
                    _conv(kids)
                continue
            if str(b.get("type")) != "compare":
                continue
            rows = b.get("rows") or []
            headers = b.get("headers") or []
            if _has_timeline(rows) or not headers:
                continue  # 일정 격자가 필요한 compare 는 유지
            new_rows = []
            for r in rows:
                if not isinstance(r, dict):
                    continue
                cells = [_cell_to_value(c) for c in (r.get("cells") or [])]
                new_rows.append([str(r.get("label") or ""), *cells])
            blocks[i] = {
                "type": "table",
                "section": b.get("section"),
                "header": list(headers),
                "rows": new_rows,
            }

    for sl in slides:
        if isinstance(sl, dict) and sl.get("layout") == "house-report":
            data = sl.get("data")
            if isinstance(data, dict) and isinstance(data.get("blocks"), list):
                _conv(data["blocks"])


_BULLET_PREFIX_RE = re.compile(r"^\s*(?:[-•▪*·]|\d+[.)]|[①-⑳])\s+")


def _house_singlecol_to_outline(slides: list[dict]) -> None:
    """**1열짜리 표**(글만 나열돼 테두리 박스로 둘러싸인 것)를 outline 블록으로 바꾼다(in-place, row 자식 포함).

    사내 요청: '글만 있는' 나열은 테두리 박스(1열 표) 말고 outline(■→1)→…)으로. 셀 줄들을 모아
    앞 글머리(- • 숫자 등)를 떼고 level 1 항목으로 만든다. 2열 이상 표(진짜 비교표)는 건드리지 않는다.
    """
    # 박스 글머리(■□▣ 등)는 렌더 단계(builders_house)와 동일 기준으로 제거해, 아웃라인 항목에
    # '■'가 남아 '1) ■ …' 처럼 이중 글머리가 되는 divergence 를 막는다.
    from ai_do_api.domains.ppt_generator.design.builders_house import (
        _strip_bullet as _strip_box_bullet,
    )

    def _ncols(b: dict) -> int:
        header = b.get("header") or []
        if header:
            return len(header)
        rows = b.get("rows") or []
        n = 1
        for r in rows:
            if isinstance(r, list):
                n = max(n, len(r))
            elif isinstance(r, dict) and isinstance(r.get("cells"), list):
                n = max(n, len(r["cells"]))
        return n

    def _cell_lines(cell: object) -> list[str]:
        if isinstance(cell, str):
            return re.split(r"<br\s*/?>|\n", cell)
        if isinstance(cell, dict):
            if isinstance(cell.get("lines"), list):
                return [str(x) for x in cell["lines"]]
            for k in ("t", "text"):
                if cell.get(k) is not None:
                    return re.split(r"<br\s*/?>|\n", str(cell[k]))
            if isinstance(cell.get("runs"), list):
                return [str(r.get("t", "") if isinstance(r, dict) else r) for r in cell["runs"]]
        return [str(cell)] if cell is not None else []

    def _conv(blocks: list) -> None:
        for i, b in enumerate(blocks):
            if not isinstance(b, dict):
                continue
            if str(b.get("type")) == "row":
                kids = b.get("blocks")
                if isinstance(kids, list):
                    _conv(kids)
                continue
            if str(b.get("type")) != "table" or _ncols(b) != 1:
                continue
            # 1열 표 → 모든 셀 줄을 모아 항목화.
            lines: list[str] = []
            for r in b.get("rows") or []:
                cell = r[0] if isinstance(r, list) and r else (r if not isinstance(r, list) else "")
                for ln in _cell_lines(cell):
                    s = _BULLET_PREFIX_RE.sub("", _strip_box_bullet(str(ln))).strip()
                    if s:
                        lines.append(s)
            if len(lines) < 2:
                continue  # 단일 값 표는 그대로 둔다
            blocks[i] = {
                "type": "outline",
                "section": b.get("section"),
                "items": [{"text": s, "level": 1} for s in lines],
            }

    for sl in slides:
        if isinstance(sl, dict) and sl.get("layout") == "house-report":
            data = sl.get("data")
            if isinstance(data, dict) and isinstance(data.get("blocks"), list):
                _conv(data["blocks"])


# LLM 이 자발적으로 붙이는 'AI/보안 유의사항' 메타 코멘트 식별 — 보고서 본문이 아니므로 제거.
_ADVISORY_RE = re.compile(
    r"영업비밀\s*유출|온프레미스|데이터\s*마스킹|외부\s*생성형\s*AI|생성형\s*AI[^\n]{0,20}(입력|유출)|보안\s*유의"
)


def _block_text_blob(b: object) -> str:
    parts: list[str] = []

    def grab(v: object) -> None:
        if isinstance(v, str):
            parts.append(v)
        elif isinstance(v, list):
            for x in v:
                grab(x)
        elif isinstance(v, dict):
            for x in v.values():
                grab(x)

    grab(b)
    return " ".join(parts)


def _is_advisory_block(b: object) -> bool:
    """'보안·AI 활용 유의사항' 류 메타 코멘트 블록인가(text/결론/소제목, 또는 작은 박스 표)."""
    if not isinstance(b, dict):
        return False
    btype = b.get("type")
    if btype in ("text", "conclusion", "heading", "lead"):
        return bool(_ADVISORY_RE.search(_block_text_blob(b)))
    if btype == "table" and len(b.get("rows") or []) <= 2:
        return bool(_ADVISORY_RE.search(_block_text_blob(b)))
    return False


def _strip_house_advisory_blocks(slides: list[dict]) -> None:
    """house 슬라이드에서 'AI/보안 유의사항' 메타 코멘트 블록을 제거(in-place, row 자식 포함).

    사내 요청: 모델이 종종 "외부 생성형 AI 에 기밀 입력 시 유출 위험" 같은 경고를 슬라이드에 넣는데,
    이는 보고서 주제 내용이 아니므로 빼낸다. 블록이 모두 빠져 빈 슬라이드가 되면 그 슬라이드도 제거.
    """
    for sl in slides:
        if not isinstance(sl, dict) or sl.get("layout") != "house-report":
            continue
        data = sl.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("blocks"), list):
            continue
        new_blocks: list = []
        for b in data["blocks"]:
            if isinstance(b, dict) and b.get("type") == "row":
                kids = [k for k in (b.get("blocks") or []) if not _is_advisory_block(k)]
                if kids:
                    b["blocks"] = kids
                    new_blocks.append(b)
                continue
            if not _is_advisory_block(b):
                new_blocks.append(b)
        data["blocks"] = new_blocks
    # 본문 블록이 하나도 안 남은 house 슬라이드는 통째로 제거.
    slides[:] = [
        sl
        for sl in slides
        if not (
            isinstance(sl, dict)
            and sl.get("layout") == "house-report"
            and not (sl.get("data") or {}).get("blocks")
        )
    ]


def _prune_house_empty_sections(slides: list[dict]) -> None:
    """내용 없는 섹션 제목(장 표지)을 제거한다(in-place).

    사내 요청: LLM 이 "■ …분석 / ■ …제언" 같은 섹션 제목 + '목적:' 한 줄만 있고 정작 표·목록 등
    본문이 없는 '장 표지' 블록을 만들 때가 있다(리패킹이 슬라이드 제목을 ■heading 으로 강등하면서
    노출). 그 섹션의 실제 내용은 보통 다른 슬라이드에 따로 있어, 이 자리엔 의미 없는 제목만 덩그러니
    남는다. → **본문(표/목록/차트/타임라인/비교/텍스트)이 뒤따르지 않는 heading 과 그 목적(lead)을
    제거**한다. 헤딩이 실제 본문을 이끌면(예: heading→lead→table) 남긴다. 블록이 모두 빠진
    house 슬라이드는 통째로 제거.
    """
    _SUBST = {"table", "outline", "chart", "timeline", "compare", "row", "text"}
    for sl in slides:
        if not isinstance(sl, dict) or sl.get("layout") != "house-report":
            continue
        data = sl.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("blocks"), list):
            continue
        blocks = data["blocks"]
        keep = [True] * len(blocks)
        i = 0
        while i < len(blocks):
            b = blocks[i]
            if isinstance(b, dict) and b.get("type") == "heading":
                # 이 heading 이 이끄는 구간: 다음 섹션 경계(다른 heading 또는 section 필드 보유 블록)까지.
                j = i + 1
                run: list[int] = []
                has_subst = False
                while j < len(blocks):
                    nb = blocks[j]
                    if isinstance(nb, dict) and (nb.get("type") == "heading" or nb.get("section")):
                        break
                    if isinstance(nb, dict):
                        run.append(j)
                        if nb.get("type") in _SUBST:
                            has_subst = True
                    j += 1
                if not has_subst:
                    keep[i] = False
                    for k in run:
                        keep[k] = False
                i = j
            else:
                i += 1
        data["blocks"] = [b for k, b in zip(keep, blocks) if k]
    # 본문 블록이 하나도 안 남은 house 슬라이드는 통째로 제거.
    slides[:] = [
        sl
        for sl in slides
        if not (
            isinstance(sl, dict)
            and sl.get("layout") == "house-report"
            and not (sl.get("data") or {}).get("blocks")
        )
    ]


_FILL_RATIO_TARGET = 0.90  # 이 비율 미만으로 차는 house 슬라이드는 자료 기반 내용으로 보강
# 사내 요청(2026-07-01, 최종): 하단 공백은 '내용 추가(보강)'가 아니라 '페이지 축소(접기)'로 없앤다.
# 80% 미만 페이지는 _compact_house_overflow 가 똑딱이로 접어 페이지를 줄인다(_HOUSE_MIN_LAST_FILL).
# 따라서 보강은 끈다 — 켜면 접기와 반대로 내용을 부풀려 사용자가 싫어한 '억지 충원'이 된다.
_HOUSE_FILL_AUGMENT = False

_HOUSE_MAX_PAGES = 3  # 사내 요청: 1장 강제 X — 공백 없이 조밀하게 최대 3장까지, 넘치면 똑딱이로
# 사내 요청(2026-07-01): 본문 페이지 충원률 목표 90%. 압축 흐름에 backfill(뒤 블록 끌어올려 빈틈
# 메움)을 넣어 앞 페이지를 조밀하게 채우고, 그래도 마지막 페이지가 이 목표 미만이면 그 내용을
# 똑딱이로 접어 페이지를 줄인다(본문 최소 1장 유지).
_HOUSE_MIN_LAST_FILL = 0.90
# 단, 이미 '꽉 찬' 페이지(이 값 이상)는 접지 않는다 — 원자 블록이라 90%를 딱 못 맞추는 게 정상인데,
# 그런 88/85% 페이지까지 접으면 멀쩡한 덱을 통째로 똑딱이에 쏟아붓는 과접기가 난다. 접기는
# '자명하게 빈' 꼬리(<이 값)에만 적용한다.
_HOUSE_KEEP_FILL = 0.75


def _compact_house_overflow(
    slides: list[dict], max_pages: int = _HOUSE_MAX_PAGES
) -> tuple[list[dict], list[tuple[dict, list[dict]]], list[dict]]:
    """house 본문을 **최대 max_pages 장**으로 압축하고, 넘치는 블록을 (제목, 블록) 리스트로 반환한다.

    사내 요청: 메인 덱은 가능한 한 1장으로 요약, 못 담은 상세는 '똑딱이'(OLE)로 뺀다. **섹션 단위로**
    묶어(제목+목적+본문 한 덩어리) 페이지에 채우므로, 본문 없는 섹션 도입부(■제목+목적만)가 메인에
    덩그러니 남지 않는다. 한 장에 안 들어가는 섹션은 통째로 넘침 → 상세본(똑딱이)으로.
    반환된 넘침 블록은 호출측이 상세본 덱으로 만든다. house 가 아닌 슬라이드는 그대로 둔다.
    """
    from ai_do_api.domains.ppt_generator.design.builders_house import (
        BODY_W_CM,
        _BLOCK_GAP,
        _estimate_block_height,
        _provides_section,
        house_body_height_cm,
    )

    bh = house_body_height_cm()
    if bh <= 0:
        return slides, [], []
    house_idx = [
        i for i, s in enumerate(slides) if isinstance(s, dict) and s.get("layout") == "house-report"
    ]
    if not house_idx:
        return slides, [], []

    # 본문 블록 스트림 [(원본제목, 블록)] 으로 펼친다.
    stream: list[tuple[str, dict]] = []
    for i in house_idx:
        data = slides[i].get("data") or {}
        title = str(data.get("title") or "")
        for b in data.get("blocks") or []:
            if isinstance(b, dict):
                stream.append((title, b))
    if not stream:
        return slides, [], []

    # 섹션 단위로 그룹화 — **자기 ■ 제목을 그리는 블록**(section 필드 보유 or type=heading)이
    # 새 섹션의 시작이다. LLM 은 별도 heading 블록 없이 표/텍스트 블록에 section 필드로 제목을
    # 달기 때문에, type=="heading" 만으로 나누면 전부 한 섹션으로 뭉쳐 앵커(제목 옆 똑딱이)가 안 된다.
    # 첫 그룹은 제목 없는 도입부(목적/lead)일 수 있다.
    sections: list[list[tuple[str, dict]]] = []
    cur_sec: list[tuple[str, dict]] = []
    for title, b in stream:
        if _provides_section(b) and cur_sec:
            sections.append(cur_sec)
            cur_sec = []
        cur_sec.append((title, b))
    if cur_sec:
        sections.append(cur_sec)

    def _blk_h(b: dict) -> float:
        return _estimate_block_height(b, BODY_W_CM)

    pages: list[dict] = []
    cur_blocks: list[dict] = []
    cur_title = ""
    cur_h = 0.0
    # 넘침(페이지 예산 초과분)을 섹션 제목 옆 '똑딱이'로 뺀다. 제목이 페이지에 있으면 그 옆(맥락형),
    # 아니면 우하단 catch-all 로. **오직 실제 넘침만** 똑딱이로 — 외로운 제목 스텁은 만들지 않는다.
    anchored: list[tuple[dict, list[dict]]] = []  # (페이지에 남은 heading 블록, 그 섹션 넘침 본문)
    catchall: list[dict] = []  # heading 을 페이지에 못 남긴 섹션의 넘침(우하단 똑딱이로 모음)

    def _flush() -> None:
        nonlocal cur_blocks, cur_title, cur_h
        if cur_blocks:
            pages.append(
                {"layout": "house-report", "data": {"title": cur_title, "blocks": cur_blocks}}
            )
        cur_blocks, cur_title, cur_h = [], "", 0.0

    def _add(title: str, b: dict) -> None:
        nonlocal cur_h, cur_title
        if cur_blocks:
            cur_h += _BLOCK_GAP
        else:
            cur_title = title
        cur_blocks.append(b)
        cur_h += _blk_h(b)

    def _fits(extra: float) -> bool:
        gap = _BLOCK_GAP if cur_blocks else 0.0
        return cur_h + gap + extra <= bh

    def _is_heading(b: dict) -> bool:
        return isinstance(b, dict) and b.get("type") == "heading"

    # 사용자 요청: 본문은 1장 강제가 아니라 **공백 없이 최대한 조밀하게** 여러 장(최대 max_pages)에
    # 흘려 담는다. 페이지 예산을 다 쓴 뒤의 꼬리 넘침만 '똑딱이'로 뺀다(똑딱이 남발 금지).
    # 블록 단위로 흘려 담되, 섹션 제목이 페이지 맨 아래 홀로 남지 않게(orphan) 가벼운 보호만 둔다.
    sec_heads: list[dict] = [sec[0][1] for sec in sections]
    sec_draws: list[bool] = [_provides_section(h) for h in sec_heads]
    annotated: list[tuple[str, dict, int]] = []
    for si, sec in enumerate(sections):
        for t, b in sec:
            annotated.append((t, b, si))

    placed_heads: set[int] = set()  # 헤딩 블록이 페이지에 놓인 섹션
    spill_by_sec: dict[int, list[dict]] = {}  # 섹션별 넘침 본문(페이지 예산 초과분)
    n = len(annotated)
    used = [False] * n
    _BACKFILL_WINDOW = 4  # 빈틈 메우러 뒤에서 끌어올릴 최대 거리(읽기순서 크게 안 흐트러지게 짧게)

    def _place_at(i: int) -> None:
        t, b, si = annotated[i]
        if b is sec_heads[si]:
            placed_heads.add(si)
        _add(t, b)
        used[i] = True

    idx = 0
    spilling = False
    while idx < n and not spilling:
        if used[idx]:
            idx += 1
            continue
        t, b, si = annotated[idx]
        bh_blk = _blk_h(b)
        is_head = (b is sec_heads[si]) and sec_draws[si]
        has_follower = idx + 1 < n and annotated[idx + 1][2] == si
        # orphan 방지: 제목이 페이지 맨 아래 홀로 남지 않게, 제목+다음 블록이 함께 못 들어가면
        # (페이지 예산이 남아 있을 때만) 새 페이지에서 시작한다.
        if is_head and has_follower and cur_blocks and len(pages) + 1 < max_pages:
            follow_h = _blk_h(annotated[idx + 1][1])
            if not (_fits(bh_blk) and cur_h + _BLOCK_GAP + bh_blk + _BLOCK_GAP + follow_h <= bh):
                _flush()
        if not cur_blocks or _fits(bh_blk):
            _place_at(idx)
            idx += 1
            continue
        # 현재 블록이 이 페이지에 안 들어감 → 하단 공백을 메우러 가까운 뒤쪽에서 들어가는 블록을
        # 끌어올린다(원자 블록, conclusion 은 끝에 와야 하므로 제외). 앞 페이지 충원률을 끌어올린다.
        filled = False
        for k in range(idx + 1, min(n, idx + 1 + _BACKFILL_WINDOW)):
            if used[k]:
                continue
            bk = annotated[k][1]
            if isinstance(bk, dict) and bk.get("type") == "conclusion":
                continue
            if _fits(_blk_h(bk)):
                _place_at(k)
                filled = True
                break
        if filled:
            continue  # 같은 idx 를 다시 시도(더 끌어올리거나 다음 iter 에서 페이지를 넘긴다).
        # 더 못 채움 → 예산 있으면 새 페이지, 없으면 여기서부터 넘침(읽기 순서 보존).
        if len(pages) + 1 < max_pages:
            _flush()
            continue
        spilling = True
    _flush()

    # 넘침: 아직 안 놓인 블록을 읽기 순서대로 섹션별로 모은다(backfill 로 생긴 구멍 포함).
    for j in range(n):
        if not used[j]:
            sj = annotated[j][2]
            spill_by_sec.setdefault(sj, []).append(annotated[j][1])
            used[j] = True

    # 사용자 규칙: '공백을 없애기 힘들 때 똑딱이로'. 마지막 페이지가 너무 비면(하단 공백 큼) 그 내용을
    # 똑딱이(catch-all)로 빼 공백을 없앤다. 단 본문은 최소 1페이지 남긴다. 앞 페이지에 같은 섹션
    # 제목이 남아 있으면 상세본이 그 섹션 제목 옆이 아니라 우하단 아이콘으로 모이되, section 필드를
    # 유지하므로 상세본 덱이 제목을 렌더한다(어느 섹션인지 보임).
    def _page_fill(p: dict) -> float:
        bs = (p.get("data") or {}).get("blocks") or []
        used = sum(_blk_h(b) for b in bs) + _BLOCK_GAP * max(0, len(bs) - 1)
        return used / bh if bh > 0 else 1.0

    # 앞 페이지들은 backfill 로 이미 조밀하다. 마지막 페이지가 목표(90%) 미만이면 그 내용을 똑딱이로
    # 접어 페이지를 줄인다 — 남는 페이지가 꽉 차도록. 단 '꽉 찬' 페이지(≥_HOUSE_KEEP_FILL)는 접지
    # 않는다(과접기 방지). 즉 자명하게 빈 꼬리(<75%)만 접는다(본문 최소 1장 유지).
    while len(pages) >= 2 and _page_fill(pages[-1]) < _HOUSE_MIN_LAST_FILL:
        if _page_fill(pages[-1]) >= _HOUSE_KEEP_FILL:
            break
        tail = pages.pop()
        for b in (tail.get("data") or {}).get("blocks") or []:
            if _is_heading(b):
                continue  # 상세본 repack 이 섹션 제목을 다시 부여.
            catchall.append(b)

    # 넘침 분류: 헤딩이 페이지에 있으면 그 제목 옆 '똑딱이'(맥락형), 아니면 우하단 catch-all.
    for si, blocks in spill_by_sec.items():
        if not blocks:
            continue
        if si in placed_heads:
            spilled: list[dict] = []
            for b in blocks:
                bb = dict(b)
                bb.pop("section", None)  # 제목은 이미 페이지에 있으니 상세본에서 중복 제거.
                spilled.append(bb)
            anchored.append((sec_heads[si], spilled))
        else:
            # 헤딩을 페이지에 못 남긴 섹션 → section 필드 유지(상세본 덱이 제목을 렌더).
            catchall.extend(blocks)

    # 안전망: 압축 결과에 house 본문이 하나도 없으면(예: 예외적 넘침 계산) 본문 유실을 막기 위해
    # 압축을 포기하고 원본 house 슬라이드를 그대로 둔다(똑딱이 없이라도 내용은 반드시 보존).
    if not any(isinstance(p, dict) and p.get("layout") == "house-report" for p in pages):
        return slides, [], []

    # 안전: max_pages 초과 시 초과분 catch-all.
    if len(pages) > max_pages:
        for p in pages[max_pages:]:
            catchall.extend(b for b in (p["data"].get("blocks") or []) if not _is_heading(b))
        pages = pages[:max_pages]

    # house 슬라이드 자리를 새 pages 로 교체(원래 위치 보존: 첫 house 인덱스에 끼워 넣음).
    first = house_idx[0]
    house_set = set(house_idx)
    rebuilt: list[dict] = []
    inserted = False
    for i, s in enumerate(slides):
        if i in house_set:
            if not inserted:
                rebuilt.extend(pages)
                inserted = True
            continue
        rebuilt.append(s)
    if not inserted:  # 안전망(이론상 도달 안 함)
        rebuilt[first:first] = pages
    return rebuilt, anchored, catchall


def _build_house_detail_slides(
    blocks: list[dict], section_title: str = "", max_pages: int = 12, deck_title: str = ""
) -> list[dict]:
    """넘침 본문 블록들을 '똑딱이' 상세본 house 덱(슬라이드 리스트)으로 묶는다.

    메인 덱과 같은 house-report 양식. section_title 이 주어지면 상세본 첫머리에 그 ■ 섹션 제목을
    달아 '어느 섹션의 상세인지' 보이게 한다. deck_title 이 주어지면 상세본 각 페이지 **상단 큰 제목**
    (메인 덱과 같은 문서 제목)을 강제로 채운다 — catch-all 처럼 여러 섹션이 섞여 상단 제목이 비는 걸
    막는다. _pack_house_run 으로 페이지를 채우고 과도하면 자른다.
    """
    from ai_do_api.domains.ppt_generator.design.builders_house import (
        _pack_house_run,
        house_body_height_cm,
    )

    items: list[tuple[str, dict]] = [(section_title, b) for b in blocks if isinstance(b, dict)]
    if not items:
        return []
    if section_title:
        items = [(section_title, {"type": "heading", "section": section_title}), *items]
    pages = _pack_house_run(items, house_body_height_cm())[:max_pages]
    if deck_title:
        # 상단 제목을 문서 제목으로 통일(메인 덱과 동일). 섹션 ■ 헤딩은 블록 단위로 그대로 유지.
        for p in pages:
            if isinstance(p, dict):
                p.setdefault("data", {})["title"] = deck_title
    return pages


def _trim_house_blocks_to_fit(blocks: list, target_cm: float) -> list:
    """채움 결과가 한 페이지를 넘치면 **통째로 버리지 말고** 끝에서부터 덜어내 페이지에 맞춘다.

    가장 행이 많은 표의 마지막 행부터 제거(구조·타임라인은 최대한 보존)하고, 표로 더 줄일 수 없으면
    마지막 블록을 통째로 제거한다. 오버슈트로 채움 전체가 폐기돼 슬라이드가 빈 채로 남는 걸 막는다.
    """
    from ai_do_api.domains.ppt_generator.design.builders_house import (
        BODY_W_CM,
        _BLOCK_GAP,
        _estimate_block_height,
    )

    out = [dict(b) if isinstance(b, dict) else b for b in blocks]
    # house_slide_used_cm 을 매 반복 호출하면 슬라이드 전체 블록을 재추정한다(행 하나만 뺐는데도).
    # 블록별 높이를 캐시하고 **변경된 블록만** 갱신해 반복당 O(1) 로 만든다(공식은 동일 → 결과 동일).
    heights = [_estimate_block_height(b, BODY_W_CM) if isinstance(b, dict) else 0.0 for b in out]
    used_sum = sum(heights)
    dict_count = sum(1 for b in out if isinstance(b, dict))

    def _used() -> float:
        # house_slide_used_cm 과 동일: dict 블록 높이 합 + 블록 간격*(dict 블록 수 - 1).
        return used_sum + _BLOCK_GAP * (dict_count - 1) if dict_count > 0 else 0.0

    guard = 0
    while out and _used() > target_cm and guard < 300:
        guard += 1
        # 행이 2개 초과인 표 중 가장 행 많은 것을 골라 마지막 행 1개 제거.
        cand = None
        cand_i = -1
        for i, b in enumerate(out):
            if (
                isinstance(b, dict)
                and b.get("type") == "table"
                and isinstance(b.get("rows"), list)
                and len(b["rows"]) > 2
            ):
                if cand is None or len(b["rows"]) > len(cand["rows"]):
                    cand = b
                    cand_i = i
        if cand is not None:
            cand["rows"] = cand["rows"][:-1]
            new_h = _estimate_block_height(cand, BODY_W_CM)  # 바뀐 표만 재추정
            used_sum += new_h - heights[cand_i]
            heights[cand_i] = new_h
            continue
        # 표로 더 못 줄이면 마지막 블록 제거
        b = out.pop()
        h = heights.pop()
        if isinstance(b, dict):
            used_sum -= h
            dict_count -= 1
    return out


def _fill_underfilled_house_slides(session, job: PptJob, slides: list[dict]) -> list[dict]:
    """채움률 < 90% 인 house 슬라이드를 **자료 기반 내용**으로 보강해 ~90% 까지 채운다(사내 요청).

    내부 Qwen 만 사용(첨부/본문은 외부로 안 나감). 한 페이지를 넘기지 않는 선에서 표 행·불릿·블록을
    더한다. 자료가 부족하면 90% 미만으로 남을 수 있다(창작 금지가 우선). 리패킹 뒤에 호출한다.
    """
    if not _HOUSE_FILL_AUGMENT:
        # 사내 요청: 충원률 채우려 내용을 덧붙이지 않는다(표/내용 자연 크기 유지).
        return slides

    from ai_do_api.domains.ppt_generator.design.builders_house import (
        house_body_height_cm,
        house_slide_used_cm,
    )

    body_h = house_body_height_cm()
    if body_h <= 0:
        return slides
    content = (job.content or "")[:6000]
    language = (job.params or {}).get("language") or "Korean"
    schema = prompts._FAMILY_SCHEMAS.get(job.family) or prompts._HOUSE_SCHEMA
    for sl in slides:
        if not isinstance(sl, dict) or sl.get("layout") != "house-report":
            continue
        data = sl.get("data")
        if not isinstance(data, dict):
            continue
        used = house_slide_used_cm(data)
        ratio = used / body_h
        if ratio >= _FILL_RATIO_TARGET:
            continue
        try:
            _set(session, job, message="빈 공간 내용 보강 중... (내부 LLM)")
            raw = _call_llm(
                session,
                job,
                prompts.build_house_fill_messages(
                    data, content, int(ratio * 100), language, schema
                ),
            )
            parsed = parsing.parse_slides_json(raw, job.family)
            new_data = parsed[0].get("data") if parsed and isinstance(parsed[0], dict) else None
            new_blocks = new_data.get("blocks") if isinstance(new_data, dict) else None
            if not isinstance(new_blocks, list) or not new_blocks:
                continue
            trial = dict(data)
            trial["blocks"] = new_blocks
            new_used = house_slide_used_cm(trial)
            ceiling = body_h * 1.02
            # 오버슈트면 통째로 버리지 말고 페이지에 맞춰 끝에서부터 덜어낸다(빈 슬라이드 방지).
            if new_used > ceiling:
                new_blocks = _trim_house_blocks_to_fit(new_blocks, body_h * 0.99)
                trial["blocks"] = new_blocks
                new_used = house_slide_used_cm(trial)
            # 더 채워졌고 한 페이지를 (거의) 안 넘으면 채택. 넘치면 원본 유지(언더필 < 오버플로).
            if new_used > used + 0.3 and new_used <= ceiling:
                data["blocks"] = new_blocks
                logger.info(
                    "ppt_generator %s 슬라이드 채움: %.0f%% → %.0f%%",
                    job.id,
                    ratio * 100,
                    new_used / body_h * 100,
                )
        except Exception as e:  # noqa: BLE001 — 채움 실패는 비치명적
            logger.info("ppt_generator %s 슬라이드 채움 실패(무시): %s", job.id, e)
    return slides


def _strip_house_conclusions(slides: list[dict]) -> None:
    """house 슬라이드에서 conclusion(파란 한줄평) 블록을 제거(in-place, row 자식 포함).

    사내 요청: 파란 줄 한줄평은 쓰지 않는다. (빈 슬라이드 정리는 뒤따르는 advisory strip 이 처리.)
    """
    for sl in slides:
        if not isinstance(sl, dict) or sl.get("layout") != "house-report":
            continue
        data = sl.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("blocks"), list):
            continue
        new_blocks: list = []
        for b in data["blocks"]:
            if isinstance(b, dict) and b.get("type") == "row":
                kids = [
                    k
                    for k in (b.get("blocks") or [])
                    if not (isinstance(k, dict) and k.get("type") == "conclusion")
                ]
                if kids:
                    b["blocks"] = kids
                    new_blocks.append(b)
                continue
            if not (isinstance(b, dict) and b.get("type") == "conclusion"):
                new_blocks.append(b)
        data["blocks"] = new_blocks


def _normalize_house_tables(slides: list[dict]) -> None:
    """LLM 이 표 header 를 **문자열**로 준 경우를 보정(in-place, row 자식 포함).

    header 가 리스트가 아니라 "구동 구성 및 제어" 같은 문자열이면, 빌더의 list() 가 **글자 단위로
    쪼개** 열이 수십 개로 폭발한다. 공백으로 나눈 단어 수가 실제 열 수(본문/colW)와 같으면 그 단어들을
    헤더로 쓰고, 아니면 헤더를 비워(headerless) 글자 쪼개짐을 막는다.
    """
    from ai_do_api.domains.ppt_generator.design.builders_house import _as_cells

    def _fix(b: object) -> None:
        if not isinstance(b, dict):
            return
        if b.get("type") == "row":
            for k in b.get("blocks") or []:
                _fix(k)
            return
        if b.get("type") == "table" and isinstance(b.get("header"), str):
            rows = b.get("rows") or []
            body_cols = max((len(_as_cells(r)) for r in rows), default=0)
            ncol = max(body_cols, len(b.get("colW") or []), 1)
            parts = b["header"].split()
            b["header"] = parts if len(parts) == ncol else []

    for sl in slides:
        if not isinstance(sl, dict) or sl.get("layout") != "house-report":
            continue
        data = sl.get("data")
        if isinstance(data, dict):
            for b in data.get("blocks") or []:
                _fix(b)


def _generate_house_spec(session, job: PptJob, family_key: str, params: dict) -> tuple[dict, int]:
    """두원 사내 진행보고 "하우스 스타일"(표 중심) — 블록 JSON 생성 → builders_house 렌더.

    이 양식은 표가 곧 내용이라 설계/내용을 분리하지 않고 한 번의 호출로 슬라이드 블록 JSON
    전체를 만든다. 본문(job.content, 첨부 추출 텍스트 포함)은 보안 정책상 외부 LLM 으로
    보내지 않고 내부 Qwen 으로만 처리한다(_generate_brandlogy_spec 와 동일). 외부로는
    비기밀 주제(≤100자) 기반 _research_block 결과만 참고로 붙는다.

    반환: (slides_spec, n_slides).
    """
    language = params.get("language") or "Korean"
    tone = params.get("tone") or "default"
    instructions = params.get("instructions")
    research_auth_gate = _PptResearchAuthGate()
    # 주제(≤100자) 외부 검색은 그대로 활용(비기밀 힌트만 나감) → 결과를 본문 앞에 붙인다.
    content = _research_block(session, job, auth_gate=research_auth_gate) + (job.content or "")

    # 사용자가 장수를 '직접 숫자로' 골랐는지(예: "5") vs '자유(분량 자동)'인지 구분한다.
    # 숫자를 고른 경우엔 그 장수를 존중(정확히 N장, 리패킹 생략)하고,
    # 자유면 '긴 자료를 짧게 요약'하도록 상한을 낮게(≤8) 잡고 리패킹으로 빈 페이지를 합친다.
    slide_range = str(params.get("slide_range") or "").strip()
    explicit_n = slide_range.isdigit()
    if explicit_n:
        n_slides = max(1, min(20, int(slide_range)))
        instructions = (instructions or "") + (
            f"\n[장수 고정] 본문 house-report 슬라이드를 **정확히 {n_slides}장** 만드세요"
            f"(표지 제외). 내용을 {n_slides}장에 고르게 나눠 채우고, 페이지를 줄이거나 합치지 마세요."
        )
    else:
        n_slides = max(1, min(8, job.n_slides or 4))

    messages = prompts.build_messages(
        content,
        n_slides,
        language,
        tone,
        instructions,
        bool(params.get("include_title_slide", True)),
        bool(params.get("include_toc", False)),
        family_key,
        exact_count=explicit_n,
    )

    use_claude = resolve_llm_workload_route(PPT_DESIGN_WORKLOAD_ID, session).route == "external"

    if use_claude:
        _set(session, job, message="Claude가 슬라이드 설계·작성 중...")
        sys_p, user_p = messages[0]["content"], messages[1]["content"]
        raw = _call_claude_design(session, sys_p, user_p, max_tokens=32000, job=job)
        try:
            slides = parsing.parse_slides_json(raw, family_key)
        except Exception as e:  # noqa: BLE001 — 1회 재시도
            logger.info("ppt_generator %s house Claude 파싱 실패: %s — 재시도", job.id, e)
            _set(session, job, message="재시도 중...")
            raw2 = _call_claude_design(
                session,
                sys_p,
                user_p + "\n\n반드시 JSON 객체 하나만, 코드블록·주변 텍스트 없이 출력하세요.",
                max_tokens=32000,
                job=job,
            )
            slides = parsing.parse_slides_json(raw2, family_key)
    else:
        logger.info("ppt_generator %s: 등록된 로컬 PPT 설계 경로 사용", job.id)
        _set(session, job, message="슬라이드 구조 생성 중... (내부 LLM)")
        raw = _call_llm(
            session,
            job,
            messages,
            workload_id=PPT_DESIGN_WORKLOAD_ID,
        )
        try:
            slides = parsing.parse_slides_json(raw, family_key)
        except Exception as e:  # noqa: BLE001 — 1회 재시도
            logger.info("ppt_generator %s house LLM 파싱 실패: %s — 재시도", job.id, e)
            retry = prompts.build_retry_messages(messages, raw, str(e))
            slides = parsing.parse_slides_json(
                _call_llm(
                    session,
                    job,
                    retry,
                    workload_id=PPT_DESIGN_WORKLOAD_ID,
                ),
                family_key,
            )

    # 전 섹션 외부 검색 보강: 1차 구조 생성 후, 섹션 제목을 기밀 제거한 일반 검색어로 바꿔
    # 외부 Claude 로 섹션별 검색 → 그 자료로 모든 섹션 내용을 보강한다(첨부 우선·구조 유지).
    # 외부로 나가는 건 일반화 검색어뿐(첨부/본문 X). 실패 시 원본 유지.
    try:
        slides = _enrich_house_with_research(
            session,
            job,
            slides,
            auth_gate=research_auth_gate,
        )
    except Exception as e:  # noqa: BLE001 — 보강은 보조 수단, 실패해도 생성 계속
        logger.info("ppt_generator %s house 섹션 보강 건너뜀: %s", job.id, e)

    # 파란 한줄평(conclusion) 제거(사내 요청) + 'AI/보안 유의사항' 메타 코멘트 제거(보고서 본문 아님).
    _strip_house_conclusions(slides)
    _strip_house_advisory_blocks(slides)
    # 표 header 가 문자열로 와 글자 단위로 쪼개지는 것 보정(열 폭발 방지).
    _normalize_house_tables(slides)
    # 사내 요청: 화살표 진행도(타임라인)는 날짜별 일정·진행이 있을 때만 — 날짜 없는 건 제거.
    _prune_dateless_timelines(slides)
    # 사내 요청: 타임라인 없는 compare 는 '구분 열'이 별도 표처럼 어긋나 보임 → 일반 다열 표로 합친다.
    _compare_to_table_if_no_timeline(slides)

    # 사내 요청: '명칭: 설명' 나열형 불릿은 표(구분|내용)로 보여준다. 리패킹 전에 변환해
    # 표 높이로 페이지 배치가 정확히 계산되도록 한다.
    _house_textlists_to_tables(slides)
    # 사내 요청: 글만 나열된 1열 표(테두리 박스)는 outline(■→1)→…)으로 — 박스 군더더기 제거.
    _house_singlecol_to_outline(slides)

    # 사내 정책: PPT 는 최대한 컴팩트하게(여백·페이지 수 최소화). LLM 이 페이지를 다 못 채우고
    # 내용을 여러 슬라이드로 흩뜨리므로, 렌더 전에 언더필 슬라이드를 본문 영역이 허용하는 한
    # 합쳐 페이지 수를 줄인다(슬라이드 분할 없음, 합쳐진 슬라이드 제목은 ■ 섹션으로 강등).
    # 단, 사용자가 장수를 '직접 숫자로' 고른 경우엔 그 장수를 존중해 리패킹(병합)을 건너뛴다.
    if explicit_n:
        logger.info("ppt_generator %s house 장수 고정(%d장 요청) → 리패킹 생략", job.id, n_slides)
    else:
        try:
            from ai_do_api.domains.ppt_generator.design.builders_house import (
                repack_house_slides,
            )

            packed = repack_house_slides(slides)
            if packed:
                logger.info(
                    "ppt_generator %s house 리패킹: %d장 → %d장",
                    job.id,
                    len(slides),
                    len(packed),
                )
                slides = packed
        except Exception as e:  # noqa: BLE001 — 리패킹 실패는 비치명적, 원본 유지
            logger.info("ppt_generator %s house 리패킹 건너뜀: %s", job.id, e)

    # 채움률 < 80% 인 슬라이드를 자료 기반 내용으로 보강(아래쪽 공백 최소화). 보강 후 표 변환·
    # 보안 코멘트 제거를 다시 한 번 적용한다(채움이 추가한 내용에도 동일 규칙 적용).
    try:
        slides = _fill_underfilled_house_slides(session, job, slides)
        # 재정규화는 **채움이 실제로 내용을 추가했을 때만** 의미가 있다. 채움이 꺼져 있으면(no-op)
        # 위(리패킹 전) 패스 결과가 그대로라, 동일 7개 트리 순회를 다시 도는 것은 순수 낭비다.
        if _HOUSE_FILL_AUGMENT:
            _strip_house_conclusions(slides)
            _strip_house_advisory_blocks(slides)
            _normalize_house_tables(slides)
            _prune_dateless_timelines(slides)
            _compare_to_table_if_no_timeline(slides)
            _house_textlists_to_tables(slides)
            _house_singlecol_to_outline(slides)
        # 리패킹이 제목을 ■섹션으로 강등하며 본문 없는 장 표지를 남길 수 있으므로, 채움 여부와
        # 무관하게 본문 없는 섹션 제목(장 표지)을 제거한다(의미 없는 ■제목+목적만 방지).
        _prune_house_empty_sections(slides)
    except Exception as e:  # noqa: BLE001 — 채움은 보조 수단, 실패해도 생성 계속
        logger.info("ppt_generator %s house 슬라이드 채움 건너뜀: %s", job.id, e)

    # 사내 요청: 메인 덱은 **공백 없이 조밀하게 최대 3장**으로 채우고, 넘치는 상세만 '똑딱이'(OLE)로 뺀다.
    # 마지막 본문장에 아이콘을 달고(finalize 가 그 자리에 상세본 덱을 OLE 로 주입), 아이콘 PNG 를
    # MinIO 에 저장(위치 매칭 기준). 사용자가 장수를 직접 고른 경우(explicit_n)엔 압축을 건너뛴다.
    # house_embeds[i] = {"slides": [...]} — 똑딱이 i 안에 임베드될 상세본 덱. 아이콘 idx 로 1:1 매칭.
    house_embeds: list[dict] = []
    if not explicit_n:
        try:
            compacted, anchored, catchall = _compact_house_overflow(slides)
            last_house = next(
                (
                    s
                    for s in reversed(compacted)
                    if isinstance(s, dict) and s.get("layout") == "house-report"
                ),
                None,
            )
            # 똑딱이 상세본 상단에 찍을 문서 제목(메인 덱과 동일). 요청 topic 우선, 없으면 첫 본문장 제목.
            report_title = (str(params.get("topic") or "").strip()) or next(
                (
                    str((s.get("data") or {}).get("title") or "").strip()
                    for s in compacted
                    if isinstance(s, dict)
                    and s.get("layout") == "house-report"
                    and str((s.get("data") or {}).get("title") or "").strip()
                ),
                "",
            )

            def _icon_src(idx: int) -> str:
                png = ole.make_ole_icon_png(idx=idx)
                return "data:image/png;base64," + base64.b64encode(png).decode("ascii")

            # 섹션별 똑딱이: 제목 옆 작은 아이콘 + 그 섹션의 넘친 본문을 임베드(맥락형).
            for head_block, spilled in anchored:
                sec_title = str(head_block.get("section") or "")
                detail = _build_house_detail_slides(
                    spilled, section_title=sec_title, deck_title=report_title
                )
                if not detail:
                    continue
                idx = len(house_embeds)
                head_block["ole"] = {"src": _icon_src(idx), "idx": idx}
                house_embeds.append({"slides": detail})

            # 넘침 catch-all → '지 맘대로' 보이는 우하단 코너 대신 **마지막 페이지의 마지막 섹션 제목 옆**에
            # 붙인다(맥락형, 겹침 없음). 붙일 섹션 제목이 없을 때만 우하단 코너 아이콘으로 폴백.
            cat_detail = (
                _build_house_detail_slides(catchall, deck_title=report_title) if catchall else []
            )
            cat_used = False
            if cat_detail and last_house is not None:
                idx = len(house_embeds)
                blocks = (last_house.get("data") or {}).get("blocks") or []
                anchor_blk = next(
                    (
                        b
                        for b in reversed(blocks)
                        if isinstance(b, dict) and b.get("section") and not b.get("ole")
                    ),
                    None,
                )
                if anchor_blk is not None:
                    anchor_blk["ole"] = {"src": _icon_src(idx), "idx": idx}
                else:
                    last_house.setdefault("data", {})["ole_icon"] = {
                        "src": _icon_src(idx),
                        "idx": idx,
                    }
                house_embeds.append({"slides": cat_detail})
                cat_used = True

            # 아이콘 부착까지 끝난 뒤 압축 확정(넘침 없으면 압축만 적용).
            slides = compacted
            if house_embeds:
                logger.info(
                    "ppt_generator %s house 압축 → 본문 %d장 + 똑딱이 %d개(섹션 %d/catch-all %d)",
                    job.id,
                    len(
                        [
                            s
                            for s in slides
                            if isinstance(s, dict) and s.get("layout") == "house-report"
                        ]
                    ),
                    len(house_embeds),
                    len([1 for _h, sp in anchored if sp]),
                    1 if cat_used else 0,
                )
        except Exception as e:  # noqa: BLE001 — 압축·똑딱이 실패는 비치명적, 원본(slides) 유지
            logger.info("ppt_generator %s house 압축·똑딱이 건너뜀(원본 유지): %s", job.id, e)

    # 페이지 번호·총장수를 실제 생성 결과에 맞춰 정규화한다. LLM 이 meta.total/no 를 요청 n
    # 기준으로 채워, 반환 장수가 다르면 푸터('N / total')가 어긋나기 때문.
    total = len(slides)
    for i, sl in enumerate(slides):
        data = sl.get("data") if isinstance(sl, dict) else None
        if not isinstance(data, dict):
            continue
        data["no"] = i + 1
        meta = data.get("meta")
        if not isinstance(meta, dict):
            meta = {}
            data["meta"] = meta
        meta["total"] = total

    # 표지: 세미나 참석 보고와 동일한 두원 A4 표지(a4-cover)를 맨 앞에 붙인다.
    # 본문(house-report) 페이지 번호는 표지를 세지 않으므로 위 meta.total/no 는 그대로 둔다.
    first_data = (slides[0].get("data") or {}) if slides and isinstance(slides[0], dict) else {}
    cover_title = (
        (params.get("topic") or "").strip()
        or str(first_data.get("title") or "").strip()
        or (content[:40].strip() if content else "진행 보고")
    )
    cover_data = {"TITLE": cover_title}
    if params.get("author_name"):
        cover_data["AUTHOR"] = params["author_name"]
    if params.get("version"):
        cover_data["VERSION"] = params["version"]
    slides = [{"layout": "a4-cover", "data": cover_data}, *slides]

    out_spec: dict = {"family": family_key, "slides": slides}
    if house_embeds:
        out_spec["house_embeds"] = house_embeds
    return out_spec, total + 1


def _parse_doowon_body_html(raw_html: str) -> tuple[str, list[dict], str]:
    """Claude 본문 HTML → (덱 제목, 섹션[{title,subtitle,inner_html}], 공통 style)."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(raw_html or "", "html.parser")
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    body_style = "\n".join(st.get_text() for st in soup.find_all("style"))
    sections: list[dict] = []
    found = soup.select("section.doowon-body") or soup.find_all("section")
    for sec in found:
        sections.append(
            {
                "title": sec.get("data-title") or "",
                "subtitle": sec.get("data-subtitle") or "",
                "inner_html": sec.decode_contents(),
            }
        )
    return title, sections, body_style


def _generate_doowon_free_spec(
    session, job: PptJob, family_key: str, params: dict
) -> tuple[dict, int]:
    """두원 양식(자유 본문) — 보안 정책상 외부 본문 생성 대신 내부 LLM 파이프라인 사용.

    Claude 는 '주제(≤100자) 최신정보 검색' 용도로만 쓰이고(=_generate_doowon_qwen_spec
    내부 _research_block), 첨부 파일/본문은 외부로 나가지 않고 내부 Qwen 으로만 처리한다.
    """
    return _generate_doowon_qwen_spec(session, job, family_key, params)


def _generate_doowon_qwen_spec(
    session, job: PptJob, family_key: str, params: dict
) -> tuple[dict, int]:
    """두원 양식(내부 LLM 자동) — 내용은 JSON, 디자인은 서버 §14 템플릿.

    파이프라인: (1) Qwen 아웃라인 1콜 → (2) 슬라이드별 Qwen 채움 N콜 →
    (3) doowon_templates 로 §14 본문 HTML 렌더 → (4) doowon_frame 두원 틀로 합성.
    반환: (slides_spec[format=html, chrome=doowon], n_slides). Claude 불필요.
    """
    from ai_do_api.domains.ppt_generator.design import doowon_frame, doowon_templates

    language = params.get("language") or "Korean"
    tone = params.get("tone") or "default"
    instructions = params.get("instructions")
    # 외부 Claude 로 주제(≤100자)만 보내 최신정보 검색 → Qwen 자료 앞에 붙임(첨부파일은 Qwen 만).
    content = _research_block(session, job) + (job.content or "")
    # 페이지 수 선택이 없는 양식은 family 의 fixed_body_n 으로 본문 장수를 고정한다.
    _, _fam = resolve_family(family_key)
    fixed_n = _fam.get("fixed_body_n")
    n_body = int(fixed_n) if fixed_n else max(1, min(14, job.n_slides or 6))

    # (1) 아웃라인 — 덱 제목 + 슬라이드별 pattern/brief
    _set(session, job, message="AI가 발표 구성(아웃라인) 작성 중...")
    outline_msgs = prompts.build_doowon_qwen_outline_messages(
        content, n_body, language, tone, instructions
    )
    try:
        deck_title, outline = parsing.parse_doowon_qwen_outline(
            _call_freeform_llm(session, job, outline_msgs, max_tokens=4000), n_body
        )
    except Exception as e:  # noqa: BLE001 — 아웃라인 실패 시 균등 bullets 폴백
        logger.info("ppt_generator %s 아웃라인 파싱 실패: %s — bullets 폴백", job.id, e)
        deck_title = ""
        outline = [{"title": "", "pattern": "bullets", "brief": ""} for _ in range(n_body)]

    # (2)+(3) 슬라이드별 채움 → §14 본문 HTML 렌더
    sections: list[dict] = []
    total = len(outline)
    # 입력 자료가 매우 길면 채움 단계 프롬프트가 비대해지므로 발췌(앞부분) 사용.
    content_excerpt = content if len(content) <= 8000 else content[:8000]
    for idx, o in enumerate(outline, start=1):
        _set(session, job, message=f"AI가 본문 작성 중... ({idx}/{total})")
        fill_msgs = prompts.build_doowon_qwen_fill_messages(
            deck_title or (content[:40].strip() if content else "발표 자료"),
            idx,
            total,
            o.get("title") or "",
            o.get("pattern") or "bullets",
            o.get("brief") or "",
            content_excerpt,
            language,
            tone,
            instructions,
        )
        try:
            slide = parsing.parse_doowon_qwen_slide(
                _call_freeform_llm(session, job, fill_msgs, max_tokens=5000), o
            )
        except Exception as e:  # noqa: BLE001 — 한 장 실패해도 전체는 진행
            logger.info("ppt_generator %s 슬라이드 %d 채움 실패: %s", job.id, idx, e)
            slide = {
                "title": o.get("title") or "",
                "pattern": "bullets",
                "groups": [{"heading": o.get("title") or "", "items": []}],
            }
        sections.append(doowon_templates.render_section(slide))

    cover_title = deck_title or (content[:40].strip() if content else "발표 자료")
    deck_html = doowon_frame.compose_deck(
        title=cover_title,
        author=params.get("author_name") or None,
        version=params.get("version"),
        sections=sections,
        body_style="",
    )
    spec = {
        "family": family_key,
        "format": "html",
        "html": deck_html,
        "slide_w": doowon_frame.SLIDE_W_PX,
        "slide_h": doowon_frame.SLIDE_H_PX,
        "slide_w_cm": doowon_frame.SLIDE_W_CM,
        "slide_h_cm": doowon_frame.SLIDE_H_CM,
        "chrome": "doowon",
        "cover": {
            "title": cover_title,
            "author": params.get("author_name") or None,
            "version": params.get("version"),
        },
        "body": sections,
        "body_style": "",
        "body_w": doowon_frame.BODY_W_PX,
        "body_h": doowon_frame.BODY_H_PX,
    }
    return spec, len(sections) + 1  # +표지 1장


def _resolve_slot_image_uris(job: PptJob, slot_texts: list[str]) -> list[str | None]:
    """params[source_images] 의 사진들을 slot(사진 자리)별 텍스트와 근접 매칭 → data URI 리스트.

    매칭/임베드는 서버 내부에서만(외부 전송 없음). 사진이 없거나 실패하면 전부 None.
    """
    if not slot_texts:
        return []
    refs = (job.params or {}).get("source_images") or []
    if not refs:
        return [None] * len(slot_texts)
    images: list[dict] = []
    for r in refs:
        data = ppt_service.fetch_object_bytes(r.get("key") or "")
        if not data:
            continue
        images.append({"data": data, "text": r.get("text") or ""})
    if not images:
        return [None] * len(slot_texts)
    assigned = src_images.match_images_to_slots(slot_texts, images)
    uris: list[str | None] = []
    for idx in assigned:
        if idx is None or idx >= len(images):
            uris.append(None)
        else:
            uris.append(src_images.to_data_uri(images[idx]["data"]))
    return uris


def _apply_slot_images(job: PptJob, slots: list[dict], ctx_texts: list[str]) -> None:
    """사진 슬롯(dict)들에 첨부 자료의 이미지를 근접 매칭해 채운다 → 각 slot['photo_src'] 설정.

    첨부 PDF/PPTX 에서 추출한 이미지·도식만 사용한다(가상 생성 없음). 매칭되는 이미지가
    없는 슬롯은 비워 둔다. 추출·매칭은 전부 서버 내부에서만 수행(외부 전송 없음).
    """
    if not slots:
        return
    for slot, uri in zip(slots, _resolve_slot_image_uris(job, ctx_texts)):
        if uri:
            slot["photo_src"] = uri


def _inject_seminar_photos(job: PptJob, slide: dict) -> None:
    """세미나 본문 — remark 의 photo 항목에 첨부 자료 이미지 주입(매칭 없으면 빈칸)."""
    sections = slide.get("sections") or []
    slots: list[dict] = []
    ctxs: list[str] = []
    for sec in sections:
        remark = sec.get("remark") or {}
        items = remark.get("items") if isinstance(remark, dict) else None
        if not items:
            continue
        ctx_base = " ".join(
            [
                str(sec.get("topic") or ""),
                " ".join(str(p) for p in (sec.get("points") or [])),
            ]
        )
        for it in items:
            if isinstance(it, dict) and it.get("photo"):
                slots.append(it)
                ctxs.append(
                    " ".join([ctx_base, str(it.get("label") or ""), str(it.get("caption") or "")])
                )
    _apply_slot_images(job, slots, ctxs)


def _build_schedule_ole_pptx(job: PptJob) -> bytes | None:
    """params[schedule_images](도형/화살표 시트 렌더 이미지)로 '첨부 일정표' 덱(.pptx) 생성.

    똑딱이(OLE)로 임베드할 대상 — 이미지 1장당 슬라이드 1장(가로 슬라이드에 맞춰 배치). 더블클릭하면
    이 덱이 열려 원본 일정표를 크게 볼 수 있다. 이미지가 없으면 None.
    """
    refs = (job.params or {}).get("schedule_images") or []
    datas: list[bytes] = []
    for r in refs:
        data = ppt_service.fetch_object_bytes(r.get("key") or "")
        if data:
            datas.append(data)
    if not datas:
        return None
    prs = Presentation()
    sw, sh = int(prs.slide_width), int(prs.slide_height)
    blank = prs.slide_layouts[6]  # blank
    for data in datas:
        slide = prs.slides.add_slide(blank)
        try:
            from PIL import Image

            with Image.open(io.BytesIO(data)) as im:
                iw, ih = im.size
        except Exception:
            iw, ih = 1000, 645
        scale = min(sw / iw, sh / ih)
        w, h = int(iw * scale), int(ih * scale)
        slide.shapes.add_picture(io.BytesIO(data), (sw - w) // 2, (sh - h) // 2, width=w, height=h)
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _build_seminar_ole_pptx(job: PptJob) -> bytes | None:
    """접은 출장 일정(params[fold_trip])을 두원 양식 출장 일정 페이지 덱(.pptx)으로 렌더.

    fold_trip 이 없거나 렌더에 실패하면 None. (첨부 엑셀 시트 이미지는 fold_trip 과 상호배타라
    별도 _build_schedule_ole_pptx 가 담당한다 — 여기서 폴백하지 않는다.)
    """
    trip = (job.params or {}).get("fold_trip")
    if not (isinstance(trip, dict) and trip.get("days")):
        return None
    try:
        from ai_do_api.domains.ppt_generator.design import doowon_frame, doowon_templates
        from ai_do_api.domains.ppt_generator.design.html_to_pptx import (
            doowon_deck_to_pptx_bytes,
        )

        _, fam = resolve_family(job.family)
        sec = doowon_templates.render_section(trip)
        return doowon_deck_to_pptx_bytes(
            {"title": str(trip.get("title") or "출장 일정")},
            [sec],
            "",
            logo_path=fam.get("logo_path"),
            body_w_px=doowon_frame.BODY_W_PX,
            body_h_px=doowon_frame.BODY_H_PX,
        )
    except Exception as e:  # noqa: BLE001
        logger.info("ppt_generator %s 출장 일정 똑딱이 덱 빌드 실패: %s", job.id, e)
        return None


def _inject_seminar_ole_icon(session, job: PptJob, report_pages: list[dict]) -> bool:
    """세미나 첫 본문 페이지의 비고칸에 똑딱이(OLE) 아이콘을 심는다.

    대상: 첨부 엑셀 도형/화살표 시트 이미지(params[schedule_images]) 또는 페이지를 못 채워
    접은 출장 일정(params[fold_trip]). 아이콘 그림을 MinIO 에 저장(finalize 가 같은 바이트로
    OLE 위치를 찾는 기준)하고, 같은 바이트의 data URI 를 첫 섹션 비고 항목 ole_src 로 넣는다.
    finalize `_maybe_embed_ole`(doowon-seminar 분기)가 이 자리에 일정표/출장 덱을 OLE 로 주입한다.
    아이콘도 비고 항목 하나를 추가하므로, 생성 흐름에서는 가능하면 pagination 전에 원본 slide에
    먼저 호출해야 한다. 그래야 사진/메모가 이미 많은 비고칸에 아이콘을 덧붙이는 경우도 페이지
    분할 계산에 반영되어 표가 겹치지 않는다.
    """
    import base64

    has_sched = bool((job.params or {}).get("schedule_images"))
    has_trip = bool((job.params or {}).get("fold_trip"))
    if not (has_sched or has_trip) or not report_pages:
        return False
    caption = "첨부 일정표" if has_sched else "출장 일정"
    sections = report_pages[0].get("sections")
    if not isinstance(sections, list) or not sections:
        return False
    icon_bytes = ole.make_ole_icon_png()
    prefix = ppt_service.job_prefix(job.workspace_id, job.id)
    try:
        _put_object(f"{prefix}/embed/icon.png", icon_bytes, "image/png")
    except Exception as e:  # noqa: BLE001
        logger.info("ppt_generator %s 세미나 일정표 똑딱이 아이콘 저장 실패: %s", job.id, e)
        return False
    src = "data:image/png;base64," + base64.b64encode(icon_bytes).decode("ascii")

    def _remark_empty(s: dict) -> bool:
        rk = s.get("remark")
        if not isinstance(rk, dict):
            return True
        return not (rk.get("items") or rk.get("photos") or rk.get("note") or rk.get("caption"))

    # 사진 등 이미 내용이 있는 비고에 겹쳐 붙지 않도록, 비고가 빈 행을 우선 고른다(없으면 첫 행).
    sec = next((s for s in sections if _remark_empty(s)), sections[0])
    remark = sec.get("remark")
    if not isinstance(remark, dict):
        remark = {}
        sec["remark"] = remark
    items = remark.get("items")
    if not isinstance(items, list):
        # 기존 photos/note 를 items 로 승격(내용 유실 방지) 후 아이콘 항목 추가.
        items = []
        for p in remark.get("photos") or []:
            items.append({"label": p, "photo": True})
        if remark.get("note"):
            items.append({"caption": remark.get("note")})
        remark["items"] = items
    items.append({"ole_src": src, "caption": caption, "photo": False})
    return True


def _education_ole_slot(slide: dict) -> dict | None:
    """교육 보고서에서 '똑딱이'(결과보고서)를 박을 비고 슬롯(dict)을 고른다.

    우선순위: 비고 caption 에 '보고서'/'결과' → photo:true 인 비고 → '교육내용' 행.
    """
    rows = slide.get("rows") or []
    for r in rows:
        rk = r.get("remark")
        if isinstance(rk, dict):
            cap = str(rk.get("caption") or "")
            if "보고서" in cap or "결과" in cap:
                return rk
    for r in rows:
        rk = r.get("remark")
        if isinstance(rk, dict) and rk.get("photo"):
            return rk
    for r in rows:
        if str(r.get("label") or "").replace(" ", "") == "교육내용":
            if not isinstance(r.get("remark"), dict):
                r["remark"] = {}
            return r["remark"]
    return None


def _inject_education_ole_icon(session, job: PptJob, slide: dict) -> None:
    """교육 보고서 비고 슬롯에 '똑딱이' 아이콘을 심는다(첨부 여부와 무관).

    결과보고서 덱은 finalize 에서 (첨부 .pptx 가 있으면 그것, 없으면 자동 생성) 만들어
    이 아이콘 자리에 OLE 로 임베드한다. 아이콘 그림을 MinIO 에 저장(파이널라이즈에서 동일
    바이트로 OLE 위치를 찾는 기준)하고, 같은 바이트의 data URI 를 슬롯 ole_src 로 넣는다.
    """
    import base64

    slot = _education_ole_slot(slide)
    if slot is None:
        return
    icon_bytes = ole.make_ole_icon_png()
    prefix = ppt_service.job_prefix(job.workspace_id, job.id)
    icon_key = f"{prefix}/embed/icon.png"
    try:
        _put_object(icon_key, icon_bytes, "image/png")
    except Exception as e:  # noqa: BLE001
        logger.info("ppt_generator %s 똑딱이 아이콘 저장 실패: %s", job.id, e)
        return
    slot["ole_src"] = "data:image/png;base64," + base64.b64encode(icon_bytes).decode("ascii")
    slot["photo"] = False
    # 똑딱이(OLE) 아이콘만 표시 — 비고칸 텍스트(캡션/메모)는 비워 아이콘과 글씨가 겹치지 않게 한다.
    slot["caption"] = ""
    slot.pop("note", None)


def _extract_education_items(slide: dict) -> list[str]:
    """교육 슬라이드 rows 의 '교육내용' 항목 리스트(번호/마커 제거) — 목차·본문 항목으로 사용."""
    import re

    for r in slide.get("rows") or []:
        if str(r.get("label") or "").replace(" ", "") == "교육내용":
            content = r.get("content")
            if not isinstance(content, (list, tuple)):
                content = [content] if content else []
            items = []
            for c in content:
                s = re.sub(r"^\s*\d+\s*[.)]\s*", "", str(c).strip())  # 'N.'/'N)' 제거
                s = s.lstrip("▶·•◦-– ").strip()
                if s:
                    items.append(s)
            return items
    return []


def _build_and_store_result_spec(
    session, job: PptJob, params: dict, slide: dict, content: str
) -> str | None:
    """똑딱이 결과보고서 덱(표지+목차+본문 N장) 스펙을 만들어 MinIO 에 저장.

    본문은 교육내용 항목마다 Qwen 이 입력자료(검색+첨부) 기반으로 자유 작성. finalize 가 이
    스펙을 두원 pptx 로 변환해 OLE 로 임베드한다. 항목이 없으면 저장하지 않음(placeholder 폴백).

    반환: 미리보기용으로 합성한 결과보고서 HTML 덱(표지+목차+본문). 항목이 없으면 None.
    """
    import json as _json
    import re

    from ai_do_api.domains.ppt_generator.design import doowon_frame, doowon_templates

    items = _extract_education_items(slide)
    if not items:
        return None
    language = params.get("language") or "Korean"
    tone = params.get("tone") or "default"
    instructions = params.get("instructions")
    topic = (params.get("topic") or "").strip()
    subject = str(slide.get("title") or "").strip() or topic
    subject = re.sub(r"^교육\s*보고서\s*[–\-:]\s*", "", subject).strip() or topic or "교육"
    excerpt = content if len(content) <= 8000 else content[:8000]

    _set(session, job, message="AI가 결과보고서 본문 작성 중...")
    msgs = prompts.build_education_result_messages(
        subject, items, excerpt, language, tone, instructions
    )
    try:
        data = parsing.parse_json_object(_call_freeform_llm(session, job, msgs, max_tokens=8000))
    except Exception as e:  # noqa: BLE001
        logger.info("ppt_generator %s 결과보고서 본문 생성 실패: %s", job.id, e)
        data = {}
    filled = data.get("sections") if isinstance(data, dict) else None
    filled = filled or []

    # 본문 이미지 — 첨부 자료(PDF/PPTX)에서 추출한 이미지·도식을 슬라이드별로 근접 매칭.
    # 매칭되는 이미지가 없으면 비워 둔다(가상 생성 없음). 첨부 파일·본문은 외부로 나가지 않는다.
    slide_ctxs: list[str] = []
    for i, _item in enumerate(items):
        _fs = filled[i] if i < len(filled) and isinstance(filled[i], dict) else {}
        slide_ctxs.append(" ".join([str(_item), str(_fs.get("header") or "")]).strip())
    img_uris = _resolve_slot_image_uris(job, slide_ctxs)
    if any(img_uris):
        _set(session, job, message="첨부 자료 이미지 배치 중...")

    toc = doowon_templates.render_section({"pattern": "toc", "title": subject, "items": items})
    body_sections = []
    for i, item in enumerate(items):
        fs = filled[i] if i < len(filled) and isinstance(filled[i], dict) else {}
        sec = {
            "pattern": "result_body",
            "title": f"{i + 1}. {item}",
            "header": fs.get("header") or item,
            "subsections": fs.get("subsections") or [],
        }
        tbl = fs.get("table")
        if isinstance(tbl, dict) and tbl.get("columns") and tbl.get("rows"):
            sec["table"] = tbl
        flw = fs.get("flow")
        if isinstance(flw, dict) and isinstance(flw.get("nodes"), list) and len(flw["nodes"]) >= 2:
            sec["flow"] = flw
        if i < len(img_uris) and img_uris[i]:
            sec["image_src"] = img_uris[i]
        body_sections.append(doowon_templates.render_section(sec))
    result_spec = {
        "cover": {
            "title": f"{subject} 교육보고서",
            "author": params.get("author_name") or None,
            "version": None,
        },
        "sections": [toc, *body_sections],
        "body_style": "",
    }
    key = f"{ppt_service.job_prefix(job.workspace_id, job.id)}/embed/result_spec.json"
    try:
        _put_object(
            key,
            _json.dumps(result_spec, ensure_ascii=False).encode("utf-8"),
            "application/json",
        )
    except Exception as e:  # noqa: BLE001
        logger.info("ppt_generator %s 결과보고서 스펙 저장 실패: %s", job.id, e)

    # 미리보기용: finalize 의 OLE 임베드(데스크톱 PPT 전용)와 동일한 결과보고서 덱을
    # 두원 틀로 합성해 HTML 로도 돌려준다 → 프론트가 똑딱이 안 내용을 미리 보여준다.
    try:
        return doowon_frame.compose_deck(
            title=result_spec["cover"]["title"],
            author=result_spec["cover"].get("author"),
            version=None,
            sections=[toc, *body_sections],
            body_style="",
        )
    except Exception as e:  # noqa: BLE001
        logger.info("ppt_generator %s 결과보고서 미리보기 합성 실패: %s", job.id, e)
        return None


# 세미나 본문 페이지 분할 — 기본은 단일 페이지. 내용이 한 장에 안 들어갈 때만 늘린다.
# 예산 = 본문 한 장에 들어가는 대략적 "줄 수". 표는 내용 크기대로 렌더(약하게만 채움)하므로
# 분할은 "실제로 넘칠 때만" 일어나야 한다. 예산이 실제 용량보다 낮으면 작은 섹션이 불필요하게
# 다른 장으로 밀려나(→ 외로운 스텁 → 늘림) 보기 싫어지므로, 실제 용량(≈22줄)에 맞춰 넉넉히 잡되
# 넘침(겹침) 방지를 위해 약간의 여유를 둔다.
_SEM_FIRST_BUDGET = 16.0  # 1페이지(정보헤더 포함) 행 용량(가중치)
_SEM_MID_BUDGET = 20.0  # 정보헤더 없는 페이지 행 용량
_SEM_CONCL_WEIGHT = 3.0  # 소감 박스가 차지하는 양
_SEM_META_WEIGHT = 4.0  # 정보헤더가 차지하는 양(1페이지 용량에서 차감)
_SEM_SINGLE_BUDGET = 17.0  # 정보헤더+표+소감을 한 장에 담을 수 있는 상한
_SEM_MAX_PAGES = 5
_SEM_FILL_TARGET = 0.90  # 본문 페이지 충원률 목표(사내 요청: 세미나 보고도 90%)


def _est_lines(text: object, width: int) -> int:
    """문자열이 폭(글자수 기준)에서 대략 몇 줄로 접히는지 추정(빈 문자열 0, 최소 1)."""
    s = str(text or "").strip()
    if not s:
        return 0
    return max(1, math.ceil(len(s) / max(1, width)))


def _seminar_row_weight(r: dict) -> float:
    """주요 내용 표 한 행의 대략적 높이(가중치).

    행 높이는 '주제 및 주요 내용' 칸의 줄 수로 지배된다. points 를 개수만 세면 긴 불릿이
    여러 줄로 접힐 때 실제 높이를 과소평가해(→ 병합/미분할 → 페이지 넘침·겹침) 문제가 됐다.
    각 불릿의 접힘 줄 수를 합산하고, 비고(remark) 항목·항목명 줄 수와의 최댓값으로 잡는다.
    """
    if not isinstance(r, dict):
        return 1.0
    points = r.get("points")
    if isinstance(points, list):
        p_lines = sum(_est_lines(p, 34) for p in points)
    else:
        p_lines = _est_lines(points, 34)
    w = float(max(1, p_lines))
    remark = r.get("remark")
    if isinstance(remark, dict):
        # 비고는 신규 items 형태와 레거시 photos 형태 둘 다 행 수만큼 세로로 펼쳐진다.
        items = remark.get("items")
        photos = remark.get("photos")
        if isinstance(items, list):
            r_lines = 0.0
            for it in items:
                if isinstance(it, dict) and it.get("photo"):
                    r_lines += 3.0  # 사진 자리표시자는 세로로 크다
                else:
                    cap = it.get("caption") if isinstance(it, dict) else it
                    r_lines += max(1, _est_lines(cap, 12))
        elif isinstance(photos, list):
            r_lines = float(len(photos) * 3)  # 사진은 각 ~3줄 높이
        else:
            r_lines = 0.0
        if r_lines:
            w = max(w, r_lines)
    # 항목명(topic/item) 이 길어 접히는 경우도 하한으로 반영
    w = max(w, float(_est_lines(r.get("topic") or r.get("item"), 9)))
    return w


def _seminar_trip_weight(trip: dict) -> float:
    """출장 일정 표의 대략적 높이(가중치).

    행 수만 세면 한 행에 여러 줄(개회선언/인사말/첫삽 등)이 들어갈 때 실제 높이를 크게
    과소평가해, 본문 페이지와 합쳐질 때 페이지를 넘쳐 겹쳐 찍힌다(사용자 보고 증상).
    각 행을 '내용 줄 수'와 '참석 인원 줄 수'의 최댓값으로 환산해 합산한다(+제목 행 1).
    """
    if not isinstance(trip, dict):
        return 0.0
    total = 1.0  # '■ 출장 일정' 제목 행
    for d in trip.get("days") or []:
        if not isinstance(d, dict):
            continue
        for row in d.get("rows") or []:
            if not isinstance(row, dict):
                total += 1.0
                continue
            content = row.get("content")
            if isinstance(content, list):
                c_lines = sum(_est_lines(c, 28) for c in content)
            else:
                c_lines = _est_lines(content, 28)
            a_lines = _est_lines(row.get("attendees"), 16)
            total += float(max(1, c_lines, a_lines))
    return total


def _maybe_merge_trip_into_report(report_pages: list[dict], trip: dict) -> bool:
    """마지막 report 페이지에 여유가 있으면 출장 일정을 그 페이지에 합친다(빈 페이지 방지).

    합쳤으면 report_pages[-1]["trip"] 을 세팅하고 True 를 반환(호출측은 별도 trip 섹션을 안 붙임).
    여유가 없으면 False(출장 일정은 기존처럼 독립 페이지).
    """
    if not report_pages or not isinstance(trip, dict) or not trip.get("days"):
        return False
    last = report_pages[-1]
    last_w = sum(_seminar_row_weight(r) for r in (last.get("sections") or []))
    if last.get("conclusion"):
        last_w += _SEM_CONCL_WEIGHT
    if last.get("meta"):
        last_w += _SEM_META_WEIGHT
    if last_w + _seminar_trip_weight(trip) <= _SEM_MID_BUDGET:
        last["trip"] = trip
        return True
    return False


def _paginate_seminar_report(slide: dict) -> list[dict]:
    """세미나 보고 본문을 행 수에 따라 1~여러 페이지로 분할한다.

    1페이지: 정보헤더 + 행 일부 / 중간: 행만 / 마지막: 행 + 소감(공간 없으면 소감 전용 페이지).
    행이 적으면 기존처럼 단일 페이지(page_role=single)로 둔다.
    """
    rows = slide.get("sections") or []
    conclusion = slide.get("conclusion") or []
    action = slide.get("action") or ""
    meta = slide.get("meta") or {}
    weights = [_seminar_row_weight(r) for r in rows]
    base = {
        k: v
        for k, v in slide.items()
        if k not in ("sections", "conclusion", "action", "meta", "page_role")
    }
    # 정보헤더+표+소감이 한 장 상한에 들어가면 단일 페이지. (행이 1개여도 그 행이 커서
    # 소감까지 넘치면 아래 분할 로직이 소감을 다음 장으로 내려 겹침을 막는다 — 행 수가 아니라
    # 실제 무게로만 판정한다.)
    if sum(weights) + _SEM_CONCL_WEIGHT <= _SEM_SINGLE_BUDGET:
        return [dict(slide, page_role="single")]

    chunks: list[list[dict]] = []
    cur: list[dict] = []
    cur_w = 0.0
    for r, w in zip(rows, weights):
        budget = _SEM_FIRST_BUDGET if not chunks else _SEM_MID_BUDGET
        if cur and cur_w + w > budget and len(chunks) < _SEM_MAX_PAGES - 1:
            chunks.append(cur)
            cur, cur_w = [], 0.0
        cur.append(r)
        cur_w += w
    if cur:
        chunks.append(cur)

    pages: list[dict] = []
    for i, ch in enumerate(chunks):
        page = dict(base)
        page["pattern"] = "seminar_report"
        page["sections"] = ch
        page["meta"] = meta if i == 0 else {}
        page["page_role"] = "first" if i == 0 else "middle"
        pages.append(page)

    last = pages[-1]
    last_w = sum(_seminar_row_weight(r) for r in last["sections"])
    # 소감을 마지막 페이지에 얹을 수 있는 여유. 한 장짜리(=1페이지, 정보헤더 meta 가 이미 실려 있음)
    # 는 앞 게이트와 동일하게 _SEM_SINGLE_BUDGET 로 판정해야 한다(MID 로 재면 meta 만큼 넘쳐
    # 소감이 하단과 겹친다). 중간에서 이어진 마지막 페이지는 meta 가 없으므로 MID 여유.
    inline_budget = _SEM_SINGLE_BUDGET if len(pages) == 1 else _SEM_MID_BUDGET
    if last_w + _SEM_CONCL_WEIGHT <= inline_budget:
        last["conclusion"] = conclusion
        last["action"] = action
        # 결국 한 장으로 합쳐졌으면 meta 헤더+소감을 모두 보여주는 single 로 둔다.
        if len(pages) == 1:
            last["meta"] = meta
            last["page_role"] = "single"
        else:
            last["page_role"] = "last"
    else:
        tail = dict(base)
        tail["pattern"] = "seminar_report"
        tail["sections"] = []
        tail["meta"] = {}
        tail["conclusion"] = conclusion
        tail["action"] = action
        tail["page_role"] = "last"
        pages.append(tail)
    return pages


def _generate_doowon_seminar_spec(
    session, job: PptJob, family_key: str, params: dict
) -> tuple[dict, int]:
    """세미나 참석 보고 — 두원 틀 + 내부 LLM 단일 본문(정보헤더+주요내용표+소감).

    파이프라인: (1) Qwen 단일 채움 콜 → (2) doowon_templates 로 본문 HTML 렌더 →
    (3) doowon_frame 두원 틀로 합성. 본문 1장 고정(아웃라인 불필요).
    """
    from ai_do_api.domains.ppt_generator.design import doowon_frame, doowon_templates

    language = params.get("language") or "Korean"
    tone = params.get("tone") or "default"
    instructions = params.get("instructions")
    # 출장/세미나 보고서는 '실제 있었던 일' 기반이라 외부 웹검색을 섞지 않는다.
    # (웹검색 결과가 사실처럼 표/일정에 녹아드는 할루시네이션 방지 — 첨부/기타 참고사항만 사용)
    content = job.content or ""
    content_excerpt = content if len(content) <= 8000 else content[:8000]

    # 본문 1 — 세미나 참석 보고(정보헤더+주요내용+소감)
    _set(session, job, message="AI가 세미나 보고 본문 작성 중... (1/2)")
    fill_msgs = prompts.build_doowon_seminar_fill_messages(
        content_excerpt, language, tone, instructions
    )
    fallback = {
        "title": content[:40].strip() if content else "세미나 참석 보고",
        "pattern": "seminar_report",
    }
    try:
        slide = parsing.parse_doowon_qwen_slide(
            # 사실 추출이라 낮은 temperature + presence_penalty=0(원문 재사용 억제 해제)로
            # 자료에 없는 이름/날짜/수치/발언을 지어내는 경향을 줄인다.
            _call_freeform_llm(
                session,
                job,
                fill_msgs,
                max_tokens=6000,
                temperature=0.2,
                presence_penalty=0.0,
            ),
            fallback,
        )
    except Exception as e:  # noqa: BLE001
        logger.info("ppt_generator %s 세미나 본문 채움 실패: %s", job.id, e)
        slide = dict(fallback)
    slide.setdefault("pattern", "seminar_report")

    # 본문 2 — 출장 일정 표
    _set(session, job, message="AI가 출장 일정 작성 중... (2/2)")
    trip_msgs = prompts.build_doowon_seminar_trip_messages(
        content_excerpt, language, tone, instructions
    )
    trip_fallback = {"title": "출장 일정", "pattern": "trip_schedule"}
    try:
        trip = parsing.parse_doowon_qwen_slide(
            _call_freeform_llm(
                session,
                job,
                trip_msgs,
                max_tokens=5000,
                temperature=0.2,
                presence_penalty=0.0,
            ),
            trip_fallback,
        )
    except Exception as e:  # noqa: BLE001
        logger.info("ppt_generator %s 출장 일정 채움 실패: %s", job.id, e)
        trip = dict(trip_fallback)
    trip.setdefault("pattern", "trip_schedule")
    if not trip.get("title"):
        trip["title"] = "출장 일정"

    # (충원률 미달 시 LLM 재확장은 제거 — 표가 CSS 로 세로 공간을 채우므로 시각적 공백은 없고,
    #  출장보고서는 사실 기반이라 분량 채우기용 확장이 없는 내용을 지어내는 원인이었음.)

    # 첨부 사진(있으면) → 비고칸 photo 항목에 근접 매칭해 주입
    try:
        _inject_seminar_photos(job, slide)
    except Exception as e:  # noqa: BLE001
        logger.info("ppt_generator %s 세미나 사진 주입 실패: %s", job.id, e)

    has_sched = bool((job.params or {}).get("schedule_images"))
    # 이전 실행(재시도/재생성)에서 커밋돼 남았을 수 있는 stale fold_trip. 이번 실행에 첨부 일정표가
    # 있으면 OLE 슬롯은 첨부 일정표가 우선이므로 아이콘 주입 전에 먼저 제거를 시도한다.
    prev_fold = (job.params or {}).get("fold_trip")
    if has_sched and prev_fold is not None:
        _p_sched = dict(job.params or {})
        _p_sched.pop("fold_trip", None)
        job.params = _p_sched
        flag_modified(job, "params")
        try:
            session.commit()
            prev_fold = None
        except Exception as e:  # noqa: BLE001
            logger.info("ppt_generator %s stale fold_trip 사전 정리 실패: %s", job.id, e)
            session.rollback()
            # 커밋 실패로 DB 에 stale 값이 남아도 아래 아이콘/finalize 경로는 schedule_images 를 우선한다.

    # 첨부 엑셀 도형/화살표 시트(schedule_images) 아이콘은 pagination 전에 원본 slide 에
    # 먼저 주입한다. 아이콘도 비고 항목 하나를 늘리므로, 뒤늦게 붙이면 이미 계산된 표 높이를
    # 초과해 첫 본문 페이지가 겹칠 수 있다.
    if has_sched:
        _inject_seminar_ole_icon(session, job, [slide])

    # 본문이 길면 주요 내용 표를 여러 페이지로 분할(정보헤더 1페이지·소감 마지막 페이지).
    report_pages = _paginate_seminar_report(slide)
    # 출장 일정: 마지막 report 페이지에 여유가 있으면 그 페이지에 합쳐 빈 페이지를 없앤다.
    merged_trip = _maybe_merge_trip_into_report(report_pages, trip)
    # 합쳐지지도 않고 한 페이지를 90% 이상 채우지도 못하는 출장 일정은, 애매한 반쪽짜리 페이지로
    # 두지 않고 '똑딱이'(OLE)로 접는다(사용자 요청). 단:
    #  (1) 첨부 엑셀 일정표 이미지(schedule_images)가 있으면 OLE 자리는 그 첨부 몫이므로 출장
    #      일정은 접지 않고 별도 페이지로 둔다(하나의 OLE 슬롯에 둘 다 담을 수 없어 첨부 유실 방지).
    #  (2) 접기로 정하면 finalize 가 아니라 지금 출장 일정 덱을 렌더해 MinIO 에 저장하고, 성공한
    #      경우에만 접는다. finalize 는 저장된 바이트를 재사용(중복 렌더 없음)하며, 렌더/저장이
    #      실패하면 접지 않아(별도 페이지로) 출장 일정이 조용히 사라지지 않는다.
    fold_trip = False
    if (
        not merged_trip
        and not has_sched
        and isinstance(trip, dict)
        and trip.get("days")
        and _seminar_trip_weight(trip) < _SEM_MID_BUDGET * _SEM_FILL_TARGET
    ):
        _orig_params = job.params
        _p = dict(_orig_params or {})
        _p["fold_trip"] = trip
        job.params = (
            _p  # _build_seminar_ole_pptx / _inject_seminar_ole_icon 가 params[fold_trip] 를 읽는다
        )
        ole_bytes = _build_seminar_ole_pptx(job)
        stored = False
        if ole_bytes:
            try:
                _prefix = ppt_service.job_prefix(job.workspace_id, job.id)
                _put_object(
                    f"{_prefix}/embed/seminar_ole.pptx",
                    ole_bytes,
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                )
                stored = True
            except Exception as e:  # noqa: BLE001
                logger.info(
                    "ppt_generator %s 출장 일정 똑딱이 덱 저장 실패(접지 않음): %s", job.id, e
                )
        # 덱 저장 + 비고칸 아이콘 주입이 **모두** 성공해야 접는다. 아이콘이 없으면 finalize 가
        # OLE 를 넣지 못해 출장 일정이 미리보기·최종본에서 조용히 사라지므로, 하나라도 실패하면
        # 접지 않고 아래에서 별도 페이지로 렌더한다(사용자 입력 유실 방지).
        fold_slide = copy.deepcopy(slide)
        if stored and _inject_seminar_ole_icon(session, job, [fold_slide]):
            # 접은 출장 일정 아이콘도 비고 항목을 하나 늘린다. 원본 slide 에 주입한 뒤 다시
            # paginate 해서 아이콘 높이를 분할 계산에 반영한다.
            fold_report_pages = _paginate_seminar_report(fold_slide)
            # fold_trip 은 params[fold_trip] 커밋이 성공한 뒤에만 확정한다 — 커밋이 실패하면
            # 접지 않고(별도 페이지) params 를 되돌려 출장 일정이 사라지지 않게 한다.
            flag_modified(job, "params")
            try:
                session.commit()
                slide = fold_slide
                report_pages = fold_report_pages
                fold_trip = True
            except Exception as e:  # noqa: BLE001
                logger.info("ppt_generator %s fold_trip 커밋 실패(접지 않음): %s", job.id, e)
                session.rollback()
                job.params = _orig_params
        else:
            job.params = _orig_params  # 접지 않음 → fold_trip 미저장, 아래에서 별도 페이지로.
    # 접지 않기로 했는데 params 에 (이전 실행의) fold_trip 이 남아 있으면 제거·커밋한다.
    if not fold_trip and prev_fold is not None:
        _p2 = dict(job.params or {})
        _p2.pop("fold_trip", None)
        job.params = _p2
        flag_modified(job, "params")
        try:
            session.commit()
        except Exception as e:  # noqa: BLE001
            logger.info("ppt_generator %s stale fold_trip 정리 실패: %s", job.id, e)
            session.rollback()
    sections = [doowon_templates.render_section(p) for p in report_pages]
    # 출장 일정을 별도 페이지로 붙이는 건 **실제 일정 행이 있을 때만**. 자료에 일정이 없으면
    # 프롬프트가 days=[] 를 반환하는데(없는 일정 창작 금지), 그걸 그대로 렌더하면 헤더만 있는
    # 빈 '출장 일정' 페이지가 생긴다 → 빈 페이지를 추가하지 않는다.
    if not merged_trip and not fold_trip and isinstance(trip, dict) and trip.get("days"):
        sections.append(doowon_templates.render_section(trip))
    cover_title = str(slide.get("title") or "").strip() or (
        content[:40].strip() if content else "세미나 참석 보고"
    )
    deck_html = doowon_frame.compose_deck(
        title=cover_title,
        author=params.get("author_name") or None,
        version=params.get("version"),
        sections=sections,
        body_style="",
    )
    spec = {
        "family": family_key,
        "format": "html",
        "html": deck_html,
        "slide_w": doowon_frame.SLIDE_W_PX,
        "slide_h": doowon_frame.SLIDE_H_PX,
        "slide_w_cm": doowon_frame.SLIDE_W_CM,
        "slide_h_cm": doowon_frame.SLIDE_H_CM,
        "chrome": "doowon",
        "cover": {
            "title": cover_title,
            "author": params.get("author_name") or None,
            "version": params.get("version"),
        },
        "body": sections,
        "body_style": "",
        "body_w": doowon_frame.BODY_W_PX,
        "body_h": doowon_frame.BODY_H_PX,
    }
    return spec, len(sections) + 1  # +표지 1장


def _generate_doowon_education_spec(
    session, job: PptJob, family_key: str, params: dict
) -> tuple[dict, int]:
    """교육 보고서 — 두원 틀 + 내부 LLM 단일 본문(구분/내용/비고 표).

    파이프라인: (1) Qwen 단일 채움 콜 → (2) doowon_templates 로 본문 HTML 렌더 →
    (3) doowon_frame 두원 틀로 합성. 본문 1장 고정.
    """
    from ai_do_api.domains.ppt_generator.design import doowon_frame, doowon_templates

    language = params.get("language") or "Korean"
    tone = params.get("tone") or "default"
    instructions = params.get("instructions")
    # 외부 Claude 로 주제(≤100자)만 보내 최신정보 검색 → Qwen 자료 앞에 붙임(첨부파일은 Qwen 만).
    content = _research_block(session, job) + (job.content or "")
    content_excerpt = content if len(content) <= 8000 else content[:8000]

    _set(session, job, message="AI가 교육 보고서 본문 작성 중...")
    fill_msgs = prompts.build_doowon_education_fill_messages(
        content_excerpt, language, tone, instructions
    )
    fallback = {
        "title": content[:40].strip() if content else "교육 보고서",
        "pattern": "education_report",
    }
    try:
        slide = parsing.parse_doowon_qwen_slide(
            _call_freeform_llm(session, job, fill_msgs, max_tokens=6000), fallback
        )
    except Exception as e:  # noqa: BLE001
        logger.info("ppt_generator %s 교육 보고서 본문 채움 실패: %s", job.id, e)
        slide = dict(fallback)
    slide.setdefault("pattern", "education_report")

    # 똑딱이 아이콘을 심어 그 슬롯을 photo=False 로 만든다(외부 표엔 똑딱이 1개만 남긴다).
    # 별도 '교육 현장 사진' 등 비고칸 사진 슬롯은 만들지 않는다 — 모든 이미지·도식은
    # 똑딱이(교육 결과 보고서) 안에 담는다(사용자 요청).
    try:
        _inject_education_ole_icon(session, job, slide)
    except Exception as e:  # noqa: BLE001
        logger.info("ppt_generator %s 똑딱이 아이콘 주입 실패: %s", job.id, e)
    # 똑딱이 안에 들어갈 결과보고서 덱 스펙 생성·저장(첨부 .pptx 없으면 이걸 임베드)
    embed_preview_html: str | None = None
    if not (params.get("embed_pptx") or {}).get("key"):
        try:
            embed_preview_html = _build_and_store_result_spec(session, job, params, slide, content)
        except Exception as e:  # noqa: BLE001
            logger.info("ppt_generator %s 결과보고서 스펙 생성 실패: %s", job.id, e)

    sections = [doowon_templates.render_section(slide)]
    cover_title = str(slide.get("title") or "").strip() or (
        content[:40].strip() if content else "교육 보고서"
    )
    deck_html = doowon_frame.compose_deck(
        title=cover_title,
        author=params.get("author_name") or None,
        version=params.get("version"),
        sections=sections,
        body_style="",
    )
    spec = {
        "family": family_key,
        "format": "html",
        "html": deck_html,
        "slide_w": doowon_frame.SLIDE_W_PX,
        "slide_h": doowon_frame.SLIDE_H_PX,
        "slide_w_cm": doowon_frame.SLIDE_W_CM,
        "slide_h_cm": doowon_frame.SLIDE_H_CM,
        "chrome": "doowon",
        "cover": {
            "title": cover_title,
            "author": params.get("author_name") or None,
            "version": params.get("version"),
        },
        "body": sections,
        "body_style": "",
        "body_w": doowon_frame.BODY_W_PX,
        "body_h": doowon_frame.BODY_H_PX,
    }
    # 미리보기 전용: 똑딱이(OLE) 안에 임베드될 결과보고서 덱을 HTML 로도 함께 실어
    # 프론트가 메인 미리보기 아래에 "똑딱이 내용"으로 펼쳐 보여줄 수 있게 한다.
    if embed_preview_html:
        spec["embed_preview"] = {
            "html": embed_preview_html,
            "slide_w": doowon_frame.SLIDE_W_PX,
            "title": "교육 결과 보고서",
        }
    return spec, len(sections) + 1  # +표지 1장


_ASR_LANG_HINT = {"Korean": "ko", "English": "en", "Japanese": "ja", "Chinese": "zh"}


def _transcribe_audio_uploads(session, job: PptJob) -> str:
    """params[audio_files] 의 음원을 STT 전사해 텍스트로 합친다.

    현재 생성 API가 audio_files 를 넣지 않으면 no-op 이다. 값이 있을 때도 실패한 파일은
    건너뛰어 회의록 생성 자체를 막지 않는다.
    """
    refs = (job.params or {}).get("audio_files") or []
    if not refs:
        return ""
    import os as _os
    import tempfile
    from pathlib import Path

    from ai_do_api.core.asr import get_asr_backend

    lang = _ASR_LANG_HINT.get((job.params or {}).get("language") or "Korean", "ko")
    try:
        backend = get_asr_backend()
    except Exception as e:  # noqa: BLE001
        logger.warning("ppt_generator %s ASR 백엔드 준비 실패: %s", job.id, e)
        return ""
    parts: list[str] = []
    for i, ref in enumerate(refs):
        if not isinstance(ref, dict):
            continue
        data = ppt_service.fetch_object_bytes(ref.get("key") or "")
        if not data:
            continue
        _set(session, job, message=f"회의 녹취 전사 중... ({i + 1}/{len(refs)})")
        ext = ref.get("ext") or ".bin"
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp.write(data)
                tmp_path = tmp.name
            result = backend.transcribe(Path(tmp_path), language_hint=lang)
            text = (getattr(result, "text", "") or "").strip()
            if text:
                parts.append(f"[{ref.get('filename') or f'녹취{i + 1}'}]\n{text}")
        except Exception as e:  # noqa: BLE001
            logger.warning("ppt_generator %s 음원 전사 실패(무시): %s", job.id, e)
        finally:
            if tmp_path:
                try:
                    _os.unlink(tmp_path)
                except OSError:
                    pass
    return "\n\n".join(parts)


def _job_author_name(session, job: PptJob) -> str:
    """회의록 작성자 — 잡을 생성한 접속 사용자의 표시 이름."""
    try:
        from ai_do_api.domains.auth.models import User

        user = session.get(User, job.user_id)
        if not user:
            return ""
        base = (
            getattr(user, "display_name", None) or getattr(user, "full_name", None) or ""
        ).strip()
        title = (getattr(user, "job_title", None) or "").strip()
        if title and base and title not in base:
            return f"{base} {title}"
        return base
    except Exception as e:  # noqa: BLE001
        logger.info("ppt_generator %s 작성자 조회 실패: %s", job.id, e)
        return ""


def _generate_doowon_meeting_spec(
    session, job: PptJob, family_key: str, params: dict
) -> tuple[dict, int]:
    """회의록 — 두원 세로 A4 1장. 회의 메모/문서 → 머리표+회의내용 정리."""
    from ai_do_api.domains.ppt_generator.design import doowon_templates

    language = params.get("language") or "Korean"
    tone = params.get("tone") or "default"
    instructions = params.get("instructions")
    transcript = _transcribe_audio_uploads(session, job)
    content = (transcript + "\n\n" + (job.content or "")).strip()
    content_excerpt = content if len(content) <= 12000 else content[:12000]

    _set(session, job, message="AI가 회의록 정리 중...")
    fill_msgs = prompts.build_doowon_meeting_fill_messages(
        content_excerpt, language, tone, instructions
    )
    fallback = {"title": (content[:28].strip() if content else "회의록")}
    try:
        slide = parsing.parse_json_object(
            _call_freeform_llm(session, job, fill_msgs, max_tokens=8000)
        )
        if not isinstance(slide, dict):
            slide = dict(fallback)
    except Exception as e:  # noqa: BLE001
        logger.info("ppt_generator %s 회의록 정리 실패: %s", job.id, e)
        slide = dict(fallback)
    if not str(slide.get("title") or "").strip():
        slide["title"] = fallback["title"]
    # 표지 작성자는 개인 이름 대신 소속 고정 라벨(params["author_name"])로 통일한다.
    # (다른 양식과 동일 정책 — 개인정보 비노출.) 고정 라벨이 LLM 이 노트에서 추출한 작성자보다
    # 우선한다(가드 안에 두면 Qwen 이 author 를 채운 정상 경우에 개인명이 그대로 노출됨).
    slide["author"] = (
        params.get("author_name")
        or str(slide.get("author") or "").strip()
        or _job_author_name(session, job)
    )

    deck_html = doowon_templates.render_meeting_minutes_deck(slide)
    spec = {
        "family": family_key,
        "format": "html",
        "html": deck_html,
        "slide_w": doowon_templates.MEETING_W_PX,
        "slide_h": doowon_templates.MEETING_H_PX,
        "slide_w_cm": doowon_templates.MEETING_W_CM,
        "slide_h_cm": doowon_templates.MEETING_H_CM,
        "cover": {"title": str(slide.get("title") or "회의록")},
    }
    return spec, 1


def _call_llm(
    session,
    job: PptJob,
    messages,
    *,
    temperature=0.6,
    max_tokens=None,
    extra_body: dict[str, object] | None = None,
    workload_id: str = "ppt_generate",
) -> str:
    # None이면 공통 Gateway가 workload 상한을 사용하고, 명시한 더 작은 값도 그 상한으로 제한한다.
    ctx = LlmTaskContext(
        source="worker.ppt_generator",
        workspace_id=job.workspace_id,
        task_kind=("ppt_design" if workload_id == PPT_DESIGN_WORKLOAD_ID else "ppt_generate"),
        app_id="ppt-assistant",
        actor_user_id=job.user_id,
        principal_kind="user",
        principal_id=job.user_id,
    )
    result = execute_llm(
        workload_id,
        LlmWorkloadContext.from_task_context(ctx),
        session,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        reasoning_effort="none",
        extra_body=extra_body,
        audit_entity_id=job.id,
        conversation_id=_chat_conversation_id(job),
    )
    return result.completion.text or ""


def _chat_conversation_id(job: PptJob) -> str | None:
    chat_result = job.chat_result if isinstance(job.chat_result, dict) else {}
    value = chat_result.get("conversation_id")
    return value if isinstance(value, str) and value.strip() else None


def _set_chat_result(session, job: PptJob, chat_result: dict) -> None:
    _set(session, job, chat_result=chat_result)
    _append_chat_assistant_turn(session, job, chat_result)


def _append_chat_assistant_turn(session, job: PptJob, chat_result: dict) -> None:
    conversation_id = _chat_conversation_id(job)
    if not conversation_id:
        return
    try:
        conversation = session.get(Conversation, conversation_id)
        if (
            conversation is None
            or conversation.workspace_id != job.workspace_id
            or conversation.user_id != job.user_id
            or conversation.deleted_at is not None
        ):
            return
        status = str(chat_result.get("status") or "")
        app_persistence.append_assistant_app_turn(
            session,
            conversation=conversation,
            content=str(chat_result.get("answer") or ""),
            meta={
                "kind": "ppt_job",
                "response_status": "error" if status == "error" else "done",
                "intent": chat_result.get("intent"),
                "refreshed_slide_index": chat_result.get("refreshed_slide_index"),
                "job_id": job.id,
            },
        )
    except Exception:  # noqa: BLE001 - job state is the worker's primary contract
        session.rollback()
        logger.exception("ppt_generator.chat_turn_persist_failed job=%s", job.id)


# ============================================================
# .pptx 빌드 (in-memory)
# ============================================================
def _find_browser() -> str | None:
    # 브라우저 탐색은 크로스플랫폼 정본(html_to_pptx._find_browser) 하나로 유지한다.
    # (브라우저 경로/명령 상수도 정본 한 곳에만 두어 워커·API 중복을 없앤다.)
    # (Windows 경로만 보던 옛 중복 구현이 prod Linux 워커에서 finalize 실패를 유발했음)
    from ai_do_api.domains.ppt_generator.design.html_to_pptx import (
        _find_browser as _canonical_find_browser,
    )

    return _canonical_find_browser()


def _html_deck_to_pptx_bytes(
    html: str, slide_w_px: int, slide_h_px: int, slide_w_cm: float = 27.0, slide_h_cm: float = 16.75
) -> bytes:
    """HTML 슬라이드 덱 → (Edge/Chrome 헤드리스) PDF → (pymupdf) 페이지 이미지 → 이미지 pptx."""
    import shutil
    import tempfile

    import fitz  # pymupdf
    from pptx.util import Cm

    from ai_do_api.domains.ppt_generator.design.html_to_pptx import (
        _bounded_browser_stderr,
        _run_browser,
    )

    browser = _find_browser()
    if browser is None:
        raise RuntimeError("PDF 변환용 브라우저(Edge/Chrome)를 찾을 수 없습니다.")

    # 헤드리스 브라우저가 종료 후에도 PDF 핸들을 잠깐 잡아 TemporaryDirectory 자동정리가
    # PermissionError 를 내므로, mkdtemp + ignore_errors 로 직접 정리한다.
    d = tempfile.mkdtemp(prefix="pptdeck_")
    try:
        html_path = os.path.join(d, "deck.html")
        pdf_path = os.path.join(d, "deck.pdf")
        # 인쇄 페이지네이션 강제: Claude HTML 의 @page/슬라이드 CSS 변형과 무관하게
        # 1 슬라이드 = 정확히 1 페이지({slide_w}×{slide_h})가 되도록 override 스타일 주입.
        override = (
            "<style id='__pptx_print_override'>"
            f"@page{{size:{slide_w_px}px {slide_h_px}px;margin:0;}}"
            "html,body{margin:0 !important;padding:0 !important;background:#fff !important;}"
            "*{-webkit-print-color-adjust:exact !important;print-color-adjust:exact !important;}"
            f".slide,section{{width:{slide_w_px}px !important;height:{slide_h_px}px !important;"
            "margin:0 !important;overflow:hidden !important;box-sizing:border-box !important;"
            "break-after:page !important;page-break-after:always !important;"
            "break-inside:avoid !important;page-break-inside:avoid !important;}"
            ".slide:last-child,section:last-child{break-after:auto !important;page-break-after:auto !important;}"
            ".slide+.slide{margin-top:0 !important;}"
            "</style>"
        )
        if "</head>" in html:
            html = html.replace("</head>", override + "</head>", 1)
        elif "<body" in html:
            import re as _re

            html = _re.sub(r"(<body[^>]*>)", r"\1" + override, html, count=1)
        else:
            html = override + html
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        file_url = "file:///" + html_path.replace("\\", "/")
        profile_dir = os.path.join(d, "browser-profile")
        result = _run_browser(
            [
                browser,
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                f"--user-data-dir={profile_dir}",
                "--no-pdf-header-footer",
                "--run-all-compositor-stages-before-draw",
                "--virtual-time-budget=10000",
                f"--print-to-pdf={pdf_path}",
                file_url,
            ],
            timeout=180,
            operation="HTML→PDF 변환",
        )
        if not os.path.exists(pdf_path):
            detail = _bounded_browser_stderr(result.stderr)
            suffix = f": {detail}" if detail else ""
            raise RuntimeError(f"HTML→PDF 변환 실패(PDF 미생성){suffix}")

        doc = fitz.open(pdf_path)
        prs = Presentation()
        prs.slide_width = Cm(slide_w_cm)
        prs.slide_height = Cm(slide_h_cm)
        blank = prs.slide_layouts[6]
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x 해상도
            png = pix.tobytes("png")
            slide = prs.slides.add_slide(blank)
            slide.shapes.add_picture(
                io.BytesIO(png), 0, 0, width=prs.slide_width, height=prs.slide_height
            )
        doc.close()
        buf = io.BytesIO()
        prs.save(buf)
        return buf.getvalue()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _build_pptx_bytes(family_key: str, slides: list[dict]) -> bytes:
    _, fam = resolve_family(family_key)
    prs = Presentation()
    prs.slide_width = fam["slide_w"]
    prs.slide_height = fam["slide_h"]
    logo = fam.get("logo_path")
    if logo and not os.path.exists(logo):
        logo = None
    build_fn = fam["build_fn"]
    # 일부 양식(예: doowon-house/TEST)은 본문 빌더와 다른 표지(a4-cover)를 섞어 쓴다.
    # a4-cover 레이아웃은 양식 build_fn 대신 공용 두원 A4 표지 빌더로 그린다.
    from ai_do_api.domains.ppt_generator.design.builders_a4 import (
        add_copyright_footer_to_master,
        add_dcc_watermark_to_master,
        build_a4_cover_slide,
        set_show_master_shapes,
    )

    # house(TEST): 사선 DCC 워터마크 + 하단 저작권 footer 를 본문마다 그리지 않고 슬라이드 마스터에
    # 1회만 올린다 → 모든 본문이 배경으로 상속해 PowerPoint 에서 선택·이동/편집 불가한 진짜 워터마크가
    # 된다. (본문 chrome 은 watermark=False, footer=False 로 그린다. builders_house._draw_frame 참고.)
    # 표지에선 set_show_master_shapes(False) 로 둘 다 가린다.
    house_master_wm = fam.get("design") == "house"
    if house_master_wm:
        add_dcc_watermark_to_master(prs)
        add_copyright_footer_to_master(prs)

    for s in slides:
        layout = s.get("layout")
        try:
            if layout == "a4-cover":
                build_a4_cover_slide(prs, s.get("data") or {}, logo_path=logo)
                if house_master_wm:
                    set_show_master_shapes(prs.slides[-1], False)
            else:
                build_fn(prs, layout, s.get("data") or {}, logo_path=logo)
        except Exception as e:  # noqa: BLE001 — 한 장 실패해도 진행
            logger.warning("ppt_generator slide build failed (layout=%s): %s", s.get("layout"), e)
            # 실패한 장을 조용히 누락하지 않고, 양식별 오류 슬라이드를 끼워 페이지 수·번호를 보존한다.
            if family_key == "doowon-v2":
                try:
                    build_fn(
                        prs,
                        "title-paragraph",
                        {"HEADER": "오류", "SLIDE_TITLE": "슬라이드 생성 실패", "BODY": str(e)},
                        logo_path=logo,
                    )
                except Exception:
                    pass
            elif fam.get("design") == "house":
                try:
                    build_fn(
                        prs,
                        "house-report",
                        {
                            "title": "슬라이드 생성 실패",
                            "meta": (s.get("data") or {}).get("meta") or {},
                            "no": (s.get("data") or {}).get("no"),
                            "blocks": [{"type": "conclusion", "text": str(e)}],
                        },
                        logo_path=logo,
                    )
                except Exception:
                    pass
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


# ============================================================
# MinIO
# ============================================================
_bucket_ensured = False


def _put_object(key: str, data: bytes, content_type: str) -> None:
    global _bucket_ensured
    settings = get_settings()
    client = _minio_client()
    # 버킷 존재 확인은 객체마다 반복할 필요 없음 — 프로세스당 1회만 (12장 덱 = put 13회).
    if not _bucket_ensured:
        if not client.bucket_exists(settings.minio_bucket):
            client.make_bucket(settings.minio_bucket)
        _bucket_ensured = True
    client.put_object(
        settings.minio_bucket,
        key,
        io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )


def _upload_pptx(job: PptJob, pptx_bytes: bytes) -> str:
    pptx_key = ppt_service.pptx_object_key(job.workspace_id, job.id)
    _put_object(pptx_key, pptx_bytes, _PPTX_MIME)
    return pptx_key


# ============================================================
# 작업 상태 헬퍼
# ============================================================
# ============================================================
# 참고 출처 → 슬라이드 페이지/섹션 매핑(추정)
# ============================================================
_TOKEN_RE = re.compile(r"[A-Za-z0-9]{2,}|[가-힣]{2,}")
# 매칭 변별력 없는 흔한 토큰(과매칭 방지).
_ATTR_STOP = {
    "그리고",
    "그러나",
    "대비",
    "기준",
    "현황",
    "대한",
    "위한",
    "통한",
    "있는",
    "없는",
    "또는",
    "보고",
    "내용",
    "주요",
    "핵심",
    "관련",
    "다양",
    "통해",
    "이를",
    "위해",
    "기술",
    "시장",
    "정보",
    "기업",
    "회사",
    "두원",
    "두원공조",
    "확인",
    "자료",
    "최신",
    "the",
    "and",
    "for",
    "with",
    "this",
    "that",
    "from",
    "are",
    "ev",
    "of",
}


# 내용이 아닌 구조/스타일 메타데이터 키 — 발췌·토큰에서 제외.
_NON_CONTENT_KEYS = {
    "type",
    "layout",
    "chart",
    "al",
    "align",
    "colw",
    "ratio",
    "h",
    "w",
    "x",
    "y",
    "fs",
    "color",
    "fill",
    "style",
}


def _collect_strings(obj) -> str:
    """dict/list 안의 내용 문자열을 재귀적으로 모아 한 문자열로(구조 키 제외)."""
    out: list[str] = []

    def walk(o):
        if isinstance(o, str):
            out.append(o)
        elif isinstance(o, dict):
            for k, v in o.items():
                if str(k).lower() in _NON_CONTENT_KEYS:
                    continue
                walk(v)
        elif isinstance(o, (list, tuple)):
            for v in o:
                walk(v)

    walk(obj)
    return " ".join(out)


def _attr_tokens(s: str) -> set[str]:
    toks = set()
    for t in _TOKEN_RE.findall(s or ""):
        tl = t.lower()
        if tl in _ATTR_STOP or len(tl) < 2:
            continue
        toks.add(tl)
    return toks


# house 블록 type → 사람이 읽는 종류 라벨.
_BLOCK_KIND_LABEL = {
    "lead": "개요",
    "table": "표",
    "chart": "차트",
    "timeline": "타임라인",
    "conclusion": "결론",
    "text": "본문",
}
_SEC_BULLET_RE = re.compile(r"^[\s■□▣▪◼◾●○◆◇·•∎]+")


def _block_excerpt(block: dict, limit: int = 46) -> str:
    """블록 대표 발췌 — 출처가 어느 내용에 반영됐는지 짧게 보여줄 텍스트."""
    s = re.sub(r"\s+", " ", _collect_strings(block)).strip()
    if len(s) > limit:
        s = s[:limit].rstrip() + "…"
    return s


def _flatten_units(blocks, cur_section: list[str], page: int, out: list[dict]) -> None:
    """블록 리스트(2단 row 포함)를 평탄화해 매칭 유닛으로 모은다.

    각 유닛: {page, kind(표/차트/본문/…), section(소제목), excerpt, tokens}.
    section 은 ■ 소제목을 시작하는 블록부터 다음 소제목 전까지 상속한다.
    """
    if not isinstance(blocks, list):
        return
    for b in blocks:
        if not isinstance(b, dict):
            continue
        if b.get("section"):
            cur_section[0] = _SEC_BULLET_RE.sub("", str(b["section"])).strip()
        btype = str(b.get("type") or "").lower()
        if btype == "row":
            _flatten_units(b.get("blocks") or b.get("cols") or [], cur_section, page, out)
            continue
        toks = _attr_tokens(_collect_strings(b))
        if not toks:
            continue
        out.append(
            {
                "page": page,
                "kind": _BLOCK_KIND_LABEL.get(btype, ""),
                "section": cur_section[0],
                "excerpt": _block_excerpt(b),
                "tokens": toks,
            }
        )


def _attribute_sources_to_pages(spec: dict, sources: list[dict]) -> list[dict]:
    """각 출처를 생성된 슬라이드의 키워드가 가장 겹치는 블록(페이지·소제목·종류)에 추정 매핑.

    페이지 번호 = 미리보기 슬라이드 순번(1-based, 표지 포함). 'slides' 리스트가 있는 spec
    (house/a4/brandlogy-json)만 처리하고, HTML 단일 spec 은 매핑하지 않는다(원문 구조 없음).
    블록 단위로 매칭해 page/section 뿐 아니라 kind(표/차트/본문/…)와 발췌(used_in)까지 채운다.
    겹치는 변별 토큰이 2개 미만이면 블록 매칭은 버리고 페이지 단위로만 추정한다(과매칭 방지).
    """
    slides = spec.get("slides") if isinstance(spec, dict) else None
    if not isinstance(slides, list) or not slides:
        return sources

    pages = []
    units: list[dict] = []
    for i, sl in enumerate(slides):
        data = (sl or {}).get("data") if isinstance(sl, dict) else {}
        data = data if isinstance(data, dict) else {}
        title = str(data.get("title") or data.get("TITLE") or "")
        pages.append(
            {
                "page": i + 1,
                "title": title,
                "tokens": _attr_tokens(title + " " + _collect_strings(data)),
            }
        )
        _flatten_units(data.get("blocks"), [title], i + 1, units)

    page_title = {pg["page"]: pg["title"] for pg in pages}

    for src in sources:
        text = " ".join(str(src.get(k) or "") for k in ("title", "snippet", "query"))
        stoks = _attr_tokens(text)
        if not stoks:
            continue
        # 1순위: 가장 많이 겹치는 블록 유닛.
        u_best, u_score = None, 0
        for u in units:
            sc = len(stoks & u["tokens"])
            if sc > u_score:
                u_best, u_score = u, sc
        if u_best is not None and u_score >= 2:
            src["page"] = u_best["page"]
            src["section"] = u_best["section"] or page_title.get(u_best["page"], "")
            if u_best["kind"]:
                src["block_kind"] = u_best["kind"]
            if u_best["excerpt"]:
                src["used_in"] = u_best["excerpt"]
            continue
        # 폴백: 페이지 단위 추정(블록 변별 토큰이 부족할 때).
        p_best, p_score = None, 0
        for pg in pages:
            sc = len(stoks & pg["tokens"])
            if sc > p_score:
                p_best, p_score = pg, sc
        if p_best is not None and p_score >= 2:
            src["page"] = p_best["page"]
            if p_best["title"]:
                src["section"] = p_best["title"]
    return sources


_HEARTBEAT_INTERVAL_S = 12.0
# 워커 부팅 시 이 시간보다 오래 갱신 안 된 running 작업은 죽은 것으로 보고 정리한다.
# 하트비트가 12초마다 updated_at 을 갱신하므로, 살아있는 작업은 절대 이만큼 오래되지 않는다.
_STALE_RUNNING_S = 300


def _start_job_heartbeat(job_id: str, interval: float = _HEARTBEAT_INTERVAL_S) -> threading.Event:
    """생성이 오래 걸리는 동안(특히 블로킹 LLM 호출 중) 백그라운드 스레드가 주기적으로
    job.updated_at 을 갱신해 '살아있음' 신호를 남긴다. 반환된 Event 를 set() 하면 멈춘다.

    프론트는 updated_at 신선도(서버 계산 heartbeat_age_seconds)로 '진행 중 vs 멈춤'을
    구분하고, 워커 부팅 sweep 이 신호가 끊긴 running 작업을 자동 정리한다. 스레드는 자체
    DB 세션을 쓰므로 메인 세션과 충돌하지 않는다(블로킹 LLM 호출로 메인은 대기 중).
    """
    stop = threading.Event()

    def _beat() -> None:
        while not stop.wait(interval):
            try:
                with _db_session_scope() as s:
                    s.execute(
                        _sa_text(
                            "UPDATE ppt_jobs SET updated_at = :now "
                            "WHERE id = :id AND status = 'running'"
                        ),
                        {"now": _utcnow(), "id": job_id},
                    )
                    s.commit()
            except Exception:  # noqa: BLE001 — 하트비트 실패는 비치명적
                pass

    th = threading.Thread(target=_beat, name=f"ppt-hb-{job_id[:8]}", daemon=True)
    th.start()
    return stop


def _sweep_stale_running_jobs() -> None:
    """워커 부팅 시, 신호가 끊긴 지 오래된 running 작업을 error 로 정리한다(좀비 청소).

    워커가 작업 중 죽으면 행은 'running' 으로 영원히 남아 프론트가 무한 대기한다. 하트비트가
    살아있는 작업은 항상 신선하므로, _STALE_RUNNING_S 보다 오래된 running 은 죽은 것이다.
    pending 은 정상 대기(긴 작업 뒤 줄서기)일 수 있어 건드리지 않는다.
    """
    try:
        cutoff = _utcnow() - timedelta(seconds=_STALE_RUNNING_S)
        with _db_session_scope() as s:
            res = s.execute(
                _sa_text(
                    "UPDATE ppt_jobs SET status = 'error', "
                    "message = :msg, error = :err, updated_at = :now "
                    "WHERE status = 'running' AND updated_at < :cutoff"
                ),
                {
                    "msg": "생성 실패(워커 중단으로 추정)",
                    "err": "워커 응답이 끊겨 자동 정리되었습니다. 다시 생성해 주세요.",
                    "now": _utcnow(),
                    "cutoff": cutoff,
                },
            )
            s.commit()
            if res.rowcount:
                logger.info("ppt_generator 부팅 sweep: stale running %d건 정리", res.rowcount)
    except Exception as e:  # noqa: BLE001 — sweep 실패는 비치명적
        logger.info("ppt_generator 부팅 sweep 건너뜀: %s", e)


@worker_ready.connect
def _on_worker_ready(**_kwargs) -> None:  # pragma: no cover — 부팅 시 1회
    _sweep_stale_running_jobs()


def _set(session, job: PptJob, **fields) -> None:
    # 생성 취소 가드: 사용자가 취소(status='cancelled')하면 그 이후 워커는 이 job row 를 **절대**
    # 갱신하지 않는다(status 전환뿐 아니라 message/error-만 갱신도 금지 — cancelled row 의
    # updated_at/message 가 바뀌면 안 됨). 취소는 API 의 다른 커넥션에서 커밋되므로, 무엇이든
    # 쓰기 전에 최신 status 를 다시 읽어 확인한다. 이미 cancelled 면 running/error/completed/message
    # 어떤 갱신도 폐기해 취소 상태를 보존한다.
    try:
        session.refresh(job, attribute_names=["status"])
    except Exception:  # noqa: BLE001 — 아직 flush 안 된 새 객체 등 refresh 불가 시엔 그대로 진행
        pass
    if getattr(job, "status", None) == "cancelled":
        logger.info(
            "ppt_generator %s 취소됨 — 이후 갱신 폐기(요청 status=%s)",
            job.id,
            fields.get("status"),
        )
        session.rollback()
        return
    # 완료 spec 이 들어오면 참고 출처를 슬라이드 페이지/섹션에 추정 매핑해 함께 갱신한다.
    spec = fields.get("slides_spec")
    if isinstance(spec, dict):
        srcs = (job.params or {}).get("research_sources")
        if isinstance(srcs, list) and srcs:
            try:
                params = dict(job.params or {})
                params["research_sources"] = _attribute_sources_to_pages(spec, srcs)
                job.params = params
                flag_modified(job, "params")
            except Exception as e:  # noqa: BLE001 — 매핑 실패는 비치명적
                logger.info("ppt_generator %s 출처 페이지 매핑 실패(무시): %s", job.id, e)
    for k, v in fields.items():
        setattr(job, k, v)
    job.updated_at = _utcnow()
    session.commit()


# ============================================================
# 태스크: 생성
# ============================================================
@celery_app.task(name="ppt_generator.generate", bind=True)
def generate(self, job_id: str) -> None:
    with _db_session_scope() as session:
        job = session.get(PptJob, job_id)
        if job is None:
            return
        # 시작 전 취소 감지(취소가 큐 픽업보다 늦거나 revoke 목록이 워커 재시작으로 사라진 경우).
        if job.status == "cancelled":
            logger.info("ppt_generator %s 시작 전 취소됨 — 생성 건너뜀", job.id)
            return
        # 긴 LLM 단계 동안에도 '살아있음' 신호(updated_at)를 남기는 하트비트 시작.
        _hb_stop = _start_job_heartbeat(job_id)
        try:
            _set(session, job, status="running", message="LLM에 슬라이드 구조 요청 중...")
            family_key, _fam = resolve_family(job.family)
            params = dict(job.params or {})
            template_reference = _template_reference_block(job, params)
            if template_reference:
                base_instructions = params.get("instructions")
                params["instructions"] = "\n\n".join(
                    part
                    for part in (
                        base_instructions if isinstance(base_instructions, str) else "",
                        template_reference,
                    )
                    if part.strip()
                )

            # 자유 양식(Brandlogy)은 Claude 단독으로 슬라이드 덱을 HTML 로 직접 생성.
            if _fam.get("design") == "brandlogy":
                spec, n_slides = _generate_brandlogy_spec(session, job, family_key, params)
                _set(
                    session,
                    job,
                    status="completed",
                    message="완료",
                    n_slides=n_slides,
                    slides_spec=spec,
                )
                return

            # 두원 양식(자유 본문) — Claude 본문 콘텐츠 + 서버 두원 틀 합성.
            if _fam.get("design") == "doowon-free":
                spec, n_slides = _generate_doowon_free_spec(session, job, family_key, params)
                _set(
                    session,
                    job,
                    status="completed",
                    message="완료",
                    n_slides=n_slides,
                    slides_spec=spec,
                )
                return

            # 두원 양식(Qwen 자동) — Qwen JSON 내용 + 서버 §14 템플릿 + 두원 틀 합성.
            if _fam.get("design") == "doowon-qwen":
                spec, n_slides = _generate_doowon_qwen_spec(session, job, family_key, params)
                _set(
                    session,
                    job,
                    status="completed",
                    message="완료",
                    n_slides=n_slides,
                    slides_spec=spec,
                )
                return

            # 회의록 — 세로 A4 단일 회의록 양식.
            if _fam.get("design") == "doowon-meeting":
                spec, n_slides = _generate_doowon_meeting_spec(session, job, family_key, params)
                _set(
                    session,
                    job,
                    status="completed",
                    message="완료",
                    n_slides=n_slides,
                    slides_spec=spec,
                )
                return

            # 세미나 참석 보고 — 두원 틀 + Qwen 단일 본문 채움.
            if _fam.get("design") == "doowon-seminar":
                spec, n_slides = _generate_doowon_seminar_spec(session, job, family_key, params)
                _set(
                    session,
                    job,
                    status="completed",
                    message="완료",
                    n_slides=n_slides,
                    slides_spec=spec,
                )
                return

            # 교육 보고서 — 두원 틀 + Qwen 단일 본문 표(구분/내용/비고) 채움.
            if _fam.get("design") == "doowon-education":
                spec, n_slides = _generate_doowon_education_spec(session, job, family_key, params)
                _set(
                    session,
                    job,
                    status="completed",
                    message="완료",
                    n_slides=n_slides,
                    slides_spec=spec,
                )
                return

            # 하우스 스타일(표 중심 진행보고) — Claude(기본) 또는 Qwen(기밀)이 블록 JSON 생성.
            if _fam.get("design") == "house":
                spec, n_slides = _generate_house_spec(session, job, family_key, params)
                _set(
                    session,
                    job,
                    status="completed",
                    message="완료",
                    n_slides=n_slides,
                    slides_spec=spec,
                )
                return

            messages = prompts.build_messages(
                job.content or "",
                job.n_slides,
                params.get("language") or "Korean",
                params.get("tone") or "default",
                params.get("instructions"),
                bool(params.get("include_title_slide", True)),
                bool(params.get("include_toc", False)),
                family_key,
            )
            raw = _call_llm(session, job, messages)
            _set(session, job, message="슬라이드 구조 파싱 중...")
            try:
                slides = parsing.parse_slides_json(raw, family_key)
            except Exception as e:  # noqa: BLE001 — 1회 재시도
                logger.info("ppt_generator %s 1차 파싱 실패: %s — 재시도", job_id, e)
                _set(session, job, message="LLM 응답 재시도 중...")
                retry_msgs = prompts.build_retry_messages(messages, raw, str(e))
                raw2 = _call_llm(session, job, retry_msgs)
                slides = parsing.parse_slides_json(raw2, family_key)

            # slides_spec 까지만 만들고 완료 — .pptx/미리보기는 'PPT로 전환'(finalize)에서.
            _set(
                session,
                job,
                status="completed",
                message="완료",
                n_slides=len(slides),
                slides_spec={"family": family_key, "slides": slides},
            )
        except Exception:  # noqa: BLE001
            logger.exception("ppt_generator.generate 실패 (job=%s)", job_id)
            # 내부 예외 원문은 로그에만 남기고, 사용자에겐 일반화된 메시지만 노출한다.
            _set(
                session,
                job,
                status="error",
                message="생성 실패",
                error="PPT 생성 중 오류가 발생했습니다.",
            )
        finally:
            _hb_stop.set()  # 하트비트 중단


# ============================================================
# 태스크: 챗봇 수정
# ============================================================
@celery_app.task(name="ppt_generator.chat_edit", bind=True)
def chat_edit(self, job_id: str) -> None:
    with _db_session_scope() as session:
        job = session.get(PptJob, job_id)
        if job is None:
            return
        cr = dict(job.chat_result or {})
        message = (cr.get("message") or "").strip()
        history = cr.get("history") or []
        family_key, fam = resolve_family(job.family)
        spec = job.slides_spec or {}
        slides = list(spec.get("slides") or [])
        valid_layouts = set(fam["builders"].keys())

        # 자유 양식(HTML 덱) 수정 — Claude 가 전체 HTML 을 재작성.
        if spec.get("format") == "html":
            if not message or not (spec.get("html") or "").strip():
                cr.update(status="error", answer="수정할 내용이 없습니다.", intent="chat")
                _set_chat_result(session, job, cr)
                return
            try:
                # 보안 정책: 즉시수정도 외부 Claude 대신 내부 Qwen 으로 처리(본문/파일이 외부로
                # 안 나가게). 로고 등 base64 data URI 는 placeholder 로 빼서 토큰 급감 + 손상 방지.
                stripped_html, _uris = _strip_data_uris(spec["html"])
                sys_p, user_p = prompts.build_brandlogy_html_edit_prompt(
                    stripped_html, message, history
                )
                # HTML 원문 출력 필요 → json_mode 끄고 presence_penalty 0(HTML 토큰 반복 허용).
                raw_edit = _call_freeform_llm(
                    session,
                    job,
                    [{"role": "system", "content": sys_p}, {"role": "user", "content": user_p}],
                    temperature=0.3,
                    max_tokens=12000,
                    json_mode=False,
                    presence_penalty=0.0,
                )
                new_html = _restore_data_uris(_extract_html(raw_edit), _uris)
                # 구조 검증: 실제 슬라이드(<section>)가 있고, 본문이 크게 잘려나가지
                # 않았는지 확인한다. 단순히 "slide" 문자열만 보면 CSS/산문 답변도
                # 통과해 덱을 빈/깨진 상태로 덮어쓴다.
                prev_html = spec.get("html") or ""
                new_sections = new_html.count("<section")
                accepted = new_sections >= 1 and len(new_html) >= max(
                    200, int(len(prev_html) * 0.4)
                )
                if accepted:
                    spec = {**spec, "html": new_html}
                    job.slides_spec = spec
                    job.pptx_key = None  # 편집됐으니 기존 .pptx 무효화
                    cr.update(
                        status="done",
                        answer="수정을 반영했어요.",
                        intent="edit",
                        refreshed_slide_index=None,
                    )
                else:
                    cr.update(
                        status="done",
                        answer="수정 결과를 적용하지 못했어요. 다시 말씀해 주세요.",
                        intent="chat",
                    )
                _set_chat_result(session, job, cr)
            except Exception:  # noqa: BLE001
                logger.exception("ppt_generator.chat_edit(html) 실패 (job=%s)", job_id)
                _set_chat_result(session, job, _chat_edit_error_result(cr))
            return

        if not message or not slides:
            cr.update(status="error", answer="수정할 내용이 없습니다.", intent="chat")
            _set_chat_result(session, job, cr)
            return

        try:
            msgs = prompts.build_chat_edit_messages(slides, message, history, family_key)
            raw = _call_llm(session, job, msgs, temperature=0.4, max_tokens=4096)
            resp = parsing.parse_chat_edit_json(raw)

            intent = resp.get("intent") or "chat"
            answer = resp.get("answer") or "응답을 받았습니다."
            refreshed: int | None = None

            if intent == "edit":
                try:
                    slide_idx = int(resp.get("slide_index"))
                except (TypeError, ValueError):
                    slide_idx = None
                new_layout = resp.get("layout")
                new_data = resp.get("data") or {}
                if (
                    slide_idx
                    and 1 <= slide_idx <= len(slides)
                    and new_layout in valid_layouts
                    and isinstance(new_data, dict)
                ):
                    slides[slide_idx - 1] = {"layout": new_layout, "data": new_data}
                    job.slides_spec = {"family": family_key, "slides": slides}
                    # slides_spec 만 갱신 — 프론트가 갱신된 spec 으로 해당 슬라이드 HTML 을
                    # 재렌더한다. (.pptx/PNG 재빌드는 'PPT로 전환' 단계로 미룸)
                    # 편집으로 기존 .pptx 는 더 이상 최신이 아니므로 다운로드 게이트(pptx_key)를
                    # 닫는다 — 서버측 pptx_ready 가 옛 덱을 가리킨 채 true 로 남지 않도록.
                    job.pptx_key = None
                    refreshed = slide_idx
                else:
                    intent = "chat"
                    answer = answer or (
                        "수정할 슬라이드 정보가 부족해요. 슬라이드 번호와 변경 내용을 함께 말씀해주세요."
                    )

            cr.update(
                status="done",
                answer=answer,
                intent=intent,
                refreshed_slide_index=refreshed,
            )
            _set_chat_result(session, job, cr)
        except Exception:  # noqa: BLE001
            logger.exception("ppt_generator.chat_edit 실패 (job=%s)", job_id)
            _set_chat_result(session, job, _chat_edit_error_result(cr))


def _spec_as_dict(job: PptJob) -> dict:
    """job.slides_spec 을 dict 로(문자열이면 파싱). 실패 시 {}."""
    import json as _json

    spec = job.slides_spec
    if isinstance(spec, str):
        try:
            spec = _json.loads(spec)
        except Exception:  # noqa: BLE001
            return {}
    return spec if isinstance(spec, dict) else {}


def _house_embeds(job: PptJob) -> list[dict]:
    """house 똑딱이 임베드 덱 목록 house_embeds[i] = {"slides": [...]} (아이콘 idx 로 매칭)."""
    embeds = _spec_as_dict(job).get("house_embeds")
    return [e for e in embeds if isinstance(e, dict)] if isinstance(embeds, list) else []


def _walk_ole_markers(node, found: list[dict]) -> None:
    """블록 트리(중첩 row 포함)를 훑어 'ole' 마커({"src","idx"}) 를 모은다."""
    if isinstance(node, dict):
        ole = node.get("ole")
        if isinstance(ole, dict) and isinstance(ole.get("idx"), int) and ole.get("src"):
            found.append(ole)
        for v in node.values():
            _walk_ole_markers(v, found)
    elif isinstance(node, list):
        for v in node:
            _walk_ole_markers(v, found)


def _collect_house_ole(job: PptJob) -> list[tuple[int, int, str]]:
    """[(슬라이드 인덱스, 임베드 idx, 아이콘 data-URI)] — 빌드된 pptx 의 슬라이드별 똑딱이 마커.

    spec.slides 순서 == 빌드된 .pptx 슬라이드 순서(표지 포함)라 인덱스를 그대로 쓴다.
    섹션 똑딱이는 블록의 'ole' 마커, 우하단 catch-all 은 data.ole_icon 으로 표현된다.
    """
    out: list[tuple[int, int, str]] = []
    for i, s in enumerate(_spec_as_dict(job).get("slides") or []):
        if not isinstance(s, dict):
            continue
        data = s.get("data") if isinstance(s.get("data"), dict) else {}
        oi = data.get("ole_icon")
        if isinstance(oi, dict) and isinstance(oi.get("idx"), int) and oi.get("src"):
            out.append((i, int(oi["idx"]), str(oi["src"])))
        markers: list[dict] = []
        _walk_ole_markers(data.get("blocks"), markers)
        for m in markers:
            out.append((i, int(m["idx"]), str(m["src"])))
    return out


def _build_result_report_pptx(job: PptJob, params: dict) -> bytes:
    """똑딱이로 임베드할 '교육 결과 보고서' 덱(.pptx) 바이트 생성.

    generate 가 저장해 둔 result_spec(표지+목차+본문) 이 있으면 두원 pptx 로 변환해 반환.
    없으면(항목 없음·생성 실패) placeholder 덱으로 폴백.
    """
    import json as _json

    key = f"{ppt_service.job_prefix(job.workspace_id, job.id)}/embed/result_spec.json"
    raw = ppt_service.fetch_object_bytes(key)
    if raw:
        try:
            spec = _json.loads(raw.decode("utf-8"))
            from ai_do_api.domains.ppt_generator.design.html_to_pptx import (
                doowon_deck_to_pptx_bytes,
            )

            _, fam = resolve_family(job.family)
            return doowon_deck_to_pptx_bytes(
                spec.get("cover") or {},
                spec.get("sections") or [],
                spec.get("body_style") or "",
                logo_path=fam.get("logo_path"),
                body_w_px=1244,
                body_h_px=754,
            )
        except Exception as e:  # noqa: BLE001
            logger.info("ppt_generator %s 결과보고서 덱 변환 실패 → placeholder: %s", job.id, e)

    from pptx import Presentation
    from pptx.util import Pt

    topic = (params.get("topic") or "").strip()
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])  # title only
    slide.shapes.title.text = "교육 결과 보고서"
    tb = slide.shapes.add_textbox(
        prs.slide_width // 12,
        prs.slide_height // 3,
        prs.slide_width * 5 // 6,
        prs.slide_height // 2,
    )
    tf = tb.text_frame
    tf.word_wrap = True
    tf.text = topic or "교육 결과 상세 보고서"
    tf.paragraphs[0].font.size = Pt(20)
    p = tf.add_paragraph()
    p.text = "※ 결과보고서 상세 양식 준비 중 — 본 페이지는 임시 placeholder 입니다."
    p.font.size = Pt(12)
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _maybe_embed_ole(job: PptJob, pptx_bytes: bytes) -> bytes:
    """교육 보고서의 똑딱이 아이콘 자리에 결과보고서 덱을 OLE 로 임베드.

    임베드 대상 = 첨부 .pptx(있으면) > 자동 생성 결과보고서 덱. 아이콘 그림(MinIO 보관)과
    같은 바이트의 그림을 본문 슬라이드(인덱스 1)에서 찾아 그 자리에 OLE 개체로 주입.
    교육 보고서가 아니고 첨부도 없으면 건드리지 않음. 실패 시 원본 그대로.
    """
    params = job.params or {}
    _, fam = resolve_family(job.family)
    embed = params.get("embed_pptx") or {}
    has_attach = bool(embed.get("key"))

    # house(TEST) 똑딱이: 섹션 제목 옆·우하단의 여러 아이콘 자리에 각자의 상세본 덱을 OLE 로 주입한다.
    if fam.get("design") == "house":
        embeds = _house_embeds(job)
        markers = _collect_house_ole(job)
        if not embeds or not markers:
            return pptx_bytes  # 똑딱이 없음(넘침 0) → 손대지 않음
        # 임베드 idx → 상세본 .pptx 바이트(캐시). 슬라이드별로 묶어 한 번에 주입.
        deck_cache: dict[int, bytes | None] = {}
        by_slide: dict[int, list[dict]] = {}
        for slide_index, eidx, src in markers:
            if eidx < 0 or eidx >= len(embeds):
                continue
            if eidx not in deck_cache:
                dslides = embeds[eidx].get("slides") or []
                try:
                    deck_cache[eidx] = _build_pptx_bytes(job.family, dslides) if dslides else None
                except Exception as e:  # noqa: BLE001
                    logger.info(
                        "ppt_generator %s house 상세본 덱(idx=%d) 빌드 실패: %s", job.id, eidx, e
                    )
                    deck_cache[eidx] = None
            embed_bytes = deck_cache[eidx]
            if not embed_bytes:
                continue
            try:
                icon_bytes = base64.b64decode(src.split(",", 1)[1])
            except Exception:  # noqa: BLE001
                continue
            by_slide.setdefault(slide_index, []).append(
                {
                    "icon_bytes": icon_bytes,
                    "embed_bytes": embed_bytes,
                    "name": "상세 보기",
                    # builders_house 가 add_picture 에 붙인 shape 이름과 동일 — 1순위 매칭 키.
                    "name_tag": f"ole-icon-{eidx}",
                }
            )
        for slide_index, items in by_slide.items():
            try:
                pptx_bytes = ole.inject_multiple_ole_into_pptx(
                    pptx_bytes, items, slide_index=slide_index
                )
            except Exception as e:  # noqa: BLE001
                logger.info("ppt_generator %s house 똑딱이 다중 OLE 임베드 실패: %s", job.id, e)
        return pptx_bytes

    # 세미나 & 출장 보고서: 첫 본문 페이지 비고칸 아이콘 자리에 (접은 출장 일정 또는 첨부 시트) 덱을 OLE 로.
    if fam.get("design") == "doowon-seminar":
        has_sched = bool(params.get("schedule_images") or [])
        has_trip = bool(params.get("fold_trip")) and not has_sched
        if not (has_sched or has_trip):
            return pptx_bytes
        prefix = ppt_service.job_prefix(job.workspace_id, job.id)
        if has_trip:
            # 접은 출장 일정: spec 생성 때 렌더해 저장한 덱을 재사용(없으면 재빌드).
            embed_bytes = ppt_service.fetch_object_bytes(
                f"{prefix}/embed/seminar_ole.pptx"
            ) or _build_seminar_ole_pptx(job)
        else:
            embed_bytes = _build_schedule_ole_pptx(job)
        if not embed_bytes:
            return pptx_bytes
        icon_bytes = ppt_service.fetch_object_bytes(f"{prefix}/embed/icon.png")
        if not icon_bytes:
            return pptx_bytes
        name = "출장 일정" if has_trip else "첨부 일정표"
        try:
            return ole.inject_ole_into_pptx(
                pptx_bytes, embed_bytes, icon_bytes, slide_index=1, name=name
            )
        except Exception as e:  # noqa: BLE001
            logger.info("ppt_generator %s 세미나 똑딱이 OLE 임베드 실패: %s", job.id, e)
            return pptx_bytes

    if fam.get("design") != "doowon-education" and not has_attach:
        return pptx_bytes

    if has_attach:
        embed_bytes = ppt_service.fetch_object_bytes(embed["key"])
    else:
        try:
            embed_bytes = _build_result_report_pptx(job, params)
        except Exception as e:  # noqa: BLE001
            logger.info("ppt_generator %s 결과보고서 덱 생성 실패: %s", job.id, e)
            return pptx_bytes
    if not embed_bytes:
        return pptx_bytes

    prefix = ppt_service.job_prefix(job.workspace_id, job.id)
    icon_bytes = ppt_service.fetch_object_bytes(f"{prefix}/embed/icon.png")
    if not icon_bytes:
        return pptx_bytes
    try:
        return ole.inject_ole_into_pptx(
            pptx_bytes,
            embed_bytes,
            icon_bytes,
            slide_index=1,
            name=embed.get("filename") or "교육 결과 보고서",
        )
    except Exception as e:  # noqa: BLE001
        logger.info("ppt_generator %s 똑딱이 OLE 임베드 실패: %s", job.id, e)
        return pptx_bytes


# ============================================================
# 태스크: PPT 전환 (finalize) — slides_spec → .pptx 빌드/업로드
# ============================================================
@celery_app.task(name="ppt_generator.finalize", bind=True)
def finalize(self, job_id: str) -> None:
    with _db_session_scope() as session:
        job = session.get(PptJob, job_id)
        if job is None:
            return
        spec = job.slides_spec or {}
        is_html = spec.get("format") == "html"
        slides = list(spec.get("slides") or [])
        family_key, _fam = resolve_family(job.family)
        if not is_html and not slides:
            _set(session, job, error="변환할 슬라이드가 없습니다.", message="변환 실패")
            raise RuntimeError("변환할 슬라이드가 없습니다.")
        if is_html and not (spec.get("html") or "").strip():
            _set(session, job, error="변환할 HTML이 없습니다.", message="변환 실패")
            raise RuntimeError("변환할 HTML이 없습니다.")
        try:
            # status 는 'completed' 유지 — pptx_key 가 채워지면 프론트가 다운로드를 연다.
            # 실패 시 error 만 채워지고 status 는 completed 이므로 finalize 오류로 구분된다.
            # 재시도(또는 코드 갱신 후 재변환) 시 이전 실패의 error 가 남아 UI 에 오류로 보이지
            # 않도록, 변환 시작 시 stale error 를 먼저 비운다.
            _set(session, job, error=None, message="PPT 변환 중...")
            if is_html and spec.get("chrome") == "doowon":
                # 두원 양식: 표지/본문 틀은 네이티브(builders_a4), 본문만 변환해 칸에 끼움.
                w_cm = spec.get("slide_w_cm") or 27.517
                h_cm = spec.get("slide_h_cm") or 19.05
                logo = _fam.get("logo_path")
                try:
                    from ai_do_api.domains.ppt_generator.design.html_to_pptx import (
                        doowon_deck_to_pptx_bytes,
                    )

                    pptx_bytes = doowon_deck_to_pptx_bytes(
                        spec.get("cover") or {},
                        spec.get("body") or [],
                        spec.get("body_style") or "",
                        logo_path=logo,
                        body_w_px=spec.get("body_w") or 1244,
                        body_h_px=spec.get("body_h") or 754,
                    )
                except Exception:
                    logger.exception(
                        "ppt_generator.finalize 두원 네이티브 변환 실패 → 이미지 폴백 (job=%s)",
                        job_id,
                    )
                    pptx_bytes = _html_deck_to_pptx_bytes(
                        spec["html"],
                        spec.get("slide_w") or 1321,
                        spec.get("slide_h") or 914,
                        slide_w_cm=w_cm,
                        slide_h_cm=h_cm,
                    )
            elif is_html:
                w = spec.get("slide_w") or 1280
                h = spec.get("slide_h") or 794
                w_cm = spec.get("slide_w_cm") or 27.0
                h_cm = spec.get("slide_h_cm") or 16.75
                # 편집형(텍스트박스/도형) 변환 우선. 실패하면 이미지-only 변환으로 폴백해
                # 다운로드가 어떤 경우에도 가능하도록 한다.
                try:
                    from ai_do_api.domains.ppt_generator.design.html_to_pptx import (
                        html_deck_to_editable_pptx_bytes,
                    )

                    pptx_bytes = html_deck_to_editable_pptx_bytes(
                        spec["html"], w, h, slide_w_cm=w_cm, slide_h_cm=h_cm
                    )
                except Exception:
                    logger.exception(
                        "ppt_generator.finalize 편집형 변환 실패 → 이미지 폴백 (job=%s)", job_id
                    )
                    pptx_bytes = _html_deck_to_pptx_bytes(
                        spec["html"], w, h, slide_w_cm=w_cm, slide_h_cm=h_cm
                    )
            else:
                pptx_bytes = _build_pptx_bytes(family_key, slides)
            # '똑딱이'(OLE) 임베드 — 모든 변환 분기 공통. house 넘침 상세본·교육 결과보고서·
            # 첨부 .pptx 를 아이콘 자리에 OLE 로 주입한다(대상 없으면 _maybe_embed_ole 가 그대로 반환).
            pptx_bytes = _maybe_embed_ole(job, pptx_bytes)
            pptx_key = _upload_pptx(job, pptx_bytes)
            _set(session, job, pptx_key=pptx_key, error=None, message="변환 완료")
        except Exception:  # noqa: BLE001
            logger.exception("ppt_generator.finalize 실패 (job=%s)", job_id)
            # 내부 예외 원문은 로그에만. 사용자에겐 일반화된 메시지만 노출.
            _set(session, job, error="PPT 변환 중 오류가 발생했습니다.", message="변환 실패")
            raise
