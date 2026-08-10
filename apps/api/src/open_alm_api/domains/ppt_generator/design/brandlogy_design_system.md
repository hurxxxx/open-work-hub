# Design System for Brandlogy PPT (27 × 16.75 cm) — Inspired by MiniMax

> Runtime prompt asset: `ppt_generator/prompts.py` loads this file as part of
> the PPT generation prompt. It is kept next to the runtime code on purpose and
> should not be treated as a general project documentation source of truth.

> **변경 사항 (v5):** 캔버스를 16:9(13.333"×7.5")에서 **27 × 16.75 cm**(≈10.63" × 6.59", 약 1.61:1)로 변경했습니다. 헤더·푸터 크롬(챕터명·로고·페이지·출처)이 제거된 상태이므로, **상·하단 여백을 최소화하고 본문이 캔버스를 가득 채우도록** 존을 재배치했습니다(헤드라인을 상단 가까이 올리고 본문 박스를 하단 여백 직전까지 확장). 폰트 크기는 좁아진 캔버스에 맞춰 약 0.8배로 축소했습니다. 좌표는 cm를 기준으로 하고 괄호 안에 인치를 병기합니다. 색상·컴포넌트·디자인 철학은 동일합니다.
>
> **이전 변경 이력:** v2 헤더 챕터명 제거 · v3 헤더 로고 제거 · v4 푸터(페이지·출처·작성) 제거.

## 0. Production Constraints (Read First)

Output
- **27 × 16.75 cm canvas only** (≈ 10.63" × 6.59", reference resolution ~1532 × 950 px, aspect ≈ 1.61:1). No other size/aspect is valid output.
- All deliverables go through the Brandlogy template (_Claude_Brandlogy_Template_2026.pptx or equivalent uploaded to project knowledge).

Brand Assets (mandatory, no substitution)
- Logo: **not placed on slides in this configuration.** The header strip is intentionally empty. (If a logo is ever re-enabled, it must be the Brandlogy logo only — never MiniMax or any third-party logo — and follow the Logo Integrity Rule below.)
- Typography: Pretendard only — no exceptions. Do NOT use DM Sans, Outfit, Poppins, Roboto, Noto, system fallbacks, or any other family under any circumstance. Every weight reference below maps to Pretendard's scale (Thin 100 → Black 900). Assume Pretendard is available on the rendering machine; if a fallback string is needed for export, use Pretendard, "Pretendard Variable", -apple-system, system-ui, sans-serif, but the only family that should actually render is Pretendard.

Slide Skeleton — locked positions across the deck
Every slide places the same zones at identical coordinates; only the body contents change. The header/footer strips carry no chrome, so the layout pushes the title block to the top and lets the body fill almost the whole canvas. Coordinates are given in cm with inch in parentheses.

