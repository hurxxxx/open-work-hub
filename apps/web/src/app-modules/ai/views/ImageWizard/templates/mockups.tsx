// i18n-exempt-file: SVG template mockups use fixed decorative placeholder labels.
/**
 * Programmatic SVG mockups for the 22 templates. Each renders inside a
 * fixed 16:10 aspect viewBox (160 × 100). Colors are intentionally
 * muted so the cards feel like wireframes / mockups, not finished art.
 */

import { MockupCard as Card } from './MockupCard';
import { MockupLine as Line } from './MockupLine';
import { MockupTitle as Title } from './MockupTitle';
import { MOCKUP_COLORS } from './mockup-theme';

const STROKE = MOCKUP_COLORS.stroke;
const TXT = MOCKUP_COLORS.text;
const TXT_HEAVY = MOCKUP_COLORS.textHeavy;
const FILL = MOCKUP_COLORS.fill;
const FILL_DEEP = MOCKUP_COLORS.fillDeep;
const ACC = MOCKUP_COLORS.accent; // inherits app-accent color from the parent.

// 발표 (5)
const meeting_deck_title = () => (
  <Card>
    <Title x="14" y="36" w="80" h="6" color={ACC} />
    <Line x="14" y="48" w="60" />
    <Line x="14" y="54" w="44" />
    <rect x="100" y="20" width="46" height="60" fill={FILL_DEEP} rx="2" />
  </Card>
);

const meeting_deck_kpi = () => (
  <Card>
    <Title x="12" y="12" w="50" h="5" color={ACC} />
    {[0, 1, 2, 3].map((i) => {
      const x = 10 + (i % 4) * 36;
      const y = 28;
      return (
        <g key={i}>
          <rect
            x={x}
            y={y}
            width="32"
            height="58"
            rx="3"
            fill={FILL}
            stroke={STROKE}
          />
          <text
            x={x + 16}
            y={y + 28}
            textAnchor="middle"
            fontSize="14"
            fontWeight="700"
            fill={ACC}
          >
            {['82%', '12.4', '3.1k', '+18%'][i]}
          </text>
          <Line x={x + 4} y={y + 42} w={24} />
          <Line x={x + 4} y={y + 50} w={20} />
        </g>
      );
    })}
  </Card>
);

const meeting_deck_compare = () => (
  <Card>
    <Title x="12" y="10" w="60" color={ACC} />
    <rect
      x="10"
      y="22"
      width="68"
      height="68"
      rx="3"
      fill={FILL}
      stroke={STROKE}
    />
    <rect
      x="82"
      y="22"
      width="68"
      height="68"
      rx="3"
      fill={FILL}
      stroke={STROKE}
    />
    <text
      x="44"
      y="36"
      textAnchor="middle"
      fontSize="6"
      fontWeight="700"
      fill={TXT_HEAVY}
    >
      BEFORE
    </text>
    <text
      x="116"
      y="36"
      textAnchor="middle"
      fontSize="6"
      fontWeight="700"
      fill={ACC}
    >
      AFTER
    </text>
    {[0, 1, 2, 3].map((i) => (
      <g key={i}>
        <Line x="16" y={48 + i * 8} w={56} />
        <Line x="88" y={48 + i * 8} w={56} />
      </g>
    ))}
  </Card>
);

const team_intro = () => (
  <Card>
    <Title x="12" y="10" w="44" color={ACC} />
    {[0, 1, 2, 3].map((i) => {
      const x = 10 + i * 38;
      return (
        <g key={i}>
          <circle cx={x + 16} cy="42" r="12" fill={FILL_DEEP} />
          <Title x={x + 4} y="60" w="24" />
          <Line x={x + 4} y="68" w="22" />
          <Line x={x + 4} y="74" w="18" />
        </g>
      );
    })}
  </Card>
);

