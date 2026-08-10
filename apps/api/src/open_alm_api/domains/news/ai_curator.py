"""AI 뉴스 큐레이션.

수집된 기사(``NewsArticle``) 중 회사 프로필과 관련 있는 것만 사내 LLM(Qwen3)으로
골라 ``NewsRecommendedArticle(origin='ai')`` 로 추천한다. "유사제품 / 기술내용 / 경쟁사"
세 사유로 분류하고, 주가·시황 등 금융 정보와 무관 기사는 제외한다.

LLM 풀 설정·생성 프로필은 ``create_app`` 부트스트랩에서만 등록되므로, 이 모듈은
풀 부트스트랩이 보장된 **API 프로세스**에서만 호출한다(수집 워커에서 호출 금지).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from open_alm_api.core.llm import LlmTaskContext
from open_alm_api.domains.ai.gateway import LlmWorkloadContext, execute_llm
from open_alm_api.domains.auth.models import utcnow_naive

from . import config_data as cfg
from . import service
from .models import NewsArticle, NewsFilterSetting, NewsRecommendedArticle

logger = logging.getLogger(__name__)

TASK_KIND = "news_curate"
_SETTINGS_ID = "singleton"
_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)
_CURATION_CHANNELS = ("keyword", "car", "front")


# ── 프로필 설정 ───────────────────────────────────────────────
def get_ai_profile(db: Session) -> str:
    """현재 큐레이션 프로필(없으면 기본 Open ALM 프로필)."""
    row = service.get_or_create_filter_settings(db)
    return (row.ai_profile or "").strip() or cfg.DEFAULT_AI_PROFILE


def update_ai_profile(
    db: Session,
    *,
    ai_profile: str | None = None,
    ai_curate_enabled: bool | None = None,
) -> dict[str, Any]:
    row = service.get_or_create_filter_settings(db)
    old_profile = (row.ai_profile or "").strip() or cfg.DEFAULT_AI_PROFILE
    profile_changed = False
    if ai_profile is not None:
        next_raw_profile = ai_profile.strip()
        next_profile = next_raw_profile or cfg.DEFAULT_AI_PROFILE
        profile_changed = next_profile != old_profile
        row.ai_profile = next_raw_profile
    if ai_curate_enabled is not None:
        row.ai_curate_enabled = bool(ai_curate_enabled)
    if profile_changed:
        _reset_ai_curation_state(db, row)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _settings_payload(row)


def _reset_ai_curation_state(db: Session, row: NewsFilterSetting) -> None:
    """회사 프로필 변경 시 기존 AI 판단을 폐기해 새 기준으로 다시 평가한다."""
    db.execute(update(NewsArticle).values(ai_evaluated=False))
    db.execute(delete(NewsRecommendedArticle).where(NewsRecommendedArticle.origin == "ai"))
    row.ai_curated_at = None

    # 산업 리포트 AI 추천도 같은 회사 프로필을 공유한다.
    from open_alm_api.domains.industry_report import service as report_service

    report_service.reset_ai_report_evaluations(db)


def _settings_payload(row: NewsFilterSetting) -> dict[str, Any]:
    return {
        "ai_profile": (row.ai_profile or "").strip() or cfg.DEFAULT_AI_PROFILE,
        "ai_profile_is_default": not (row.ai_profile or "").strip(),
        "ai_curate_enabled": bool(row.ai_curate_enabled),
        "ai_curated_at": (
            row.ai_curated_at.strftime("%Y-%m-%d %H:%M") if row.ai_curated_at else None
        ),
    }


def get_settings_payload(db: Session) -> dict[str, Any]:
    return _settings_payload(service.get_or_create_filter_settings(db))


# ── Staleness ─────────────────────────────────────────────────
def needs_curation(db: Session) -> bool:
    """아직 AI가 평가하지 않은 수집 기사가 있으면 True(수집 14일치 전체 대상)."""
    row = service.get_or_create_filter_settings(db)
    if not row.ai_curate_enabled:
        return False
    pending = db.scalar(
        select(NewsArticle.id)
        .where(
            NewsArticle.channel.in_(_CURATION_CHANNELS),
            NewsArticle.ai_evaluated.is_(False),
        )
        .limit(1)
    )
    return pending is not None


# ── 큐레이션 ──────────────────────────────────────────────────
def _unevaluated_articles(db: Session, limit: int) -> list[NewsArticle]:
    """아직 평가하지 않은(ai_evaluated=False) 수집 기사를 채널 균형 있게 뽑는다.

    날짜순으로만 뽑으면 오늘자 신문사(front) 기사가 상위를 점유해 정작 관련성 높은
    keyword/car 채널이 밀려난다. 채널별로 미평가 기사를 모아 keyword→car→front
    라운드로빈으로 섞어 ``limit`` 까지 채운다. 수집은 14일치만 보관되므로 결과는
    "지금 DB에 있는 14일치 중 미평가분" 전체가 된다.
    """
    recommended_urls = service.recommended_urls(db)

    per_channel: dict[str, list[NewsArticle]] = {}
    seen: set[str] = set()
    for channel in _CURATION_CHANNELS:
        rows = db.scalars(
            select(NewsArticle)
            .where(
                NewsArticle.channel == channel,
                NewsArticle.ai_evaluated.is_(False),
            )
            .order_by(
                NewsArticle.published_date.desc(),
                NewsArticle.collected_at.desc(),
            )
            .limit(limit)
        )
        bucket: list[NewsArticle] = []
        for r in rows:
            url = (r.original_url or "").strip()
            if not url or url in recommended_urls or url in seen:
                continue
            seen.add(url)
            bucket.append(r)
        per_channel[channel] = bucket

    out: list[NewsArticle] = []
    idx = 0
    while len(out) < limit and any(idx < len(b) for b in per_channel.values()):
        for channel in _CURATION_CHANNELS:
            bucket = per_channel[channel]
            if idx < len(bucket):
                out.append(bucket[idx])
                if len(out) >= limit:
                    break
        idx += 1
    return out


def _build_prompt(profile: str, articles: list[NewsArticle]) -> str:
    lines = [
        "당신은 제조사의 산업 뉴스 큐레이터입니다. 아래 [회사 프로필] 기준으로 "
        "[기사 목록]의 각 기사가 회사와 관련 있는지 판단하세요.",
        "",
        "[회사 프로필]",
        profile.strip(),
        "",
        "[판단 규칙] — 아래 제외 규칙이 관련 규칙보다 우선한다.",
        "1) 제외(무조건 relevant=false): 주가·주식·증시·시황·목표주가·투자의견·공시·"
        "실적발표·증권 리포트 등 금융/투자 기사. 경쟁사가 언급돼도 주가/금융 기사면 제외.",
        "2) 제외: 정치·사회·스포츠·세금 등 분야가 다른 일반 뉴스. 그리고 기술/제품 실체가 없는 "
        "마케팅성 기사 — 시승·체험·구독·할인·행사·서비스센터 개소·무상점검/정비 서비스·"
        "단순 판매량/실적 홍보 등은 제외.",
        "3) 위 제외에 해당하지 않을 때만 관련 사유를 부여: 정확히 유사제품 / 기술내용 / 경쟁사 중 하나.",
        "   - 유사제품: 컴프레서·열교환기·열관리/공조 모듈 등 회사 아이템과 같거나 유사한 부품·시스템 제품.",
        "   - 기술내용: 자동차 공조·열관리·전동화의 실질적 기술/연구/특허/부품·공급망 동향"
        "(전기차/배터리 열관리·냉각, 히트펌프 등 회사가 부품을 공급하는 분야 포함). "
        "단순 완성차 판매/마케팅 소식은 제외하고, 기술·부품·공급망 실체가 있을 때만.",
        "   - 경쟁사: 경쟁사의 수주·신제품·기술·투자·협력·인사 등 '사업' 동향(주가 제외).",
        "- 기술·제품 실체가 있고 위 프로필 분야에 실질적으로 닿을 때만 관련 있음으로 본다.",
        "",
        "[기사 목록]",
    ]
    for i, a in enumerate(articles):
        lines.append(
            f"{i}. [{a.channel}] {a.title} (출처: {a.source or '미상'}, {a.published_date})"
        )
    lines += [
        "",
        "[출력 형식] 다른 설명 없이 JSON 배열만 출력하세요. 각 원소:",
        '{"index": <기사번호>, "relevant": <true|false>, '
        '"reason": "<유사제품|기술내용|경쟁사|>", "detail": "<관련 이유 한 줄, 없으면 빈 문자열>"}',
        '관련 없는 기사는 relevant=false, reason="" 로 표기하세요.',
    ]
    return "\n".join(lines)


def _parse_verdicts(content: str) -> list[dict[str, Any]]:
    if not content:
        return []
    match = _JSON_ARRAY_RE.search(content)
    raw = match.group(0) if match else content
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        logger.warning("news_curate: LLM 응답 JSON 파싱 실패")
        return []
    return data if isinstance(data, list) else []


def curate_recent(
    db: Session,
    *,
    actor_user_id: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """최근 수집 기사를 LLM으로 분류해 관련 기사만 AI 추천으로 저장.

    반환: ``{"evaluated", "saved", "by_reason", "error"}``.
    LLM/네트워크 오류는 예외를 던지지 않고 ``error`` 로 보고한다(수집·UI 흐름 보호).
    """
    limit = limit or cfg.AI_CURATE_MAX_ARTICLES
    profile = get_ai_profile(db)
    articles = _unevaluated_articles(db, limit)
    if not articles:
        _stamp_curated(db)
        return {"evaluated": 0, "saved": 0, "by_reason": {}, "error": None}

    context = LlmTaskContext(
        source="api.news_curate",
        workspace_id="system",
        task_kind=TASK_KIND,
        app_id="news",
        actor_user_id=actor_user_id,
        principal_kind="user" if actor_user_id else "system",
        principal_id=actor_user_id or "news-curator",
    )

    # 14일치 전체를 작은 배치로 나눠 평가(로컬 모델 정확도/토큰 고려). 한 번 평가한
    # 기사는 ai_evaluated 로 표시해 다음 실행에서 건너뛴다.
    batch_size = max(1, cfg.AI_CURATE_BATCH_SIZE)
    by_reason: dict[str, int] = {}
    saved = 0
    evaluated = 0
    error: str | None = None
    for start in range(0, len(articles), batch_size):
        batch = articles[start : start + batch_size]
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
        except Exception as err:  # noqa: BLE001 - LLM/네트워크 best-effort
            logger.exception("news_curate: LLM 호출 실패(batch @%d)", start)
            error = str(err)
            break  # 실패 배치 이후는 평가 미표시 → 다음 실행에서 재시도

        verdicts = _parse_verdicts(content)
        if not verdicts:
            logger.warning("news_curate: LLM verdict missing or empty(batch @%d)", start)
            error = "invalid_verdicts"
            break

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
            if reason not in cfg.AI_CURATE_REASONS:
                continue
            art = batch[idx]
            service.recommend_article(
                db,
                channel=art.channel,
                keyword=art.keyword,
                source=art.source,
                title=art.title,
                summary=art.summary,
                original_url=art.original_url,
                published_date=art.published_date,
                user_id=None,
                origin="ai",
                reason=reason,
                reason_detail=str(v.get("detail") or "").strip(),
            )
            saved += 1
            by_reason[reason] = by_reason.get(reason, 0) + 1

        # 배치 전체를 평가 완료로 표시(저장 여부와 무관).
        for art in batch:
            art.ai_evaluated = True
            db.add(art)
        db.commit()
        evaluated += len(batch)

    pruned = _prune_old_ai_recommended(db)
    _stamp_curated(db)
    logger.info(
        "news_curate done: evaluated=%d saved=%d pruned=%d %s",
        evaluated,
        saved,
        pruned,
        by_reason,
    )
    return {"evaluated": evaluated, "saved": saved, "by_reason": by_reason, "error": error}


def _prune_old_ai_recommended(db: Session) -> int:
    """발행일 기준 보관 기간(1년)을 넘긴 AI 추천 기사 정리(수동 저장은 제외)."""
    cutoff = (datetime.now() - timedelta(days=cfg.AI_SAVED_RETENTION_DAYS)).strftime("%Y-%m-%d")
    result = db.execute(
        delete(NewsRecommendedArticle).where(
            NewsRecommendedArticle.origin == "ai",
            NewsRecommendedArticle.published_date != "",
            NewsRecommendedArticle.published_date < cutoff,
        )
    )
    db.commit()
    return result.rowcount or 0


def _stamp_curated(db: Session) -> None:
    row = service.get_or_create_filter_settings(db)
    row.ai_curated_at = utcnow_naive()
    db.add(row)
    db.commit()
