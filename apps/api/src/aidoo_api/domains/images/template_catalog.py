from __future__ import annotations

from dataclasses import dataclass


USER_TEMPLATE_PREFIX = "user_template:"


@dataclass(frozen=True)
class BuiltinImageTemplate:
    id: str
    label: str
    asset_path: str
    guidance: str


_GUIDANCE: dict[str, tuple[str, str]] = {
    "meeting_deck_title": (
        "Deck title slide",
        "A polished executive cover slide with a strong title area, restrained subtitle lines, and one confident visual panel.",
    ),
    "meeting_deck_kpi": (
        "KPI slide",
        "A premium four-metric slide with card-based KPIs, crisp hierarchy, and executive presentation polish.",
    ),
    "meeting_deck_compare": (
        "Comparison slide",
        "A before/after or option A/B comparison slide with two balanced panels and clear contrast.",
    ),
    "team_intro": (
        "Team intro",
        "A refined team slide with four profile cards, consistent portrait placeholders, roles, and tidy spacing.",
    ),
    "deck_section_divider": (
        "Section divider",
        "A dramatic but minimal section divider slide with a single focal title and generous negative space.",
    ),
    "status_report": (
        "Status report",
        "A one-page status report with summary cards, progress blocks, and a calm business-report rhythm.",
    ),
    "kpi_dashboard": (
        "KPI dashboard",
        "A high-end dashboard view with metric cards, a trend chart, and dense but readable analytics layout.",
    ),
    "post_mortem": (
        "Post-mortem",
        "A structured post-mortem report with WHAT, WHY, and NEXT columns plus a concise evidence area.",
    ),
    "weekly_brief": (
        "Weekly brief",
        "An editorial weekly brief page with dated header, three priority items, and a clean reading flow.",
    ),
    "process_flow": (
        "Process flow",
        "A modern process diagram with sequential steps, directional connectors, and strong visual rhythm.",
    ),
    "swimlane": (
        "Swimlane",
        "A swimlane process diagram with role rows, phase columns, and clear cross-functional handoffs.",
    ),
    "org_chart": (
        "Org chart",
        "A polished organization chart with hierarchy, reporting lines, and clean people-card geometry.",
    ),
    "mindmap": (
        "Mindmap",
        "A rich mind map with one central concept, branching clusters, and memorable color-coded nodes.",
    ),
    "data_pipeline": (
        "Data pipeline",
        "A data pipeline diagram from source to transform to sink, using dimensional blocks and connectors.",
    ),
    "quote_card": (
        "Quote card",
        "A refined quote card with one prominent statement, attribution area, and editorial typography.",
    ),
    "announce_card": (
        "Announcement card",
        "A bold announcement card with one dominant message, energetic shapes, and high social-share impact.",
    ),
    "badge_celebrate": (
        "Badge award",
        "A celebratory badge card with a central award mark, premium shine, and achievement framing.",
    ),
    "doc_hero": (
        "Document hero",
        "A documentation hero image with a strong header area and supporting content preview blocks.",
    ),
    "blog_header": (
        "Blog header",
        "An editorial blog header with a strong visual field, headline area, and magazine-like balance.",
    ),
    "slack_announcement": (
        "Slack announcement",
        "A chat-style announcement card with message hierarchy, reaction strip, and friendly product polish.",
    ),
    "social_square": (
        "Social square",
        "A high-impact square social graphic with central message composition and bold visual contrast.",
    ),
    "newsletter_top": (
        "Newsletter top",
        "A newsletter masthead with issue metadata, strong publication identity, and readable editorial layout.",
    ),
}


BUILTIN_IMAGE_TEMPLATES: dict[str, BuiltinImageTemplate] = {
    template_id: BuiltinImageTemplate(
        id=template_id,
        label=label,
        asset_path=f"/image-wizard/templates/{template_id}.png",
        guidance=guidance,
    )
    for template_id, (label, guidance) in _GUIDANCE.items()
}


def get_builtin_template(template_id: str | None) -> BuiltinImageTemplate | None:
    if not template_id:
        return None
    return BUILTIN_IMAGE_TEMPLATES.get(template_id)


def make_user_template_id(generation_id: str) -> str:
    return f"{USER_TEMPLATE_PREFIX}{generation_id}"


def get_user_template_source_id(template_id: str | None) -> str | None:
    if not template_id or not template_id.startswith(USER_TEMPLATE_PREFIX):
        return None
    source_id = template_id[len(USER_TEMPLATE_PREFIX) :].strip()
    return source_id or None


def describe_template_for_prompt(template_id: str | None) -> str:
    template = get_builtin_template(template_id)
    if template:
        return (
            f"Selected template: {template.label}. {template.guidance} "
            "A high-quality template sample image will be attached as a composition reference. "
            "Use that sample for layout, polish, hierarchy, and style direction only. "
            "Do not copy any filler text, numbers, logos, or sample facts from the template image."
        )
    if get_user_template_source_id(template_id):
        return (
            "Selected template: a user-saved generated image. The saved image will be attached "
            "as a composition reference. Reuse its layout, polish, hierarchy, and style direction, "
            "but do not copy its old text, numbers, logos, or facts unless the current approved "
            "plan explicitly asks for them."
        )
    return ""