const deck_section_divider = () => (
  <Card bg={MOCKUP_COLORS.cardBgDark}>
    <text
      x="80"
      y="48"
      textAnchor="middle"
      fontSize="14"
      fontWeight="700"
      fill={MOCKUP_COLORS.white}
    >
      SECTION 02
    </text>
    <rect
      x="60"
      y="56"
      width="40"
      height="1.5"
      fill={MOCKUP_COLORS.white}
      opacity="0.6"
    />
    <text
      x="80"
      y="72"
      textAnchor="middle"
      fontSize="6"
      fill={MOCKUP_COLORS.white}
      opacity="0.7"
    >
      Overview
    </text>
  </Card>
);

// 보고서 (4)
const status_report = () => (
  <Card>
    <Title x="10" y="10" w="60" color={ACC} />
    <Line x="10" y="18" w="40" />
    <rect
      x="10"
      y="26"
      width="68"
      height="32"
      rx="3"
      fill={FILL}
      stroke={STROKE}
    />
    <Title x="14" y="32" w="20" color={ACC} />
    <Line x="14" y="40" w="50" />
    <Line x="14" y="46" w="44" />
    <Line x="14" y="52" w="40" />
    <rect
      x="82"
      y="26"
      width="68"
      height="32"
      rx="3"
      fill={FILL}
      stroke={STROKE}
    />
    <Title x="86" y="32" w="20" />
    <Line x="86" y="40" w="50" />
    <Line x="86" y="46" w="40" />
    <Line x="86" y="52" w="32" />
    <rect x="10" y="64" width="140" height="24" rx="3" fill={FILL_DEEP} />
    <Title x="14" y="70" w="30" />
  </Card>
);

const kpi_dashboard = () => (
  <Card>
    <Title x="10" y="10" w="50" color={ACC} />
    {[0, 1, 2, 3].map((i) => {
      const x = 10 + (i % 4) * 36;
      return (
        <g key={i}>
          <rect x={x} y="22" width="32" height="22" rx="2" fill={FILL_DEEP} />
          <text
            x={x + 16}
            y="36"
            textAnchor="middle"
            fontSize="9"
            fontWeight="700"
            fill={ACC}
          >
            {['82', '+12%', '3.1k', '94'][i]}
          </text>
        </g>
      );
    })}
    <rect
      x="10"
      y="50"
      width="140"
      height="40"
      rx="2"
      fill={FILL}
      stroke={STROKE}
    />
    <polyline
      points="14,80 36,72 56,76 76,60 96,68 116,52 136,58 146,46"
      stroke={ACC}
      strokeWidth="1.4"
      fill="none"
    />
  </Card>
);

const post_mortem = () => (
  <Card>
    <rect x="0" y="0" width="160" height="14" fill={ACC} opacity="0.85" />
    <text
      x="10"
      y="10"
      fontSize="6"
      fontWeight="700"
      fill={MOCKUP_COLORS.white}
    >
      POST-MORTEM
    </text>
    <Title x="10" y="22" w="80" />
    <Line x="10" y="30" w="100" />
    <Line x="10" y="36" w="80" />
    <rect
      x="10"
      y="44"
      width="44"
      height="48"
      rx="2"
      fill={FILL}
      stroke={STROKE}
    />
    <rect
      x="58"
      y="44"
      width="44"
      height="48"
      rx="2"
      fill={FILL}
      stroke={STROKE}
    />
    <rect
      x="106"
      y="44"
      width="44"
      height="48"
      rx="2"
      fill={FILL}
      stroke={STROKE}
    />
    <text
      x="32"
      y="56"
      textAnchor="middle"
      fontSize="5"
      fontWeight="700"
      fill={TXT_HEAVY}
    >
      WHAT
    </text>
    <text
      x="80"
      y="56"
      textAnchor="middle"
      fontSize="5"
      fontWeight="700"
      fill={TXT_HEAVY}
    >
      WHY
    </text>
    <text
      x="128"
      y="56"
      textAnchor="middle"
      fontSize="5"
      fontWeight="700"
      fill={TXT_HEAVY}
    >
      NEXT
    </text>
  </Card>
);

