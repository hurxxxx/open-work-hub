"""AI 추천 산업 리포트 큐레이션.

수집된 산업 리포트(자동차연구원 파일·오토저널·KDI)를 사내 LLM으로 회사 프로필
기준 분류해 관련 있는 것만 ``IndustryReportRecommended(origin='ai')`` 로 추천한다.
회사 프로필·LLM 태스크·판정 파서는 뉴스 AI 추천(``news.ai_curator``)과 공유한다.

LLM 풀 부트스트랩이 보장된 API 프로세스에서만 호출한다.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_alm_api.core.llm import LlmTaskContext
from open_alm_api.domains.ai.gateway import LlmWorkloadContext, execute_llm
from open_alm_api.domains.news import ai_curator as news_curator
from open_alm_api.domains.news import config_data as news_cfg

from . import config_data as cfg
from . import service
from .models import IndustryReportFile, IndustryReportItem

logger = logging.getLogger(__name__)

TASK_KIND = "news_curate"  # 동일 분류 작업 — 별도 예산 불필요(뉴스와 공유)


def _candidates(db: Session, limit: int) -> list[dict[str, Any]]:
    """아직 저장(수동/AI)되지 않은 리포트 후보 — 최신순, 채널 균형."""
    refs = service.recommended_refs(db) | service.ai_evaluated_report_refs(db)
    out: list[dict[str, Any]] = []
    # 자동차연구원/오토저널/KDI crawled items
    items = db.scalars(
        select(IndustryReportItem).order_by(IndustryReportItem.collected_at.desc()).limit(limit)
    )
    for it in items:
        ref = service.content_ref(it.source, url=it.url)
        if ref in refs:
            continue
        out.append(
            {
                "ref": ref,
                "kind": it.source,
                "title": it.title,
                "org": it.org,
                "published_date": it.published_date,
                "url": it.url,
                "file_id": None,
            }
        )
    # 자동차연구원(KATECH) 첨부 파일
    files = db.scalars(
        select(IndustryReportFile).order_by(IndustryReportFile.created_at.desc()).limit(limit)
    )
    for f in files:
        ref = service.content_ref("trend", file_id=f.id)
        if ref in refs:
            continue
        out.append(
            {
                "ref": ref,
                "kind": "trend",
                "title": f.title,
                "org": cfg.COMPANY_MAP.get(f.company, f.company),
                "published_date": f.published_date,
                "url": "",
                "file_id": f.id,
            }
        )
    return out[:limit]


def _build_prompt(profile: str, batch: list[dict[str, Any]]) -> str:
    lines = [
        "당신은 제조사의 산업 리포트 큐레이터입니다. 아래 [회사 프로필] 기준으로 "
        "[리포트 목록]의 각 항목이 회사와 관련 있는지 판단하세요.",
        "",
        "[회사 프로필]",
        profile.strip(),
        "",
        "[판단 규칙]",
        "1) 관련 사유는 정확히: 유사제품 / 기술내용 / 경쟁사 중 하나.",
        "2) 회사 아이템(자동차 공조·열관리·전동화)과 무관한 일반 경제/정책 리포트는 관련 없음.",
        "3) 애매하면 보수적으로 관련 없음(relevant=false).",
        "",
        "[리포트 목록]",
    ]
    for i, r in enumerate(batch):
        lines.append(
            f"{i}. [{r['kind']}] {r['title']} (출처: {r.get('org') or '미상'}, {r.get('published_date') or ''})"
        )
    lines += [
        "",
        "[출력 형식] 설명 없이 JSON 배열만:",
        '{"index": <번호>, "relevant": <true|false>, "reason": "<유사제품|기술내용|경쟁사|>", "detail": "<한 줄, 없으면 \\"\\">"}',
    ]
    return "\n".join(lines)


def curate_recent(
    db: Session,
    *,
    actor_user_id: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    profile = news_curator.get_ai_profile(db)
    candidates = _candidates(db, limit)
    if not candidates:
        return {"evaluated": 0, "saved": 0, "by_reason": {}, "error": None}

    context = LlmTaskContext(
        source="api.report_curate",
        workspace_id="system",
        task_kind=TASK_KIND,
        app_id="news",
        actor_user_id=actor_user_id,
        principal_kind="user" if actor_user_id else "system",
        principal_id=actor_user_id or "report-curator",
    )
    batch_size = max(1, news_cfg.AI_CURATE_BATCH_SIZE)
    by_reason: dict[str, int] = {}
    saved = 0
    evaluated = 0
    error: str | None = None
    for start in range(0, len(candidates), batch_size):
        batch = candidates[start : start + batch_size]
        prompt = _build_prompt(profile, batch)
        try:
            result = execute_llm(
                TASK_KIND,
                LlmWorkloadContext.from_task_context(context),
                db,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
            )
            content = result.completion.text
        except Exception as err:  # noqa: BLE001
            logger.exception("report_curate: LLM 호출 실패(batch @%d)", start)
            error = str(err)
            break

        verdicts = news_curator._parse_verdicts(content)
        if not verdicts:
            logger.warning("report_curate: LLM verdict missing or empty(batch @%d)", start)
            error = "invalid_verdicts"
            break

        relevant_by_index: dict[int, tuple[str, str]] = {}
        for v in verdicts:
            if not isinstance(v, dict) or not v.get("relevant"):
                continue
            try:
                idx = int(v.get("index"))
            except (TypeError, ValueError):
                continue
            if idx < 0 or idx >= len(batch):
                continue
            reason = str(v.get("reason") or "").strip()
            if reason not in news_cfg.AI_CURATE_REASONS:
                continue
            relevant_by_index[idx] = (reason, str(v.get("detail") or "").strip())

        for idx, c in enumerate(batch):
            verdict = relevant_by_index.get(idx)
            if verdict is None:
                service.record_ai_report_evaluation(
                    db,
                    kind=c["kind"],
                    url=c.get("url", "") or "",
                    file_id=c.get("file_id"),
                    relevant=False,
                )
                continue
            reason, reason_detail = verdict
            service.recommend_report(
                db,
                kind=c["kind"],
                title=c["title"],
                org=c.get("org", "") or "",
                published_date=c.get("published_date", "") or "",
                url=c.get("url", "") or "",
                file_id=c.get("file_id"),
                company="",
                user_id=None,
                origin="ai",
                reason=reason,
                reason_detail=reason_detail,
            )
            service.record_ai_report_evaluation(
                db,
                kind=c["kind"],
                url=c.get("url", "") or "",
                file_id=c.get("file_id"),
                relevant=True,
                reason=reason,
                reason_detail=reason_detail,
            )
            saved += 1
            by_reason[reason] = by_reason.get(reason, 0) + 1
        evaluated += len(batch)

    logger.info("report_curate done: evaluated=%d saved=%d %s", evaluated, saved, by_reason)
    return {"evaluated": evaluated, "saved": saved, "by_reason": by_reason, "error": error}