| Zone | Position (canvas 27 × 16.75 cm) | Contents | Style |
|---|---|---|---|
| Top margin | 0 – 0.76 cm (0 – 0.30") | Empty breathing space (no header chrome) | — |
| Headline zone | 0.76 – 2.34 cm (0.30 – 0.92") from top, 0.9 cm (0.35") left margin | Slide headline (대제목) | Pretendard 700, 24–28pt, #222222, line-height 1.10–1.20 |
| Subtitle zone | 2.34 – 3.30 cm (0.92 – 1.30") from top, 0.9 cm left margin | Subtitle (부제목) | Pretendard 500, 12–13pt, #45515e, line-height 1.30 |
| Body box | 3.68 – 16.05 cm (1.45 – 6.32") from top, 0.9 cm side margins | All body components — see §5. **Must fill this box top-to-bottom.** | Mixed |
| Bottom margin | 16.05 – 16.75 cm (6.32 – 6.59") | Empty breathing space (no footer chrome) | — |

Content width: 25.2 cm (9.93"). Body box height: 12.37 cm (4.87") — the tallest zone, where ~90% of design work happens and which must be filled densely (see Body Density Rule).

Vertical rhythm: Top margin → Headline = 0.76 cm (small, just enough to breathe). Headline → Subtitle reads as one tightly-coupled unit (≈0.2 cm visual gap). Subtitle → Body ≈ 0.38 cm — a clear break that lets the body box read as its own region. The intent is a compact title block hugging the top so the body box can claim the maximum vertical space.

Lock rule: These zones do not move between slides. Headline starts at the same Y (0.76 cm), subtitle at the same Y, body box starts (3.68 cm) and ends (16.05 cm) at the same Y. Top and bottom margins stay empty on every slide. Override is permitted only when structurally unavoidable — i.e., a section divider that intentionally breaks the frame, a full-bleed cover, or a closing slide. Routine "this body is taller than usual" is NOT an unavoidable case; restructure the content instead.

Hard boundary: Body content lives strictly inside 3.68 – 16.05 cm (the Body box). It does NOT bleed upward into the Subtitle zone (above 3.68 cm) and does NOT bleed below 16.05 cm (keep the 0.7 cm bottom margin clear). Anything taller than 12.37 cm of body height must be split, scaled down, or moved to a second slide — not allowed to invade the margins.

Logo Integrity Rule (applies only if a logo is re-enabled — by default no logo is placed): The Brandlogy logo must be placed exactly as provided — original file, original proportions, original colors, original transparency (alpha channel preserved). The user supplies a transparent PNG (누끼); insert that file as-is. Do NOT add an underline, strikethrough, drop shadow, glow, border, frame, recolor, gradient, opacity change, background fill, opaque box behind the logo, or any other visual treatment. Do NOT crop, stretch, skew, rotate, or duplicate the logo. The only permitted operations are uniform scaling (preserving aspect ratio) to fit the ≈0.24" target height (resulting width typically ≈1.22" depending on source proportions), and uniform color inversion to a white variant when placed on dark backgrounds (section dividers, closing slides). A black or white rectangle behind the logo is a defect, not the design — if a generated output shows any line, mark, decoration, or solid box on/behind the logo that is not in the original file, treat it as a defect and fix it before exporting.

Body Density Rule (critical for this canvas)
Because the header and footer carry no chrome, the body box is the dominant zone and **must be filled top-to-bottom**. Leaving white space above or below the body content defeats the purpose of this layout. Plan body content to fill the full 12.37 cm height at a comfortable reading density — charts, diagrams, KPI tiles, comparison tables, dual-column layouts, supporting captions, summary bands. If cards end up shorter than the body box, add a full-width summary/insight band, a "So What" callout, or a keyword/tag footer inside each card to consume the remaining height. Whitespace is a tool for breathing rhythm between elements, not a default for the top or bottom of the canvas.

Density never overrides the hard boundary. "Filling" means filling inside the body box (3.68 – 16.05 cm) — it does NOT mean spilling content into the top margin (above 3.68 cm) or the bottom margin (below 16.05 cm). If pursuing density tempts you to push a card past the margins, you have too much content on the slide; split it.

If a slide genuinely has thin content, use one of these density tactics — never decorative padding, never zone invasion:
- Pull supporting evidence (quote, data point, mini-chart, source) into a side panel, still inside the body box
- Add a "So What" callout box at the bottom of the body box (above 16.05 cm) summarizing the takeaway
- Insert a diagram that visually reinforces the headline
- Split the body into a 2-column claim / evidence layout
- Use Pattern F (Stacked Insight Layers, see §5) — three horizontal bands within the body box

Do NOT pad with decorative shapes or stock illustrations to fake density.

Visualization-First Rule (Style 1 — strong)
Style 1 is data-first. Whenever a slide carries data, comparison, process, structure, or relationship — visualize it, do not narrate it in prose. This is a strong default, not a suggestion.

Trigger conditions (if any of these apply, the slide MUST include a visualization):
- Two or more numbers being compared (chart or KPI tile row, never inline prose)
- A trend over time (line chart or timeline, even with only 2–3 points)
- Composition / share / distribution (bar, donut, or 100% stacked bar)
- A process or sequence (horizontal arrow flow, numbered stages)
- A comparison across categories (grouped/stacked bar or table — chart preferred over table)
- A structural relationship between concepts (diagram, matrix, 2×2)
- A geographic or hierarchical breakdown (map, tree, or org chart)

Visualization options to reach for, in priority order:
1. Charts — bar (horizontal/vertical/grouped/stacked), line, area, scatter, donut. Default. Use Style 1 chart palette (§4).
2. KPI tiles with sparklines — when a single number deserves emphasis but context still matters
3. Diagrams — flow, sequence, 2×2 matrix, layered architecture, Venn (rare), funnel, hierarchy
4. Annotated images / screenshots — only when the visual artifact itself is the evidence
5. Tables — last resort, only when individual cell values matter and ranking/comparison is secondary

Constraints (visualization never breaks the layout):
- Visualizations live strictly inside the body box (3.68 – 16.05 cm). Never bleed into the headline/subtitle zones above or the bottom margin.
- A single slide should carry 1–2 visualizations max, not 4+. Cramming charts breaks the pacing more than missing them.
- Every chart and diagram must have: a title (Pretendard 600 14pt), axis labels (Pretendard 400 10pt #45515e), and a source line (Pretendard 400 9pt #8e8e93) directly below.
- If a visualization would force font sizes below 9pt or compress data labels into illegibility, the slide has too much data — split it, don't shrink the chart.
- Pure-prose body slides are reserved for: section openers, hero takeaways, single-quote callouts, definitions. Everything else gets a visualization.

When in doubt, ask: "Could this be a chart instead of bullets?" If yes, make it a chart.

---

## 1. Visual Theme & Atmosphere

The aesthetic bridges Apple-grade product-marketing clarity with a playful, rounded, gallery-like feel. Pure white (#ffffff) is the structural background; color enters via charts, KPI cards, gradients, and accent elements. Pretendard at moderate weights (500–700) carries a confident-but-approachable tone — not aggressive, not airy.

Key Characteristics
- White-dominant canvas with colorful accent elements (charts, KPI cards, gradients) carrying visual interest
- Pretendard across the entire system, with weight (not family) doing all hierarchy work
- Pill buttons (9999px / fully rounded) for nav, tabs, toggles
- Generous rounded cards (16–24px radius) for content blocks
- Brand blue spectrum: #1456f0 → #3b82f6 → #60a5fa
- Brand pink (#ea5ec1) reserved for decorative accents
- Near-black text (#222222, #18181b) on white
- Purple-tinted shadows (rgba(44, 30, 116, 0.16)) for featured cards — subtle brand glow
- Dark sections (#181e25) for divider/closing slides if needed

---

## 2. Color Palette & Roles

### Brand Primary
- Brand Blue (#1456f0): primary brand identity color
- Sky Blue (#3daeff): lighter brand variant for accents
- Brand Pink (#ea5ec1): secondary accent — decorative only, never on body text

### Blue Scale
- #bfdbfe — light blue background
- #60a5fa — primary-light, active states, chart fills
- #3b82f6 — primary-500, standard blue actions, primary chart series
- #2563eb — primary-600, emphasis
- #1d4ed8 — primary-700, deep emphasis
- #17437d — brand-deep

### Text
- #222222 — primary text (body, headline)
- #18181b — heading-dark, dark button text
- #181e25 — dark surface text, footer-bg
- #45515e — secondary text (subtitle, captions)
- #8e8e93 — tertiary/muted text (chart captions, muted notes)
- #5f5f5f — helper text

### Surface
- #ffffff — primary background (every slide)
- #f0f0f0 — secondary container background
- hsla(0, 0%, 100%, 0.4) — frosted glass overlay
- #f2f3f5 — subtle dividers
- #e5e7eb — component borders

### Semantic
- #e8ffea — success background (pair with #16a34a for success text)

### Shadow Library
| Token | Value | Use |
|---|---|---|
| Standard | rgba(0, 0, 0, 0.08) 0px 4px 6px | Default cards |
| Soft Glow | rgba(0, 0, 0, 0.08) 0px 0px 22.576px | Ambient shadow |
| Brand Glow | rgba(44, 30, 116, 0.16) 0px 0px 15px | Featured cards |
| Brand Glow Offset | rgba(44, 30, 116, 0.11) 6.5px 2px 17.5px | Hero product cards |
| Elevated | rgba(36, 36, 36, 0.08) 0px 12px 16px -4px | Lifted/hover-equivalent emphasis |

### Hero Gradient (Premium Accent — use sparingly)
A single elegant blue gradient is permitted to elevate hero moments. The gradient is built from the existing blue scale — no new colors are introduced.

TokenHero Gradient: linear-gradient(135deg, #1456f0 0%, #3b82f6 50%, #60a5fa 100%)

Fixed parameters — do NOT vary these:
- Angle: 135° (top-left dark → bottom-right light). Consistent across the deck.
- Stops: 0% / 50% / 100% with the three brand blues in order. No additional color stops.
- Colors: Only #1456f0, #3b82f6, #60a5fa from the existing scale. No purple, cyan, teal, or pink mixed in.

Permitted locations (max 3 across the entire deck)
1. Cover slide hero card — the single featured card on the cover slide (Pattern E in §5)
2. Section divider background — the dark divider slide may use Hero Gradient instead of solid #181e25 for a more premium feel
3. One Featured KPI card per slide — at most one KPI tile per slide may use the gradient as background, with white text on it. Pair with Brand Glow shadow.

Forbidden locations
- Chart bars / lines / data points — gradients on data create false visual hierarchy (longer bars look "more saturated"). Use flat brand blue (#1456f0 or #3b82f6) for all chart series.
- Headline or body text — text-on-gradient or gradient-text is AI-slop visual. Text stays solid #222222.
- Header strip and footer strip — these zones are flat, always.
- Standard content cards (non-featured) — gradients on every card destroy the white-canvas brand identity.
- Body card backgrounds in bulk — only one gradient element per slide. Multiple gradients break the design.

Premium-look rules
- Always pair Hero Gradient with the Brand Glow shadow (rgba(44, 30, 116, 0.16) 0px 0px 15px) for the soft halo effect that prevents flat-poster look.
- Inside text on gradient must be white (#ffffff) at Pretendard 500–700, never #222222 or any blue.
- Gradient cards use 20–24px radius (the larger end of the radius scale) — sharp corners on gradient look cheap.
- Never overlay another gradient, image, or pattern on top of Hero Gradient. The gradient itself IS the visual interest.

If the gradient would compete with charts on the same slide, the chart wins — move the gradient element to a different slide. Charts and gradients on the same slide create visual chaos.

---

## 3. Typography Rules (Pretendard-only)

### Family
Pretendard only (Korean + Latin support, weights 100–900). No other family is permitted under any circumstance — not for headlines, not for data, not for fallback. If a fallback string is required for export-safety, use: Pretendard, "Pretendard Variable", -apple-system, system-ui, sans-serif, but the only family that should actually render is Pretendard. Pretendard must be embedded in the .pptx on export so the layout survives on machines without it installed.

### Weight Map (functional roles)
- 700 Bold — Slide headlines, section titles, KPI numbers, strong body emphasis
- 600 SemiBold — Card titles, button text, body H2/H3
- 500 Medium — Sub-headings, subtitles, feature labels, emphasized body
- 400 Regular — Body text, captions, sources, footnotes
- 300 Light and 800 ExtraBold are available for special cases — use sparingly

### Hierarchy (27 × 16.75 cm canvas — sizes scaled ~0.8× from the 16:9 system)

| Role | Weight | Size (pt) | Line Height | Color |
|---|---|---|---|---|
| Slide Headline (대제목) | 700 | 24–28pt | 1.10–1.20 | #222222 |
| Subtitle (부제목) | 500 | 12–13pt | 1.30 | #45515e |
| Body H2 (본문 중제목) | 600 | 14–16pt | 1.35 | #222222 |
| Body H3 (본문 소제목) | 600 | 12–13pt | 1.40 | #222222 |
| Body | 400 | 9.5–11pt | 1.45 | #222222 |
| Body Emphasized | 500 | 9.5–11pt | 1.45 | #222222 |
| Body Bold | 700 | 9.5–11pt | 1.45 | #222222 |
| KPI Number | 700 | 26–38pt | 1.05 | #1456f0 (or context color) |
| KPI Label | 500 | 10–11pt | 1.25 | #45515e |
| Caption / Source | 400 | 8.5–9pt | 1.35 | #8e8e93 |
| Tag / Badge | 600 | 8.5–10pt | 1.15 | varies |

> **Note:** The previous "Chapter Name" role has been removed. The header strip carries only the logo.

### Principles
- Weight does the hierarchy work, not family. Pretendard 700 vs 500 vs 400 carries the entire vertical rhythm.
- Default line-height 1.50 for body, 1.45 for subtitles, 1.20–1.30 for headlines and labels. Tight (1.10) for big numbers.
- No italic unless quoting a source — use weight contrast instead.
- Korean–Latin mixing: Pretendard handles both natively. No font swap mid-sentence.
- Tracking (자간): 0 for body, -0.02em ~ -0.03em for large headlines (32pt+) to compensate for optical loosening at large sizes.

---

## 4. Component Stylings

### Buttons / Pills

Pill Primary Dark
- BG #181e25, text #ffffff, padding 11px 20px, radius 8px, Pretendard 600 13–14pt
- Use: primary CTA on cover/closing slides

Pill Nav / Tab
- BG rgba(0, 0, 0, 0.05), text #18181b, radius 9999px, Pretendard 500 11–12pt
- Use: section tabs, filter indicators

Pill White
- BG #ffffff, text rgba(24, 30, 37, 0.8), radius 9999px, Pretendard 500
- Use: secondary nav, inactive tabs

Secondary Light
- BG #f0f0f0, text #333333, padding 11px 20px, radius 8px, Pretendard 500
- Use: secondary actions, divider tags

### Content Cards (body zone)

Standard Content Card
- BG #ffffff, radius 13–16px, shadow Standard (rgba(0,0,0,0.08) 0px 4px 6px)
- Internal padding 16–24px
- Use: KPI tiles, point-by-point breakdowns, capability cards

Featured Card
- BG vibrant gradient (blue/purple/pink/orange family) or white, radius 20–24px
- Shadow Brand Glow (rgba(44,30,116,0.16) 0px 0px 15px)
- Use: hero takeaway, section opener, headline product card

Data Card (chart container)
- BG #ffffff, radius 13px, border 1px solid #f2f3f5, no shadow OR Standard shadow
- Title row at top (Pretendard 600, 14pt), source line at bottom (Pretendard 400, 9pt, #8e8e93)

### Charts
- Primary series: #1456f0 or #3b82f6
- Secondary series: #60a5fa, #bfdbfe, #17437d
- Negative/comparison series: #ea5ec1 or neutral #8e8e93
- Gridlines: #e5e7eb, 1px
- Axis labels: Pretendard 400, 10pt, #45515e
- Data labels on bars/points: Pretendard 600, 11pt, #222222
- Always cite source under chart in 9–10pt #8e8e93

### Tables
- Header row: BG #f2f3f5, Pretendard 600 12pt, #222222
- Body rows: Pretendard 400 12pt, #222222, alternating BG #ffffff / #fafafa optional
- Row dividers: 1px #e5e7eb
- Cell padding: 8px 12px
- No vertical dividers — rely on column spacing

### Links / Inline Emphasis
- Primary inline: #1456f0, no underline, Pretendard 500
- Source attribution: #8e8e93, Pretendard 400, 9–10pt

---

## 5. Layout Principles

### Slide Grid (27 × 16.75 cm)
- Outer margins: 0.9 cm (0.35") left/right, 0.76 cm (0.30") top, 0.70 cm (0.28") bottom
- Content width: 25.2 cm (9.93")
- Content height (top margin to bottom margin): 15.29 cm
- Internal column system: 12-column grid, ~0.4 cm gutter (column width ≈ 1.7 cm)

### Vertical Zones (locked — identical coordinates on every slide; cm with inch in parens)
| Zone | Y-range (from top) | Contents |
|---|---|---|
| Top margin | 0 – 0.76 cm (0 – 0.30") | Empty (no header chrome) |
| Headline | 0.76 – 2.34 cm (0.30 – 0.92") | Slide headline (대제목) |
| Subtitle | 2.34 – 3.30 cm (0.92 – 1.30") | Subtitle (부제목, one-sentence lead, 12–13pt) |
| Body box | 3.68 – 16.05 cm (1.45 – 6.32") | All body components, charts, diagrams — fill top-to-bottom |
| Bottom margin | 16.05 – 16.75 cm (6.32 – 6.59") | Empty (no footer chrome) |

Lock rule: These zones do not shift between slides. The headline → subtitle → body rhythm is fixed across the entire deck. The body box (3.68 – 16.05 cm, a 12.37 cm / 4.87" tall box) is where ~90% of design work happens, and it must be filled densely top-to-bottom — but only inside the box (see §0 Body Density Rule and Hard boundary).

Vertical rhythm (gaps between zones): Top margin → Headline = 0.76 cm (compact, just enough to breathe at the top). Headline → Subtitle ≈ 0.2 cm visual gap — title and subtitle read as a single tightly-coupled unit. Subtitle → Body = 0.38 cm (a clear break that lets the body box read as its own region). The title block hugs the top so the body box can claim maximum vertical space and fill the canvas.

Bottom margin: The 0.70 cm below the body box bottom (16.05 cm) stays empty as breathing space — no page number, source, or author line. Treat 16.05 cm as a wall for body content; the body should fill right up to it.

Override exception: Section dividers, full-bleed covers, and closing slides may break the frame intentionally — but only if the break is the design point. "I had too much content" is not a valid override.

### Spacing Scale (within body zone)
- Base unit: 4px (0.028" / 0.07cm)
- Steps: 4, 8, 12, 16, 20, 24, 32, 40, 48, 64, 80px
- Card-to-card gap: 16–24px
- Section-internal padding: 16–24px
- Headline-to-subtitle gap: ~0.2 cm (tightly coupled)
- Subtitle-to-body gap: ~0.38 cm

### Border Radius Scale
- 4px — small tags, micro badges
- 8px — buttons, small cards, input-like elements
- 11–13px — medium cards, data tiles
- 16–20px — large content cards
- 22–24px — hero product cards, major containers
- 30–32px — badge pills
- 9999px — full pill (buttons, tabs)

### Body Composition Patterns (use these to maintain density)

Pattern A — KPI Strip + Detail (most common)
- Top half of body: 3–4 KPI cards in a row (each ~3" wide × 1.6" tall)
- Bottom half: supporting chart or 2-column claim/evidence

Pattern B — Two-Column Compare
- Left column (~12 cm wide): claim + supporting bullets
- Right column (~12 cm wide): chart, diagram, or visual evidence
- Optional bottom-spanning "So What" callout box

Pattern C — Diagram-Centered
- Centered diagram occupies ~70% of body
- 3–4 caption boxes around the diagram explain components
- Bottom strip: source + summary takeaway

Pattern D — Process Flow
- Horizontal arrow flow with 4–6 stages across body
- Each stage: numbered circle, stage label, 1–2 line description
- Below the flow: outcomes summary or pull-quote

Pattern E — Quote + Evidence
- Large pull-quote (Pretendard 500, 24–28pt) on left half
- Stack of 2–3 supporting data cards on right half

Pattern F — Stacked Insight Layers (use when content is thin to keep density)
- Top band: KPI summary (1 row)
- Middle band: one chart or diagram
- Bottom band: 3-up evidence cards (claim + 1-line proof + source)
- Eliminates empty bottom space without padding

---

## 6. Depth & Elevation

| Level | Treatment | Use |
|---|---|---|
| 0 — Flat | No shadow | Background, in-flow text |
| 1 — Subtle | rgba(0,0,0,0.08) 0px 4px 6px | Standard content cards |
| 2 — Ambient | rgba(0,0,0,0.08) 0px 0px 22.576px | Soft surrounding glow |
| 3 — Brand Glow | rgba(44,30,116,0.16) 0px 0px 15px | Featured/takeaway cards |
| 4 — Elevated | rgba(36,36,36,0.08) 0px 12px 16px -4px | Hero, hover-equivalent emphasis |

Use Brand Glow sparingly — at most one element per slide. Standard shadow handles most cards. Flat is the default for blocks of text directly on the white slide background.

---

## 7. Do's and Don'ts

### Do
- Anchor the headline and subtitle at the same coordinates on every single slide; keep the header strip empty
- Fill the lower body box with structured, dense content (charts, KPI cards, 2-column layouts, evidence stacks)
- Use Pretendard weights — not different families — to build hierarchy
- Apply pill radius (9999px) for tabs/toggles, 8px for action buttons, 16–24px for content cards
- Reserve the brand purple-tinted shadow for the single featured element on a slide
- Keep body copy at Pretendard 400–500; use 700 only for emphasis and KPI numbers
- Cite every data source in 9–10pt #8e8e93 at the bottom of the relevant element
- Use 12-column internal grid logic for body layouts

### Don't
- Don't leave the bottom 20–30% of the body zone visually empty — restructure or add evidence/callout
- Don't use any font other than Pretendard — no DM Sans, Outfit, Poppins, Roboto, Noto, system defaults
- Don't use the MiniMax logo or any logo other than Brandlogy
- Don't deviate from the locked zone coordinates (header strip, headline, subtitle, body box, footer strip) across slides — same Y for headline, subtitle, body top, and body bottom on every page. Override only when structurally unavoidable (section divider, full-bleed cover, closing slide).
- Don't add a page number, source line, or author/footnote in the footer strip — the footer strip is empty.
- Don't add a chapter-name label, logo, or any repeating element in the header strip — the header strip is empty.
- Don't let body content invade the headline/subtitle zones above 3.68 cm or the bottom margin below 16.05 cm — if it doesn't fit, split the slide
- Don't apply brand pink (#ea5ec1) to body text or buttons — decorative accents only
- Don't use sharp corners on content cards — minimum radius is 8px, body cards 13–24px
- Don't darken shadows past 0.16 opacity — light-and-airy is the brand register
- Don't apply Hero Gradient to chart bars, lines, or any data series — gradients create false visual hierarchy on data. Charts use flat brand blue.
- Don't apply Hero Gradient to text or use gradient-text effects — solid #222222 for ink, white for text on gradient surfaces.
- Don't use more than one Hero Gradient element per slide, and don't exceed 3 gradient elements across the entire deck.
- Don't vary the gradient angle, stops, or colors — Hero Gradient is fixed at linear-gradient(135deg, #1456f0 0%, #3b82f6 50%, #60a5fa 100%).
- Don't pad slides with decorative shapes or stock illustrations to fake density — use real evidence
- Don't introduce a second display family alongside Pretendard
- Don't use weight 800–900 for body headings (reserve for closing slide / section divider only)
- Don't use emojis anywhere on slides

---

## 8. Aspect Ratio & Export Notes

- 27 × 16.75 cm only. Reject 16:9, 4:3, 1:1, 9:16, A4, letter, or any other format requests.
- Export resolution target: ~1532 × 950 px minimum for image preview; native PowerPoint vector preserved in the .pptx.
- Embedded font: Pretendard must be embedded in the .pptx (Save options → "Embed fonts in the file") so the layout survives on machines without Pretendard installed.
- All chart text and data labels must be live text (not rasterized images) to keep edit-ability.

---

## 9. Agent Prompt Guide

### Quick Reference Strip
- Canvas: 27 × 16.75 cm only (≈10.63" × 6.59")
- Bg: #ffffff (every slide), #181e25 (closing/divider only)
- Headline: #222222, Pretendard 700, 24–28pt
- Subtitle: #45515e, Pretendard 500, 12–13pt
- Body: #222222, Pretendard 400, 9.5–11pt
- Source/caption: #8e8e93, Pretendard 400, 8.5–9pt
- Body box: 3.68 – 16.05 cm — **fill top-to-bottom** (add summary band / keyword footers if cards run short)
- Brand blue: #1456f0 / #3b82f6 / #60a5fa
- Hero Gradient (premium accent, max 3 elements per deck): linear-gradient(135deg, #1456f0 0%, #3b82f6 50%, #60a5fa 100%) — for cover hero card / section divider bg / 1 featured KPI per slide. Pair with Brand Glow shadow. Never on charts, text, headers, or footers.
- Brand pink (accents only): #ea5ec1
- Borders: #e5e7eb, #f2f3f5
- Header strip: **empty — no chapter name, no logo**
- Footer strip: **empty — no page number, no source, no author line**
- Font: Pretendard only

### Example Component Prompts

Cover Slide (Hero Gradient option)
"Build a 27 × 16.75 cm cover slide on #ffffff. Eyebrow line at top (~0.6 cm), Pretendard 600 10–11pt #8e8e93. Slide headline at 0.76–2.34 cm, Pretendard 700 30–34pt #222222, line-height 1.10. Subtitle just below, Pretendard 500 13pt #45515e. Body box (3.68–16.05 cm): hero featured card with Hero Gradient (linear-gradient(135deg, #1456f0 0%, #3b82f6 50%, #60a5fa 100%)), 20px radius, Brand Glow shadow, central KPI Pretendard 700 ~48pt #ffffff (white on gradient — never blue) with a label below; pair it with a contents/agenda card so the two fill the body box top-to-bottom. Top and bottom margins stay empty (no logo, chapter name, page number, or source)."

Content Slide — KPI Strip + Chart
"Build a 27 × 16.75 cm content slide. Top margin empty — no logo, no chapter name. Headline at 0.76–2.34 cm, Pretendard 700 26pt #222222. Subtitle at 2.34–3.30 cm, Pretendard 500 12.5pt #45515e. Body box (3.68–16.05 cm) split: top band is a row of 3–4 KPI cards (white BG, 11px radius, Standard shadow, padding ~0.5 cm), each with KPI number Pretendard 700 26pt #1456f0 and label Pretendard 500 10.5pt #45515e. Bottom band is a chart card + a narrative/insight card sized so the two together fill the body box down to 16.05 cm; chart primary series #3b82f6, axis labels Pretendard 400 9.5pt, optional source caption under the chart Pretendard 400 8.5pt #8e8e93. Bottom margin stays empty — no page number, no source line."

Two-Column Compare
"Build a 27 × 16.75 cm slide with anchors as standard (empty top margin — no logo, no chapter name). Body zone: two columns, ~12 cm wide each, ~0.7 cm gutter. Left column header Pretendard 600 18pt #222222, body bullets Pretendard 400 13pt #222222 line-height 1.50. Right column same structure but with a vertical bar chart (primary #1456f0, comparison #ea5ec1). Add a 'So What' callout box spanning full width at the bottom of the body zone, BG #f2f3f5, 13px radius, padding 16px, Pretendard 600 14pt #222222."

Section Divider
"Build a 27 × 16.75 cm section divider on #181e25 (dark) BG OR Hero Gradient for premium feel. Section number top-left Pretendard 600 12pt rgba(255,255,255,0.6) — part of the divider design, the only header text permitted (standard content slides carry an empty top margin). Section title centered vertically, Pretendard 700 ~42pt #ffffff. One-line lead under title, Pretendard 500 ~17pt rgba(255,255,255,0.7). No footer (no page number, no source)."

### Iteration Checklist (run before exporting any slide)
1. Canvas 27 × 16.75 cm? ✓
2. Pretendard everywhere — no other fonts? ✓
3. Top & bottom margins empty — no logo, chapter name, page number, or source? ✓
4. All zone anchors (headline 0.76 cm / subtitle 2.34 cm / body 3.68–16.05 cm) match previous slide coordinates? ✓
5. Body content stays strictly inside 3.68 – 16.05 cm — no invasion of the headline/subtitle zones above or the bottom margin below? ✓
6. **Body box filled top-to-bottom** — no empty band at the top or bottom of the body box (add a summary band / per-card keyword footer if content runs short)? ✓
7. If the slide carries data / comparison / process / structure — is it visualized as a chart or diagram (not narrated as prose)? ✓
8. If a chart needs sourcing, the caption sits directly under the chart inside the body box (not in a footer)? ✓
9. At most one Brand Glow element on the slide? ✓
10. Hero Gradient (if used) only on permitted locations (cover hero card / section divider bg / 1 featured KPI), max 1 per slide and max 3 across the deck, never on chart bars or text? ✓
11. Headline weight 700, subtitle weight 500, body 400 — hierarchy holds? ✓
12. No emojis anywhere? ✓
13. All chart/data text is live (not rasterized)? ✓

---

End of system. Apply consistently across every slide in the deck.