const weekly_brief = () => (
  <Card>
    <Title x="10" y="10" w="60" color={ACC} />
    <text x="10" y="20" fontSize="5" fill={TXT}>
      2026.W18
    </text>
    {[0, 1, 2].map((i) => (
      <g key={i}>
        <circle cx="14" cy={32 + i * 18} r="2" fill={ACC} />
        <Title x="20" y={30 + i * 18} w="60" />
        <Line x="20" y={36 + i * 18} w="120" />
      </g>
    ))}
  </Card>
);

// 다이어그램 (5)
const process_flow = () => (
  <Card>
    {[0, 1, 2, 3].map((i) => {
      const x = 8 + i * 38;
      return (
        <g key={i}>
          <rect
            x={x}
            y="40"
            width="30"
            height="20"
            rx="3"
            fill={FILL_DEEP}
            stroke={STROKE}
          />
          <Line x={x + 4} y="48" w={22} />
          <Line x={x + 4} y="54" w={16} />
          {i < 3 && (
            <g>
              <line
                x1={x + 30}
                y1="50"
                x2={x + 36}
                y2="50"
                stroke={ACC}
                strokeWidth="1.4"
              />
              <polygon
                points={`${x + 36},50 ${x + 33},48 ${x + 33},52`}
                fill={ACC}
              />
            </g>
          )}
        </g>
      );
    })}
  </Card>
);

const swimlane = () => (
  <Card>
    <rect x="0" y="20" width="160" height="0.6" fill={STROKE} />
    <rect x="0" y="50" width="160" height="0.6" fill={STROKE} />
    <rect x="0" y="80" width="160" height="0.6" fill={STROKE} />
    {[
      { lane: 0, items: [0, 1] },
      { lane: 1, items: [0, 1, 2] },
      { lane: 2, items: [0] },
    ].map(({ lane, items }) =>
      items.map((i) => {
        const x = 16 + i * 38;
        const y = 8 + lane * 30;
        return (
          <rect
            key={`${lane}-${i}`}
            x={x}
            y={y}
            width="30"
            height="14"
            rx="2"
            fill={FILL_DEEP}
          />
        );
      }),
    )}
    <text x="2" y="14" fontSize="4" fill={TXT}>
      UX
    </text>
    <text x="2" y="44" fontSize="4" fill={TXT}>
      ENG
    </text>
    <text x="2" y="74" fontSize="4" fill={TXT}>
      QA
    </text>
  </Card>
);

const org_chart = () => (
  <Card>
    <rect
      x="64"
      y="10"
      width="32"
      height="14"
      rx="2"
      fill={ACC}
      opacity="0.85"
    />
    <line x1="80" y1="24" x2="80" y2="36" stroke={STROKE} strokeWidth="1" />
    <line x1="22" y1="36" x2="138" y2="36" stroke={STROKE} strokeWidth="1" />
    {[0, 1, 2, 3].map((i) => {
      const x = 14 + i * 36;
      return (
        <g key={i}>
          <line
            x1={x + 12}
            y1="36"
            x2={x + 12}
            y2="48"
            stroke={STROKE}
            strokeWidth="1"
          />
          <rect x={x} y="48" width="24" height="14" rx="2" fill={FILL_DEEP} />
          <line
            x1={x + 12}
            y1="62"
            x2={x + 12}
            y2="74"
            stroke={STROKE}
            strokeWidth="1"
          />
          <rect x={x + 4} y="74" width="16" height="10" rx="1.5" fill={FILL} />
        </g>
      );
    })}
  </Card>
);

const mindmap = () => (
  <Card>
    <circle cx="80" cy="50" r="16" fill={ACC} opacity="0.85" />
    {[
      { x: 24, y: 20 },
      { x: 136, y: 20 },
      { x: 24, y: 80 },
      { x: 136, y: 80 },
      { x: 14, y: 50 },
      { x: 146, y: 50 },
    ].map((p, i) => (
      <g key={i}>
        <line
          x1="80"
          y1="50"
          x2={p.x}
          y2={p.y}
          stroke={STROKE}
          strokeWidth="0.8"
        />
        <circle cx={p.x} cy={p.y} r="6" fill={FILL_DEEP} />
      </g>
    ))}
  </Card>
);

const data_pipeline = () => (
  <Card>
    {[0, 1, 2, 3, 4].map((i) => {
      const x = 6 + i * 32;
      const shape = i === 0 || i === 4 ? 'circle' : 'rect';
      return (
        <g key={i}>
          {shape === 'circle' ? (
            <circle
              cx={x + 12}
              cy="50"
              r="10"
              fill={FILL_DEEP}
              stroke={STROKE}
            />
          ) : (
            <rect
              x={x}
              y="40"
              width="24"
              height="20"
              rx="2"
              fill={FILL_DEEP}
              stroke={STROKE}
            />
          )}
          {i < 4 && (
            <g>
              <line
                x1={x + 24}
                y1="50"
                x2={x + 32}
                y2="50"
                stroke={ACC}
                strokeWidth="1"
                strokeDasharray="2 1.5"
              />
            </g>
          )}
        </g>
      );
    })}
    <text x="80" y="80" textAnchor="middle" fontSize="5" fill={TXT}>
      SOURCE → TRANSFORM → SINK
    </text>
  </Card>
);

// 카드·배너 (4)
const quote_card = () => (
  <Card>
    <text x="14" y="34" fontSize="20" fontWeight="700" fill={ACC}>
      "
    </text>
    <Title x="22" y="30" w="118" />
    <Line x="22" y="40" w="110" />
    <Line x="22" y="46" w="92" />
    <text x="22" y="76" fontSize="6" fontWeight="700" fill={TXT_HEAVY}>
      Author Name
    </text>
    <text x="22" y="84" fontSize="5" fill={TXT}>
      Role · Company
    </text>
  </Card>
);

const announce_card = () => (
  <Card>
    <rect x="0" y="0" width="160" height="100" fill={ACC} opacity="0.92" />
    <text
      x="80"
      y="36"
      textAnchor="middle"
      fontSize="6"
      fontWeight="700"
      fill={MOCKUP_COLORS.white}
      opacity="0.85"
    >
      ANNOUNCEMENT
    </text>
    <text
      x="80"
      y="58"
      textAnchor="middle"
      fontSize="14"
      fontWeight="800"
      fill={MOCKUP_COLORS.white}
    >
      We just shipped
    </text>
    <text
      x="80"
      y="76"
      textAnchor="middle"
      fontSize="6"
      fill={MOCKUP_COLORS.white}
      opacity="0.85"
    >
      Read more →
    </text>
  </Card>
);

const badge_celebrate = () => (
  <Card>
    <circle cx="80" cy="48" r="32" fill={ACC} opacity="0.15" />
    <circle cx="80" cy="48" r="22" fill={ACC} opacity="0.85" />
    <text
      x="80"
      y="44"
      textAnchor="middle"
      fontSize="6"
      fontWeight="700"
      fill={MOCKUP_COLORS.white}
    >
      YEAR
    </text>
    <text
      x="80"
      y="56"
      textAnchor="middle"
      fontSize="14"
      fontWeight="800"
      fill={MOCKUP_COLORS.white}
    >
      Q3
    </text>
    <text
      x="80"
      y="92"
      textAnchor="middle"
      fontSize="6"
      fontWeight="700"
      fill={TXT_HEAVY}
    >
      TOP PERFORMER
    </text>
  </Card>
);

const doc_hero = () => (
  <Card>
    <rect x="0" y="0" width="160" height="60" fill={ACC} opacity="0.18" />
    <text x="14" y="34" fontSize="10" fontWeight="700" fill={TXT_HEAVY}>
      Documentation
    </text>
    <Line x="14" y="44" w="80" />
    <Line x="14" y="74" w="120" />
    <Line x="14" y="80" w="100" />
    <Line x="14" y="86" w="110" />
  </Card>
);

// 소셜 (4)
const blog_header = () => (
  <Card>
    <rect x="0" y="0" width="60" height="100" fill={ACC} opacity="0.7" />
    <text x="68" y="36" fontSize="11" fontWeight="700" fill={TXT_HEAVY}>
      5 things
    </text>
    <text x="68" y="50" fontSize="11" fontWeight="700" fill={TXT_HEAVY}>
      we learned
    </text>
    <Line x="68" y="60" w="60" />
    <Line x="68" y="68" w="48" />
    <text x="68" y="86" fontSize="5" fill={TXT}>
      Blog · 4 min read
    </text>
  </Card>
);

const slack_announcement = () => (
  <Card bg={MOCKUP_COLORS.cardBgWarm}>
    <rect
      x="6"
      y="10"
      width="148"
      height="80"
      rx="3"
      fill={MOCKUP_COLORS.white}
      stroke={STROKE}
    />
    <circle cx="18" cy="22" r="5" fill={ACC} />
    <Title x="26" y="20" w="40" />
    <text x="68" y="22" fontSize="4" fill={TXT}>
      10:24 AM
    </text>
    <Line x="14" y="34" w="120" />
    <Line x="14" y="42" w="110" />
    <Line x="14" y="50" w="80" />
    <rect x="14" y="60" width="80" height="20" rx="2" fill={FILL_DEEP} />
    <text x="20" y="74" fontSize="5" fontWeight="700" fill={ACC}>
      +12 reactions
    </text>
  </Card>
);

const social_square = () => (
  <Card>
    <rect x="20" y="0" width="120" height="100" fill={ACC} opacity="0.18" />
    <text
      x="80"
      y="40"
      textAnchor="middle"
      fontSize="11"
      fontWeight="800"
      fill={TXT_HEAVY}
    >
      BIG IDEA
    </text>
    <text
      x="80"
      y="56"
      textAnchor="middle"
      fontSize="11"
      fontWeight="800"
      fill={ACC}
    >
      HERE
    </text>
    <Line x="50" y="68" w="60" />
    <text x="80" y="86" textAnchor="middle" fontSize="5" fill={TXT}>
      @brand · share
    </text>
  </Card>
);

const newsletter_top = () => (
  <Card>
    <text
      x="80"
      y="22"
      textAnchor="middle"
      fontSize="5"
      fontWeight="700"
      fill={TXT}
    >
      WEEKLY · ISSUE 124
    </text>
    <line x1="20" y1="28" x2="140" y2="28" stroke={STROKE} strokeWidth="0.6" />
    <text
      x="80"
      y="50"
      textAnchor="middle"
      fontSize="14"
      fontWeight="800"
      fill={ACC}
    >
      The Friday Five
    </text>
    <text x="80" y="66" textAnchor="middle" fontSize="5" fill={TXT}>
      5 stories worth your weekend
    </text>
    <line x1="60" y1="78" x2="100" y2="78" stroke={ACC} strokeWidth="1.5" />
  </Card>
);

const blank_canvas = () => (
  <Card>
    <rect
      x="20"
      y="20"
      width="120"
      height="60"
      fill="none"
      stroke={STROKE}
      strokeDasharray="3 3"
      rx="2"
    />
    <text x="80" y="54" textAnchor="middle" fontSize="6" fill={TXT}>
      비어있는 캔버스
    </text>
  </Card>
);

export const TEMPLATE_MOCKUPS = {
  meeting_deck_title,
  meeting_deck_kpi,
  meeting_deck_compare,
  team_intro,
  deck_section_divider,
  status_report,
  kpi_dashboard,
  post_mortem,
  weekly_brief,
  process_flow,
  swimlane,
  org_chart,
  mindmap,
  data_pipeline,
  quote_card,
  announce_card,
  badge_celebrate,
  doc_hero,
  blog_header,
  slack_announcement,
  social_square,
  newsletter_top,
  blank_canvas,
} as const;

export type TemplateMockupId = keyof typeof TEMPLATE_MOCKUPS;
