import type { CSSProperties, ReactNode } from 'react';

import { useTranslation } from 'react-i18next';

import type { PptSlide } from '../../api/ppt-generator-api';

/**
 * slides_spec(구조화 데이터)를 HTML 슬라이드로 렌더한다. .pptx 빌더(design/builders_a4.py)와
 * 동일한 두원공조 A4 경영진 보고 양식(27.517×19.05cm)을 재현한다.
 *
 * 빌더가 cm 절대좌표로 그리므로, 공통 chrome(워터마크·Confidential 배지·로고·분할 가로선·
 * 대각선 DCC 워터마크·저작권)도 같은 좌표를 캔버스 대비 %로 환산해 절대배치한다. 본문 콘텐츠
 * 영역만 안전 구역 안에서 flex 로 흐른다. 폰트 크기는 pt → cqw(컨테이너 폭 1%) 로 환산해
 * 슬라이드 폭에 맞춰 자동 스케일된다.
 */

// 캔버스 (builders_a4.py SLIDE_W_CM / SLIDE_H_CM)
const CW = 27.517;
const CH = 19.05;
// cm → 캔버스 대비 % (x/너비는 폭 기준, y/높이는 높이 기준)
const X = (cm: number) => `${((cm / CW) * 100).toFixed(3)}%`;
const Y = (cm: number) => `${((cm / CH) * 100).toFixed(3)}%`;
// pt → cqw (1pt=0.03528cm, 폭 27.517cm 기준): pt * 0.03528 / 27.517 * 100
const FT = (pt: number) => `${(pt * 0.128208).toFixed(3)}cqw`;
const LOGO_SRC = '/ppt-templates/doowon_wordmark.png';

// builders_a4.py COLORS 와 1:1
const C = {
  white: '#FFFFFF',
  navy: '#1B2C6B', // brand_navy
  red: '#D7261E', // brand_red
  coverTitle: '#333333',
  coverRule: '#808080',
  coverWatermark: '#E5E5E5',
  verLabel: '#666666',
  bodyRule: '#808080',
  bodyTitle: '#1A1A1A',
  dccWatermark: '#F0E0E0',
  copyright: '#C8C8C8',
  dateText: '#000000',
  surface: '#F5F6F8',
  surfaceSoft: '#FAFAFB',
  hairline: '#E2E4E9',
  coolMist: '#EAEEF5',
  track: '#E8ECF2',
  amber: '#D7B017',
  green: '#2D8659',
  navySubtle: '#A8B4D9',
  muted: '#666666',
  statusGoodBg: '#E7F1EC',
  statusBadBg: '#FBE9E8',
  statusWarnBg: '#FBF5E0',
  previewShadow: '0 1px 4px rgba(0,0,0,.10)',
} as const;

// builders_a4.py §3 고정 문자열 — 변경 금지 (Control/Confidential 사이 더블 스페이스)
const COVER_WATERMARK_TEXT = 'DOOWON Climate Control  Confidential Documents';
const CONFIDENTIAL_BADGE_TEXT = 'Confidential';
const DCC_WATERMARK_TEXT = 'DCC Confidential Documents';
const COPYRIGHT_TEXT =
  'Doowon Climate Control Co., Ltd. : This information is exclusive property of ' +
  'Doowon Corporation. Without their consent, it may not be required or given to ' +
  'third parties.';

const FONT_STACK =
  "'HDharmony M','현대하모니 M','Pretendard','Malgun Gothic',-apple-system,sans-serif"; // i18n-exempt-line: font family name

type Dict = Record<string, unknown>;

const str = (d: Dict, k: string, fb = ''): string => {
  const v = d[k];
  return v == null || v === '' ? fb : String(v);
};
const arr = (d: Dict, k: string): Dict[] => {
  const v = d[k];
  return Array.isArray(v) ? (v as Dict[]) : [];
};
const truthy = (v: unknown): boolean =>
  v === true || v === 'true' || v === 1 || v === '1';
// 섹션명 앞 불릿 기호(■ 등) 제거 — 렌더러가 ■ 를 자동으로 붙이므로 LLM 이 넣어 온 ■ 와 중복 방지.
const stripBullet = (s: string): string =>
  s.replace(/^[\s■□▣▪◼◾●○◆◇·•∎]+/, '').trim();
const numv = (v: unknown, fb = 0): number => {
  if (typeof v === 'number') return Number.isFinite(v) ? v : fb;
  const n = parseFloat(String(v ?? '').replace(/[^0-9.eE+-]/g, ''));
  return Number.isFinite(n) ? n : fb;
};

// ── 캔버스 프레임 ────────────────────────────────────────────
function SlideFrame({ children }: { children: ReactNode }) {
  return (
    <div
      style={
        {
          position: 'relative',
          width: '100%',
          aspectRatio: `${CW} / ${CH}`,
          background: C.white,
          containerType: 'inline-size',
          overflow: 'hidden',
          border: `1px solid ${C.hairline}`,
          borderRadius: 3,
          boxShadow: C.previewShadow,
          color: C.bodyTitle,
          fontFamily: FONT_STACK,
        } as CSSProperties
      }
    >
      {children}
    </div>
  );
}

// 실제 두원 로고(빨간 O + 스워시). height 만 지정하면 종횡비 자동.
function Logo({ style }: { style?: CSSProperties }) {
  return (
    <img
      src={LOGO_SRC}
      alt="DOOWON"
      style={{ display: 'block', width: 'auto', ...style }}
    />
  );
}

// 우상단 Confidential 배지 (흰 배경 + 빨간 외곽선). 모든 슬라이드 공통.
function ConfidentialBadge() {
  return (
    <div
      style={{
        position: 'absolute',
        left: X(CW - 4.2 - 0.3),
        top: Y(0.3),
        width: X(4.2),
        height: Y(0.78),
        border: `0.13cqw solid ${C.red}`,
        borderRadius: '0.7cqw',
        background: C.white,
        color: C.red,
        fontWeight: 700,
        fontSize: FT(14),
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        letterSpacing: '0.02cqw',
      }}
    >
      {CONFIDENTIAL_BADGE_TEXT}
    </div>
  );
}

// ── 표지 (build_a4_cover_slide) ──────────────────────────────
function A4CoverSlide({ data }: { data: Dict }) {
  const today = new Date();
  const title = str(data, 'TITLE', '제목 미정');
  const date =
    str(data, 'DATE') ||
    `${today.getFullYear()}.${String(today.getMonth() + 1).padStart(2, '0')}.${String(
      today.getDate(),
    ).padStart(2, '0')}`;
  const author = str(data, 'AUTHOR', '㈜두원공조 기술연구소 AI TFT');
  const version = str(data, 'VERSION', 'Ver 1');
  const abs = (s: CSSProperties): CSSProperties => ({
    position: 'absolute',
    ...s,
  });

  return (
    <SlideFrame>
      {/* 1) 좌상 워터마크 (Arial Bold 20pt, C.coverWatermark) */}
      <div
        style={abs({
          left: X(0.8),
          top: Y(0.45),
          height: Y(0.9),
          display: 'flex',
          alignItems: 'center',
          color: C.coverWatermark,
          fontWeight: 700,
          fontSize: FT(20),
          whiteSpace: 'pre',
          fontFamily: 'Arial, sans-serif',
        })}
      >
        {COVER_WATERMARK_TEXT}
      </div>

      {/* 2) Confidential 배지 */}
      <ConfidentialBadge />

      {/* 3) 제목 (HDharmony Bold 32pt, C.coverTitle) */}
      <div
        style={abs({
          left: X(1.5),
          top: Y(6.2),
          width: X(18.3),
          height: Y(1.8),
          display: 'flex',
          alignItems: 'center',
          color: C.coverTitle,
          fontWeight: 800,
          fontSize: FT(32),
          lineHeight: 1.1,
        })}
      >
        {title}
      </div>

      {/* 4) 긴 회색 밑줄 / 5) 짧은 우측 밑줄 (2pt, C.coverRule) */}
      <div
        style={abs({
          left: X(1.5),
          top: Y(7.95),
          width: X(18.3),
          height: Y(0.071),
          background: C.coverRule,
        })}
      />
      <div
        style={abs({
          left: X(20.2),
          top: Y(7.95),
          width: X(5.2),
          height: Y(0.071),
          background: C.coverRule,
        })}
      />

      {/* 6) Ver 라벨 (HDharmony 16pt, C.verLabel, 짧은 밑줄 위 가운데) */}
      <div
        style={abs({
          left: X(20.2),
          top: Y(6.9),
          width: X(5.2),
          height: Y(0.9),
          display: 'flex',
          alignItems: 'flex-end',
          justifyContent: 'center',
          color: C.verLabel,
          fontSize: FT(16),
        })}
      >
        {version}
      </div>

      {/* 7) 날짜 (HDharmony Bold 22pt, C.coverTitle) */}
      <div
        style={abs({
          left: X(1.5),
          top: Y(11.9),
          width: X(15),
          height: Y(1.2),
          display: 'flex',
          alignItems: 'center',
          color: C.coverTitle,
          fontWeight: 800,
          fontSize: FT(22),
        })}
      >
        {date}
      </div>

      {/* 8) 작성자 (HDharmony Bold 32pt, C.coverTitle) */}
      <div
        style={abs({
          left: X(1.5),
          top: Y(14.2),
          width: X(20),
          height: Y(1.8),
          display: 'flex',
          alignItems: 'center',
          color: C.coverTitle,
          fontWeight: 800,
          fontSize: FT(32),
        })}
      >
        {author}
      </div>

      {/* 9) 우하단 로고 (h=0.69cm) */}
      <Logo style={abs({ right: X(0.3), bottom: Y(0.3), height: Y(0.69) })} />
    </SlideFrame>
  );
}

// ── 본문 공통 chrome (apply_body_chrome) ─────────────────────
function BodyChrome({
  header,
  children,
}: {
  header: string;
  children: ReactNode;
}) {
  const today = new Date();
  const date = `${today.getFullYear()}.${String(today.getMonth() + 1).padStart(2, '0')}.${String(
    today.getDate(),
  ).padStart(2, '0')}`;
  const cleanHeader = header.replace(/^\s*(▣\s*)+/, '');
  const abs = (s: CSSProperties): CSSProperties => ({
    position: 'absolute',
    ...s,
  });

  return (
    <>
      {/* S1 — ▣ 제목 (HDharmony Bold 30pt, C.bodyTitle) */}
      <div
        style={abs({
          left: X(0.7),
          top: Y(0.3),
          width: X(19.5),
          height: Y(1.3),
          display: 'flex',
          alignItems: 'center',
          gap: '0.6cqw',
          color: C.bodyTitle,
          fontWeight: 800,
          fontSize: FT(30),
          whiteSpace: 'nowrap',
          overflow: 'hidden',
        })}
      >
        <span>▣</span>
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {cleanHeader}
        </span>
      </div>

      {/* Confidential 배지 */}
      <ConfidentialBadge />

      {/* L1 — 날짜 (우상, Reg 10pt, C.dateText) */}
      <div
        style={abs({
          left: X(24.5),
          top: Y(1.3),
          width: X(2.45),
          height: Y(0.6),
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'flex-end',
          color: C.dateText,
          fontSize: FT(10),
          whiteSpace: 'nowrap',
        })}
      >
        {date}
      </div>

      {/* L2a / L2b — 분할 가로선 (gap 안 로고) */}
      <div
        style={abs({
          left: 0,
          top: Y(1.85),
          width: X(22.4),
          height: Y(0.106),
          background: C.bodyRule,
        })}
      />
      <div
        style={abs({
          left: X(24.86),
          top: Y(1.85),
          width: X(CW - 24.86),
          height: Y(0.106),
          background: C.bodyRule,
        })}
      />

      {/* L3 — DOOWON 로고 (gap 안). 네이티브 apply_body_chrome 와 동일: x=22.5, top=1.65, h=0.40cm.
          (이전 0.55cm/1.5 는 로고가 커져 우상단 날짜와 겹쳐 'YYYY'가 가려짐) */}
      <Logo style={abs({ left: X(22.5), top: Y(1.65), height: Y(0.4) })} />

      {/* L4 — 사선 DCC 워터마크 (-30°) */}
      <div
        style={abs({
          left: '50%',
          top: '49%',
          transform: 'translate(-50%,-50%) rotate(-30deg)',
          color: C.dccWatermark,
          fontWeight: 700,
          fontSize: FT(32),
          fontFamily: 'Arial, sans-serif',
          whiteSpace: 'nowrap',
          zIndex: 0,
          pointerEvents: 'none',
        })}
      >
        {DCC_WATERMARK_TEXT}
      </div>

      {/* L5 — 하단 영문 저작권 (Arial 7pt, C.copyright) */}
      <div
        style={abs({
          left: X(0.8),
          top: Y(18.5),
          width: X(25.92),
          height: Y(0.45),
          display: 'flex',
          alignItems: 'center',
          color: C.copyright,
          fontSize: FT(7),
          fontFamily: 'Arial, sans-serif',
          whiteSpace: 'nowrap',
          overflow: 'hidden',
        })}
      >
        {COPYRIGHT_TEXT}
      </div>

      {/* 콘텐츠 안전 구역 (가로선 바로 아래 ~ 저작권 위) */}
      <div
        style={abs({
          left: X(0.8),
          right: X(0.8),
          top: Y(2.1),
          bottom: Y(0.9),
          zIndex: 1,
          display: 'flex',
          flexDirection: 'column',
          gap: '1.3cqw',
          overflow: 'hidden',
        })}
      >
        {children}
      </div>
    </>
  );
}

function SectionTitle({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '0.8cqw',
        marginBottom: '0.7cqw',
      }}
    >
      <span
        style={{
          width: '0.5cqw',
          height: '1.8cqw',
          background: C.navy,
          borderRadius: 1,
        }}
      />
      <span style={{ color: C.navy, fontWeight: 700, fontSize: '1.7cqw' }}>
        {children}
      </span>
    </div>
  );
}

function Chip({ text, bg, fg }: { text: string; bg: string; fg: string }) {
  return (
    <span
      style={{
        background: bg,
        color: fg,
        fontSize: '1.15cqw',
        fontWeight: 700,
        padding: '0.25cqw 0.9cqw',
        borderRadius: '1cqw',
        whiteSpace: 'nowrap',
      }}
    >
      {text}
    </span>
  );
}

// ── KPI 대시보드 (build_a4_exec_kpi_slide) ──────────────────
function A4ExecKpiSlide({ data }: { data: Dict }) {
  const kpis = arr(data, 'KPIS').slice(0, 4);
  while (kpis.length < 4)
    kpis.push({ label: `KPI ${kpis.length + 1}`, value: '—' });
  const summary = arr(data, 'SUMMARY_ITEMS').map((x) => String(x));
  const labels = arr(data, 'CHART_LABELS').map((x) => String(x));
  const values = arr(data, 'CHART_VALUES').map((x) => numv(x));
  const maxV = Math.max(1, ...values);
  const issues = arr(data, 'ISSUES').slice(0, 4);
  const actions = arr(data, 'ACTIONS').slice(0, 4);
  const sevColor = (sev: string) =>
    sev === 'HIGH' ? C.red : sev === 'MID' ? C.amber : C.navy;

  return (
    <SlideFrame>
      <BodyChrome header={str(data, 'HEADER', '경영회의 보고서')}>
        {/* KPI 카드 */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(4,1fr)',
            gap: '1cqw',
          }}
        >
          {kpis.map((k, i) => {
            const up = truthy(k.up);
            return (
              <div
                key={i}
                style={{
                  background: C.surfaceSoft,
                  border: `1px solid ${C.hairline}`,
                  borderRadius: '0.8cqw',
                  padding: '1cqw 1.1cqw',
                }}
              >
                <div
                  style={{
                    color: C.muted,
                    fontSize: '1.2cqw',
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}
                >
                  {str(k, 'label')}
                </div>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'baseline',
                    gap: '0.4cqw',
                    marginTop: '0.4cqw',
                  }}
                >
                  <span
                    style={{ color: C.navy, fontWeight: 800, fontSize: '3cqw' }}
                  >
                    {str(k, 'value', '—')}
                  </span>
                  <span style={{ color: C.muted, fontSize: '1.2cqw' }}>
                    {str(k, 'unit')}
                  </span>
                </div>
                <div
                  style={{
                    marginTop: '0.3cqw',
                    color: up ? C.navy : C.red,
                    fontSize: '1.3cqw',
                    fontWeight: 700,
                  }}
                >
                  {str(k, 'delta')}{' '}
                  <span
                    style={{
                      color: C.muted,
                      fontWeight: 400,
                      fontSize: '1.05cqw',
                    }}
                  >
                    {str(k, 'vs')}
                  </span>
                </div>
              </div>
            );
          })}
        </div>

        {/* 요약 + 차트 */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: '1.6cqw',
            flex: 1,
            minHeight: 0,
          }}
        >
          <div
            style={{
              background: C.surfaceSoft,
              border: `1px solid ${C.hairline}`,
              borderRadius: '0.8cqw',
              padding: '1.1cqw 1.3cqw',
              overflow: 'hidden',
            }}
          >
            <SectionTitle>
              {str(data, 'SUMMARY_TITLE', '핵심 요약')}
            </SectionTitle>
            <ul
              style={{
                margin: 0,
                padding: 0,
                listStyle: 'none',
                display: 'flex',
                flexDirection: 'column',
                gap: '0.7cqw',
              }}
            >
              {summary.map((it, i) => (
                <li
                  key={i}
                  style={{
                    display: 'flex',
                    gap: '0.7cqw',
                    fontSize: '1.35cqw',
                    lineHeight: 1.4,
                  }}
                >
                  <span style={{ color: C.red }}>•</span>
                  <span>{it}</span>
                </li>
              ))}
            </ul>
          </div>
          <div
            style={{
              background: C.surfaceSoft,
              border: `1px solid ${C.hairline}`,
              borderRadius: '0.8cqw',
              padding: '1.1cqw 1.3cqw',
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            <SectionTitle>{str(data, 'CHART_TITLE', '월별 추이')}</SectionTitle>
            <div
              style={{
                flex: 1,
                display: 'flex',
                alignItems: 'flex-end',
                gap: '1.2cqw',
                paddingTop: '0.8cqw',
              }}
            >
              {labels.map((lb, i) => (
                <div
                  key={i}
                  style={{
                    flex: 1,
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    gap: '0.4cqw',
                  }}
                >
                  <div
                    style={{ color: C.navy, fontSize: '1cqw', fontWeight: 700 }}
                  >
                    {values[i] ?? ''}
                  </div>
                  <div
                    style={{
                      width: '70%',
                      height: `${Math.max(4, ((values[i] ?? 0) / maxV) * 100)}%`,
                      background: C.navy,
                      borderRadius: '0.3cqw',
                    }}
                  />
                  <div style={{ color: C.muted, fontSize: '1.05cqw' }}>
                    {lb}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* 이슈 + 액션 */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: '1.6cqw',
          }}
        >
          <div>
            <SectionTitle>
              {str(data, 'ISSUES_TITLE', '주요 이슈')}
            </SectionTitle>
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: '0.6cqw',
              }}
            >
              {issues.map((it, i) => (
                <div
                  key={i}
                  style={{
                    display: 'flex',
                    gap: '0.8cqw',
                    alignItems: 'center',
                  }}
                >
                  <Chip
                    text={str(it, 'sev', 'LOW')}
                    bg={sevColor(str(it, 'sev'))}
                    fg={C.white}
                  />
                  <span style={{ fontSize: '1.3cqw', fontWeight: 700 }}>
                    {str(it, 'title')}
                  </span>
                  <span
                    style={{
                      fontSize: '1.15cqw',
                      color: C.muted,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {str(it, 'desc')}
                  </span>
                </div>
              ))}
            </div>
          </div>
          <div>
            <SectionTitle>
              {str(data, 'ACTIONS_TITLE', '차월 액션 아이템')}
            </SectionTitle>
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: '0.6cqw',
              }}
            >
              {actions.map((it, i) => (
                <div
                  key={i}
                  style={{
                    display: 'flex',
                    gap: '0.8cqw',
                    alignItems: 'baseline',
                  }}
                >
                  <span
                    style={{
                      color: C.navy,
                      fontWeight: 800,
                      fontSize: '1.4cqw',
                    }}
                  >
                    {str(it, 'num', String(i + 1).padStart(2, '0'))}
                  </span>
                  <span style={{ fontSize: '1.3cqw', fontWeight: 700 }}>
                    {str(it, 'title')}
                  </span>
                  <span style={{ fontSize: '1.1cqw', color: C.muted }}>
                    {str(it, 'owner')}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </BodyChrome>
    </SlideFrame>
  );
}

// ── 사업부 스코어카드 (build_a4_scorecard_slide) ─────────────
function A4ScorecardSlide({ data }: { data: Dict }) {
  const { t } = useTranslation('apps');
  const agg = arr(data, 'AGG_KPIS').slice(0, 3);
  const divs = arr(data, 'DIVISIONS');
  const issues = arr(data, 'ISSUES').slice(0, 3);
  const decisions = arr(data, 'DECISIONS').slice(0, 3);
  const statusChip = (st: string) =>
    st === 'good'
      ? { t: '양호', bg: C.statusGoodBg, fg: C.green }
      : st === 'bad'
        ? { t: '부진', bg: C.statusBadBg, fg: C.red }
        : { t: '주의', bg: C.statusWarnBg, fg: C.amber };
  const GRID = '1.4fr 1fr 1fr 1.6fr 1fr 0.9fr';

  return (
    <SlideFrame>
      <BodyChrome header={str(data, 'HEADER', '사업부별 실적 스코어카드')}>
        {/* 헤드라인 + 집계 KPI */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1.6fr 1fr',
            gap: '1.4cqw',
          }}
        >
          <div
            style={{
              background: C.navy,
              color: C.white,
              borderRadius: '0.8cqw',
              padding: '1.2cqw 1.6cqw',
            }}
          >
            <div
              style={{
                color: C.navySubtle,
                fontSize: '1.1cqw',
                letterSpacing: '0.2cqw',
                fontWeight: 700,
              }}
            >
              {str(data, 'HEADLINE_EYEBROW', 'EXECUTIVE HEADLINE')}
            </div>
            <div
              style={{
                fontSize: '2.2cqw',
                fontWeight: 800,
                lineHeight: 1.25,
                marginTop: '0.5cqw',
              }}
            >
              {str(data, 'HEADLINE_MAIN', '한 줄 결론')}
            </div>
            <div
              style={{
                fontSize: '1.3cqw',
                opacity: 0.85,
                marginTop: '0.6cqw',
                lineHeight: 1.4,
              }}
            >
              {str(data, 'HEADLINE_SUB')}
            </div>
          </div>
          <div
            style={{ display: 'flex', flexDirection: 'column', gap: '0.7cqw' }}
          >
            {agg.map((k, i) => {
              const up = truthy(k.up);
              return (
                <div
                  key={i}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    background: C.surfaceSoft,
                    border: `1px solid ${C.hairline}`,
                    borderRadius: '0.7cqw',
                    padding: '0.6cqw 1cqw',
                  }}
                >
                  <span style={{ color: C.muted, fontSize: '1.2cqw' }}>
                    {str(k, 'label')}
                  </span>
                  <span
                    style={{
                      display: 'flex',
                      alignItems: 'baseline',
                      gap: '0.4cqw',
                    }}
                  >
                    <span
                      style={{
                        color: C.navy,
                        fontWeight: 800,
                        fontSize: '1.9cqw',
                      }}
                    >
                      {str(k, 'value')}
                    </span>
                    <span style={{ color: C.muted, fontSize: '1cqw' }}>
                      {str(k, 'unit')}
                    </span>
                    <span
                      style={{
                        color: up ? C.navy : C.red,
                        fontSize: '1.1cqw',
                        fontWeight: 700,
                      }}
                    >
                      {str(k, 'delta')}
                    </span>
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* 부문 테이블 */}
        <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: GRID,
              background: C.coolMist,
              color: C.navy,
              fontWeight: 700,
              fontSize: '1.15cqw',
              padding: '0.6cqw 1cqw',
              borderRadius: '0.5cqw 0.5cqw 0 0',
            }}
          >
            <span>부문</span>
            <span style={{ textAlign: 'right' }}>계획</span>
            <span style={{ textAlign: 'right' }}>실적</span>
            <span style={{ paddingLeft: '1cqw' }}>
              {t('ai.pptGenerator.renderer.achievementRate')}
            </span>
            <span style={{ textAlign: 'right' }}>증감</span>
            <span style={{ textAlign: 'center' }}>상태</span>
          </div>
          {divs.map((d, i) => {
            const plan = numv(d.plan);
            const actual = numv(d.actual);
            const rate = plan > 0 ? Math.min(120, (actual / plan) * 100) : 0;
            const up = truthy(d.delta_up);
            const bold = truthy(d.bold);
            const sc = statusChip(str(d, 'status', 'warn'));
            return (
              <div
                key={i}
                style={{
                  display: 'grid',
                  gridTemplateColumns: GRID,
                  alignItems: 'center',
                  padding: '0.55cqw 1cqw',
                  borderBottom: `1px solid ${C.hairline}`,
                  background: bold ? C.surface : C.white,
                  fontWeight: bold ? 700 : 400,
                  fontSize: '1.25cqw',
                }}
              >
                <span style={{ color: bold ? C.navy : C.bodyTitle }}>
                  {str(d, 'name')}
                </span>
                <span style={{ textAlign: 'right' }}>
                  {plan ? plan.toLocaleString() : str(d, 'plan')}
                </span>
                <span style={{ textAlign: 'right' }}>
                  {actual ? actual.toLocaleString() : str(d, 'actual')}
                </span>
                <span
                  style={{
                    paddingLeft: '1cqw',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.6cqw',
                  }}
                >
                  <span
                    style={{
                      flex: 1,
                      height: '0.9cqw',
                      background: C.track,
                      borderRadius: '0.5cqw',
                      overflow: 'hidden',
                    }}
                  >
                    <span
                      style={{
                        display: 'block',
                        width: `${rate}%`,
                        height: '100%',
                        background: rate >= 100 ? C.navy : C.amber,
                      }}
                    />
                  </span>
                  <span style={{ fontSize: '1.05cqw', color: C.muted }}>
                    {Math.round(rate)}%
                  </span>
                </span>
                <span
                  style={{
                    textAlign: 'right',
                    color: up ? C.navy : C.red,
                    fontWeight: 700,
                  }}
                >
                  {str(d, 'delta')}
                </span>
                <span style={{ textAlign: 'center' }}>
                  <Chip text={sc.t} bg={sc.bg} fg={sc.fg} />
                </span>
              </div>
            );
          })}
        </div>

        {/* 이슈 + 의사결정 */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: '1.6cqw',
          }}
        >
          <div>
            <SectionTitle>
              {str(data, 'ISSUES_TITLE', '핵심 이슈 · 위험 신호')}
            </SectionTitle>
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: '0.5cqw',
              }}
            >
              {issues.map((it, i) => (
                <div
                  key={i}
                  style={{
                    display: 'flex',
                    gap: '0.7cqw',
                    alignItems: 'baseline',
                    fontSize: '1.2cqw',
                  }}
                >
                  <span
                    style={{
                      color: C.red,
                      fontWeight: 700,
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {str(it, 'div')}
                  </span>
                  <span style={{ fontWeight: 700 }}>{str(it, 'title')}</span>
                  <span
                    style={{
                      color: C.muted,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {str(it, 'desc')}
                  </span>
                </div>
              ))}
            </div>
          </div>
          <div>
            <SectionTitle>
              {str(data, 'DECISIONS_TITLE', '차월 의사결정 사항')}
            </SectionTitle>
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: '0.5cqw',
              }}
            >
              {decisions.map((it, i) => (
                <div
                  key={i}
                  style={{
                    display: 'flex',
                    gap: '0.7cqw',
                    alignItems: 'baseline',
                    fontSize: '1.2cqw',
                  }}
                >
                  <span style={{ color: C.navy }}>Q.</span>
                  <span style={{ flex: 1 }}>{str(it, 'q')}</span>
                  <span style={{ color: C.muted, whiteSpace: 'nowrap' }}>
                    {str(it, 'owner')}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </BodyChrome>
    </SlideFrame>
  );
}

// ── 경영회의 회의록 (build_a4_minutes_slide) ─────────────────
function A4MeetingMinutesSlide({ data }: { data: Dict }) {
  const { t } = useTranslation('apps');
  const meta = arr(data, 'META_ITEMS').slice(0, 4);
  const agendas = arr(data, 'AGENDAS').slice(0, 3);
  const items = arr(data, 'ACTION_ITEMS');
  const statusChip = (st: string) =>
    st === 'done'
      ? { t: '완료', bg: C.statusGoodBg, fg: C.green }
      : st === 'in_progress'
        ? { t: '진행', bg: C.coolMist, fg: C.navy }
        : { t: '예정', bg: C.statusWarnBg, fg: C.amber };
  const GRID = '0.5fr 2.6fr 1fr 1fr 0.8fr';

  return (
    <SlideFrame>
      <BodyChrome header={str(data, 'HEADER', '경영회의 회의록')}>
        {/* 메타 */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(4,1fr)',
            gap: '0.8cqw',
          }}
        >
          {meta.map((m, i) => (
            <div
              key={i}
              style={{
                background: C.surfaceSoft,
                border: `1px solid ${C.hairline}`,
                borderRadius: '0.6cqw',
                padding: '0.6cqw 0.9cqw',
              }}
            >
              <div
                style={{ color: C.navy, fontSize: '1.05cqw', fontWeight: 700 }}
              >
                {str(m, 'label')}
              </div>
              <div
                style={{
                  fontSize: '1.2cqw',
                  marginTop: '0.2cqw',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}
              >
                {str(m, 'value')}
              </div>
            </div>
          ))}
        </div>

        {/* 안건 */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3,1fr)',
            gap: '1cqw',
            flex: 1,
            minHeight: 0,
          }}
        >
          {agendas.map((a, i) => (
            <div
              key={i}
              style={{
                background: C.surfaceSoft,
                border: `1px solid ${C.hairline}`,
                borderRadius: '0.7cqw',
                padding: '1cqw 1.1cqw',
                display: 'flex',
                flexDirection: 'column',
                overflow: 'hidden',
              }}
            >
              <div
                style={{ display: 'flex', alignItems: 'center', gap: '0.6cqw' }}
              >
                <span
                  style={{
                    color: C.white,
                    background: C.navy,
                    fontSize: '1.1cqw',
                    fontWeight: 800,
                    borderRadius: '0.4cqw',
                    padding: '0.15cqw 0.7cqw',
                  }}
                >
                  {str(a, 'num', String(i + 1).padStart(2, '0'))}
                </span>
                <span
                  style={{
                    fontWeight: 700,
                    fontSize: '1.4cqw',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {str(a, 'title')}
                </span>
              </div>
              <div
                style={{
                  fontSize: '1.15cqw',
                  color: C.bodyTitle,
                  marginTop: '0.6cqw',
                  lineHeight: 1.4,
                  flex: 1,
                  overflow: 'hidden',
                }}
              >
                {str(a, 'discussion')}
              </div>
              <div
                style={{
                  fontSize: '1.15cqw',
                  marginTop: '0.6cqw',
                  borderTop: `1px dashed ${C.hairline}`,
                  paddingTop: '0.5cqw',
                }}
              >
                <span style={{ color: C.red, fontWeight: 700 }}>결정 </span>
                {str(a, 'decision')}
              </div>
            </div>
          ))}
        </div>

        {/* 액션 아이템 테이블 */}
        <div>
          <SectionTitle>
            {t('ai.pptGenerator.renderer.actionItems')}
          </SectionTitle>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: GRID,
              background: C.coolMist,
              color: C.navy,
              fontWeight: 700,
              fontSize: '1.1cqw',
              padding: '0.45cqw 0.9cqw',
              borderRadius: '0.4cqw 0.4cqw 0 0',
            }}
          >
            <span>No</span>
            <span>{t('ai.pptGenerator.renderer.actionItems')}</span>
            <span>담당</span>
            <span>기한</span>
            <span style={{ textAlign: 'center' }}>상태</span>
          </div>
          {items.map((it, i) => {
            const sc = statusChip(str(it, 'status', 'planned'));
            return (
              <div
                key={i}
                style={{
                  display: 'grid',
                  gridTemplateColumns: GRID,
                  alignItems: 'center',
                  padding: '0.45cqw 0.9cqw',
                  borderBottom: `1px solid ${C.hairline}`,
                  fontSize: '1.2cqw',
                }}
              >
                <span style={{ color: C.muted }}>
                  {str(it, 'no', String(i + 1))}
                </span>
                <span
                  style={{
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {str(it, 'task')}
                </span>
                <span>{str(it, 'owner')}</span>
                <span style={{ color: C.muted }}>{str(it, 'due')}</span>
                <span style={{ textAlign: 'center' }}>
                  <Chip text={sc.t} bg={sc.bg} fg={sc.fg} />
                </span>
              </div>
            );
          })}
        </div>

        {/* 푸터 */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            gap: '1cqw',
            fontSize: '1.15cqw',
          }}
        >
          <span>
            <span style={{ color: C.navy, fontWeight: 700 }}>다음 회의 </span>{/* i18n-exempt-line: fixed PPT template copy */}
            {str(data, 'NEXT_MEETING')}
          </span>{' '}
          <span style={{ color: C.muted, whiteSpace: 'nowrap' }}>
            {str(data, 'SIGNOFF')}
          </span>
        </div>
      </BodyChrome>
    </SlideFrame>
  );
}

// ════════════════════════════════════════════════════════════
// 자유 양식 — Brandlogy 27 × 16.75 cm 자유배치
// builders_brandlogy.py 와 좌표·색상·컴포넌트 1:1 대응.
// ════════════════════════════════════════════════════════════
const BL_CW = 27.0;
const BL_CH = 16.75;
const BX = (cm: number) => `${((cm / BL_CW) * 100).toFixed(3)}%`;
const BY = (cm: number) => `${((cm / BL_CH) * 100).toFixed(3)}%`;
// pt → cqw (1pt=0.03528cm, 폭 27cm 기준)
const BFT = (pt: number) => `${(pt * 0.130667).toFixed(3)}cqw`;
const BL_FONT =
  "'Pretendard','Pretendard Variable',-apple-system,system-ui,sans-serif";

const BL = {
  ink: '#222222',
  sub: '#45515e',
  mute: '#8e8e93',
  blue: '#1456f0',
  blue2: '#3b82f6',
  blue3: '#60a5fa',
  pink: '#ea5ec1',
  border: '#e5e7eb',
  borderSoft: '#f2f3f5',
  white: '#ffffff',
  whiteShort: '#fff',
  dark: '#181e25',
  darkText: '#18181b',
  featuredLabel: '#e8efff',
  highlightBg: '#eff5ff',
  darkSub: '#cdd6e0',
  blueSoft: '#bfdbfe',
  glowShadow: '0 0 15px rgba(44,30,116,0.16)',
  standardShadow: '0 4px 6px rgba(0,0,0,0.08)',
  previewShadow: '0 1px 4px rgba(0,0,0,.10)',
} as const;
const BL_GRADIENT = `linear-gradient(135deg,${BL.blue} 0%,${BL.blue2} 50%,${BL.blue3} 100%)`;
const BL_SERIES = [BL.blue2, BL.blue3, BL.blue, BL.blueSoft, BL.pink, BL.mute];

// 본문 박스 잠금 좌표
const BB = { x0: 0.9, y0: 3.68, x1: 26.1, y1: 16.05 } as const;

const blShadow = (s?: string): string | undefined =>
  s === 'glow'
    ? BL.glowShadow
    : s === 'standard'
      ? BL.standardShadow
      : undefined;

// 본문 박스 안으로 보정 (builders_brandlogy._clamp 와 동일)
function blClamp(el: Dict) {
  let x = numv(el.x, BB.x0);
  let y = numv(el.y, BB.y0);
  let w = numv(el.w, 6);
  let h = numv(el.h, 2);
  x = Math.max(BB.x0, Math.min(x, BB.x1 - 0.5));
  y = Math.max(BB.y0, Math.min(y, BB.y1 - 0.5));
  w = Math.max(0.5, Math.min(w, BB.x1 - x));
  h = Math.max(0.3, Math.min(h, BB.y1 - y));
  return { x, y, w, h };
}

const blBox = (x: number, y: number, w: number, h: number): CSSProperties => ({
  position: 'absolute',
  left: BX(x),
  top: BY(y),
  width: BX(w),
  height: BY(h),
});

// ── element: text ────────────────────────────────────────────
function BlText({ el, dark }: { el: Dict; dark: boolean }) {
  const { x, y, w, h } = blClamp(el);
  const fill = str(el, 'FILL');
  const hasCard = !!fill;
  const pad = numv(el.PAD, hasCard ? 0.4 : 0);
  const color = str(el, 'COLOR') || (dark && !hasCard ? BL.white : BL.ink);
  const align =
    (str(el, 'ALIGN', 'left') as CSSProperties['textAlign']) || 'left';
  const valign = str(el, 'VALIGN', 'top');
  return (
    <div
      style={{
        ...blBox(x, y, w, h),
        background: hasCard ? fill : undefined,
        border: el.BORDER ? `0.08cqw solid ${str(el, 'BORDER')}` : undefined,
        borderRadius: hasCard ? `${numv(el.RADIUS, 13) / 4}cqw` : undefined,
        boxShadow: hasCard ? blShadow(str(el, 'SHADOW')) : undefined,
        padding: `${(pad / BL_CH) * 100}% ${(pad / BL_CW) * 100}%`,
        boxSizing: 'border-box',
        display: 'flex',
        flexDirection: 'column',
        justifyContent:
          valign === 'middle'
            ? 'center'
            : valign === 'bottom'
              ? 'flex-end'
              : 'flex-start',
        color,
        fontSize: BFT(numv(el.SIZE, 11)),
        fontWeight: numv(el.WEIGHT, 400),
        lineHeight: numv(el.LINE_HEIGHT, 1.45),
        whiteSpace: 'pre-wrap',
        overflow: 'hidden',
        textAlign: align,
      }}
    >
      {str(el, 'TEXT')}
    </div>
  );
}

// ── element: kpi ─────────────────────────────────────────────
function BlKpi({ el }: { el: Dict }) {
  const { x, y, w, h } = blClamp(el);
  const featured = truthy(el.FEATURED);
  const up = el.UP === undefined ? true : truthy(el.UP);
  const valC = featured ? BL.white : BL.blue;
  const lblC = featured ? BL.featuredLabel : BL.sub;
  const deltaC = featured ? BL.white : up ? BL.blue : BL.pink;
  return (
    <div
      style={{
        ...blBox(x, y, w, h),
        background: featured ? BL_GRADIENT : BL.white,
        border: featured ? undefined : `0.08cqw solid ${BL.border}`,
        borderRadius: featured ? '1.6cqw' : '1cqw',
        boxShadow: featured ? blShadow('glow') : blShadow('standard'),
        padding: '1.1cqw 1.3cqw',
        boxSizing: 'border-box',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          color: lblC,
          fontSize: BFT(10.5),
          fontWeight: 500,
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
        }}
      >
        {str(el, 'LABEL')}
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.4cqw' }}>
        <span
          style={{
            color: valC,
            fontWeight: 700,
            fontSize: BFT(30),
            lineHeight: 1.05,
          }}
        >
          {str(el, 'VALUE')}
        </span>
        {el.UNIT ? (
          <span
            style={{
              color: featured ? BL.white : BL.sub,
              fontSize: BFT(13),
              fontWeight: 500,
            }}
          >
            {str(el, 'UNIT')}
          </span>
        ) : null}
      </div>
      {el.DELTA ? (
        <div style={{ color: deltaC, fontWeight: 700, fontSize: BFT(11) }}>
          {str(el, 'DELTA')}
        </div>
      ) : (
        <div />
      )}
    </div>
  );
}

// ── element: pill ────────────────────────────────────────────
function BlPill({ el }: { el: Dict }) {
  const { x, y, w, h } = blClamp(el);
  const style = str(el, 'STYLE', 'light').toLowerCase();
  const bg =
    style === 'dark' ? BL.dark : style === 'nav' ? BL.borderSoft : BL.white;
  const fg = style === 'dark' ? BL.white : BL.darkText;
  return (
    <div
      style={{
        ...blBox(x, y, w, h),
        background: bg,
        border: style === 'dark' ? undefined : `0.08cqw solid ${BL.border}`,
        borderRadius: '999px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: fg,
        fontWeight: 600,
        fontSize: BFT(10),
        whiteSpace: 'nowrap',
        overflow: 'hidden',
      }}
    >
      {str(el, 'TEXT')}
    </div>
  );
}

// ── element: divider ─────────────────────────────────────────
function BlDivider({ el }: { el: Dict }) {
  const { x, y, w } = blClamp(el);
  return (
    <div
      style={{
        ...blBox(x, y, w, 0.04),
        background: str(el, 'COLOR') || BL.border,
      }}
    />
  );
}

// ── element: bullets ─────────────────────────────────────────
function BlBullets({ el, dark }: { el: Dict; dark: boolean }) {
  const { x, y, w, h } = blClamp(el);
  const fill = str(el, 'FILL');
  const hasCard = !!fill;
  const items = arr(el, 'ITEMS')
    .map((i) => String(i))
    .slice(0, 8);
  const size = numv(el.SIZE, 11);
  const txtC = dark && !hasCard ? BL.white : BL.ink;
  return (
    <div
      style={{
        ...blBox(x, y, w, h),
        background: hasCard ? fill : undefined,
        border:
          hasCard && fill.toLowerCase().startsWith(BL.whiteShort)
            ? `0.08cqw solid ${BL.border}`
            : undefined,
        borderRadius: hasCard ? `${numv(el.RADIUS, 13) / 4}cqw` : undefined,
        boxShadow: hasCard ? blShadow(str(el, 'SHADOW')) : undefined,
        padding: hasCard ? '1.1cqw 1.3cqw' : 0,
        boxSizing: 'border-box',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      {el.TITLE ? (
        <div
          style={{
            fontWeight: 600,
            fontSize: BFT(14),
            color: txtC,
            marginBottom: '0.6cqw',
          }}
        >
          {str(el, 'TITLE')}
        </div>
      ) : null}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5cqw' }}>
        {items.map((it, i) => (
          <div
            key={i}
            style={{
              display: 'flex',
              gap: '0.6cqw',
              fontSize: BFT(size),
              lineHeight: 1.35,
              color: txtC,
            }}
          >
            <span style={{ color: BL.blue, fontWeight: 700 }}>•</span>
            <span>{it}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── element: steps ───────────────────────────────────────────
function BlSteps({ el }: { el: Dict }) {
  const { x, y, w, h } = blClamp(el);
  const items = arr(el, 'ITEMS').slice(0, 6);
  return (
    <div
      style={{
        ...blBox(x, y, w, h),
        display: 'grid',
        gridTemplateColumns: `repeat(${Math.max(1, items.length)},1fr)`,
        gap: '0.4cqw',
      }}
    >
      {items.map((it, i) => (
        <div
          key={i}
          style={{
            background: BL.white,
            border: `0.08cqw solid ${BL.border}`,
            borderRadius: '1cqw',
            boxShadow: blShadow('standard'),
            padding: '0.8cqw 0.9cqw',
            display: 'flex',
            flexDirection: 'column',
            gap: '0.5cqw',
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              width: '2.6cqw',
              height: '2.6cqw',
              borderRadius: '50%',
              background: BL.blue,
              color: BL.white,
              fontWeight: 700,
              fontSize: BFT(14),
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            {i + 1}
          </div>
          <div style={{ fontWeight: 600, fontSize: BFT(12.5), color: BL.ink }}>
            {str(it, 'LABEL')}
          </div>
          <div style={{ fontSize: BFT(10), color: BL.sub, lineHeight: 1.35 }}>
            {str(it, 'BODY')}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── element: table ───────────────────────────────────────────
function BlTable({ el }: { el: Dict }) {
  const { x, y, w, h } = blClamp(el);
  const columns = arr(el, 'COLUMNS').map((c) => String(c));
  const rows = arr(el, 'ROWS');
  if (!columns.length) return null;
  const hl = numv(el.HIGHLIGHT_ROW, -1);
  const grid = `repeat(${columns.length},1fr)`;
  return (
    <div
      style={{ ...blBox(x, y, w, h), overflow: 'hidden', fontSize: BFT(11) }}
    >
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: grid,
          background: BL.borderSoft,
          color: BL.ink,
          fontWeight: 600,
          padding: '0.5cqw 0.7cqw',
          borderRadius: '0.5cqw 0.5cqw 0 0',
        }}
      >
        {columns.map((c, i) => (
          <span key={i} style={{ textAlign: i === 0 ? 'left' : 'center' }}>
            {c}
          </span>
        ))}
      </div>
      {rows.map((row, r) => {
        const cells = Array.isArray(row) ? (row as unknown[]) : [row];
        const isHl = r === hl;
        return (
          <div
            key={r}
            style={{
              display: 'grid',
              gridTemplateColumns: grid,
              padding: '0.45cqw 0.7cqw',
              borderBottom: `0.06cqw solid ${BL.border}`,
              background: isHl ? BL.highlightBg : BL.white,
              color: isHl ? BL.blue : BL.ink,
              fontWeight: isHl ? 600 : 400,
            }}
          >
            {columns.map((_, c) => (
              <span
                key={c}
                style={{
                  textAlign: c === 0 ? 'left' : 'center',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {String(cells[c] ?? '')}
              </span>
            ))}
          </div>
        );
      })}
    </div>
  );
}

// ── element: chart ───────────────────────────────────────────
function BlChart({ el }: { el: Dict }) {
  const { x, y, w, h } = blClamp(el);
  const kind = str(el, 'CHART', 'bar').toLowerCase();
  const labels = arr(el, 'LABELS').map((l) => String(l));
  const series = arr(el, 'SERIES');
  const title = str(el, 'TITLE');
  const source = str(el, 'SOURCE');
  const colorFor = (i: number) =>
    str(series[i] || {}, 'color') || BL_SERIES[i % BL_SERIES.length];
  const seriesVals = series.map((s) =>
    arr({ v: s.values } as Dict, 'v').map((v) => numv(v)),
  );
  const allVals = seriesVals.flat();
  const maxV = Math.max(1, ...allVals);

  return (
    <div
      style={{
        ...blBox(x, y, w, h),
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      {title ? (
        <div
          style={{
            fontWeight: 600,
            fontSize: BFT(14),
            color: BL.ink,
            marginBottom: '0.5cqw',
          }}
        >
          {title}
        </div>
      ) : null}
      <div
        style={{
          flex: 1,
          minHeight: 0,
          display: 'flex',
          alignItems: kind === 'hbar' ? 'stretch' : 'flex-end',
          gap: '0.8cqw',
        }}
      >
        {kind === 'donut' ? (
          <BlDonut
            values={seriesVals[0] || []}
            labels={labels}
            colorFor={colorFor}
          />
        ) : kind === 'line' ? (
          <BlLine
            seriesVals={seriesVals}
            labels={labels}
            maxV={maxV}
            colorFor={colorFor}
          />
        ) : kind === 'hbar' ? (
          <div
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'center',
              gap: '0.5cqw',
            }}
          >
            {(seriesVals[0] || []).map((v, i) => (
              <div
                key={i}
                style={{ display: 'flex', alignItems: 'center', gap: '0.6cqw' }}
              >
                <span
                  style={{
                    width: '20%',
                    fontSize: BFT(10),
                    color: BL.sub,
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}
                >
                  {labels[i] ?? ''}
                </span>
                <span
                  style={{
                    flex: 1,
                    height: '1.6cqw',
                    background: BL.borderSoft,
                    borderRadius: '0.3cqw',
                    overflow: 'hidden',
                  }}
                >
                  <span
                    style={{
                      display: 'block',
                      width: `${(v / maxV) * 100}%`,
                      height: '100%',
                      background: colorFor(0),
                    }}
                  />
                </span>
                <span
                  style={{ fontSize: BFT(10), color: BL.ink, fontWeight: 600 }}
                >
                  {v}
                </span>
              </div>
            ))}
          </div>
        ) : (
          labels.map((lb, i) => (
            <div
              key={i}
              style={{
                flex: 1,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'flex-end',
                gap: '0.4cqw',
                height: '100%',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'flex-end',
                  gap: '0.2cqw',
                  height: '100%',
                  width: '100%',
                  justifyContent: 'center',
                }}
              >
                {seriesVals.map((sv, si) => (
                  <div
                    key={si}
                    title={`${sv[i] ?? ''}`}
                    style={{
                      width: `${70 / Math.max(1, seriesVals.length)}%`,
                      height: `${Math.max(2, ((sv[i] ?? 0) / maxV) * 100)}%`,
                      background: colorFor(si),
                      borderRadius: '0.3cqw 0.3cqw 0 0',
                    }}
                  />
                ))}
              </div>
              <div
                style={{
                  color: BL.sub,
                  fontSize: BFT(9.5),
                  whiteSpace: 'nowrap',
                }}
              >
                {lb}
              </div>
            </div>
          ))
        )}
      </div>
      {source ? (
        <div style={{ color: BL.mute, fontSize: BFT(9), marginTop: '0.4cqw' }}>
          {source}
        </div>
      ) : null}
    </div>
  );
}

function BlLine({
  seriesVals,
  labels,
  maxV,
  colorFor,
}: {
  seriesVals: number[][];
  labels: string[];
  maxV: number;
  colorFor: (i: number) => string;
}) {
  const n = Math.max(1, labels.length || (seriesVals[0]?.length ?? 1));
  return (
    <div style={{ flex: 1, position: 'relative' }}>
      <svg
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        style={{ width: '100%', height: '100%' }}
      >
        {seriesVals.map((sv, si) => {
          const pts = sv
            .map(
              (v, i) =>
                `${(i / Math.max(1, n - 1)) * 100},${100 - (v / maxV) * 95}`,
            )
            .join(' ');
          return (
            <polyline
              key={si}
              points={pts}
              fill="none"
              stroke={colorFor(si)}
              strokeWidth={1.5}
              vectorEffect="non-scaling-stroke"
            />
          );
        })}
      </svg>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          marginTop: '0.3cqw',
        }}
      >
        {labels.map((lb, i) => (
          <span key={i} style={{ fontSize: BFT(9.5), color: BL.sub }}>
            {lb}
          </span>
        ))}
      </div>
    </div>
  );
}

function BlDonut({
  values,
  labels,
  colorFor,
}: {
  values: number[];
  labels: string[];
  colorFor: (i: number) => string;
}) {
  const total = values.reduce((a, b) => a + b, 0) || 1;
  let acc = 0;
  const stops = values.map((v, i) => {
    const start = (acc / total) * 360;
    acc += v;
    const end = (acc / total) * 360;
    return `${colorFor(i)} ${start}deg ${end}deg`;
  });
  return (
    <div
      style={{ flex: 1, display: 'flex', alignItems: 'center', gap: '1cqw' }}
    >
      <div
        style={{
          width: '60%',
          aspectRatio: '1',
          borderRadius: '50%',
          background: `conic-gradient(${stops.join(',')})`,
          position: 'relative',
        }}
      >
        <div
          style={{
            position: 'absolute',
            inset: '28%',
            borderRadius: '50%',
            background: BL.white,
          }}
        />
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4cqw' }}>
        {labels.map((lb, i) => (
          <div
            key={i}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5cqw',
              fontSize: BFT(10),
              color: BL.sub,
            }}
          >
            <span
              style={{
                width: '1cqw',
                height: '1cqw',
                borderRadius: 2,
                background: colorFor(i),
              }}
            />
            {lb}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── 슬라이드 ──────────────────────────────────────────────────
function BrandlogySlide({ data }: { data: Dict }) {
  const bg = str(data, 'BG', 'white').toLowerCase();
  const dark = bg === 'dark' || bg === 'gradient';
  const ink = dark ? BL.white : BL.ink;
  const subC = dark ? BL.darkSub : BL.sub;
  const eyebrowC = dark ? BL.darkSub : BL.mute;
  const elements = arr(data, 'ELEMENTS');

  return (
    <div
      style={
        {
          position: 'relative',
          width: '100%',
          aspectRatio: `${BL_CW} / ${BL_CH}`,
          background:
            bg === 'gradient'
              ? BL_GRADIENT
              : bg === 'dark'
                ? BL.dark
                : BL.white,
          containerType: 'inline-size',
          overflow: 'hidden',
          border: `1px solid ${BL.border}`,
          borderRadius: 3,
          boxShadow: BL.previewShadow,
          fontFamily: BL_FONT,
        } as CSSProperties
      }
    >
      {/* eyebrow */}
      {data.EYEBROW ? (
        <div
          style={{
            position: 'absolute',
            left: BX(0.9),
            top: BY(0.3),
            width: BX(BB.x1 - 0.9),
            height: BY(0.45),
            display: 'flex',
            alignItems: 'center',
            color: eyebrowC,
            fontWeight: 600,
            fontSize: BFT(10.5),
            whiteSpace: 'nowrap',
          }}
        >
          {str(data, 'EYEBROW')}
        </div>
      ) : null}

      {/* 헤드라인 (잠금 존 0.76~2.34) */}
      {data.HEADLINE ? (
        <div
          style={{
            position: 'absolute',
            left: BX(0.9),
            top: BY(0.76),
            width: BX(BB.x1 - 0.9),
            height: BY(1.58),
            display: 'flex',
            alignItems: 'center',
            color: ink,
            fontWeight: 700,
            fontSize: BFT(bg === 'gradient' ? 32 : 27),
            lineHeight: 1.15,
          }}
        >
          {str(data, 'HEADLINE')}
        </div>
      ) : null}

      {/* 부제 (잠금 존 2.34~3.30) */}
      {data.SUBTITLE ? (
        <div
          style={{
            position: 'absolute',
            left: BX(0.9),
            top: BY(2.34),
            width: BX(BB.x1 - 0.9),
            height: BY(0.96),
            display: 'flex',
            alignItems: 'center',
            color: subC,
            fontWeight: 500,
            fontSize: BFT(12.5),
            lineHeight: 1.3,
          }}
        >
          {str(data, 'SUBTITLE')}
        </div>
      ) : null}

      {/* 본문 박스 elements */}
      {elements.map((el, i) => {
        const t = str(el, 'type').toLowerCase();
        if (t === 'kpi') return <BlKpi key={i} el={el} />;
        if (t === 'chart') return <BlChart key={i} el={el} />;
        if (t === 'table') return <BlTable key={i} el={el} />;
        if (t === 'pill') return <BlPill key={i} el={el} />;
        if (t === 'bullets') return <BlBullets key={i} el={el} dark={dark} />;
        if (t === 'steps') return <BlSteps key={i} el={el} />;
        if (t === 'divider') return <BlDivider key={i} el={el} />;
        if (t === 'text') return <BlText key={i} el={el} dark={dark} />;
        return null;
      })}
    </div>
  );
}

// ════════════════════════════════════════════════════════════
// 두원 사내 진행보고 "하우스 스타일" (design/builders_house.py 재현)
// 본문 블록(lead/table/timeline/conclusion)만 담당하고, 위/아래 틀은 세미나(A4) 본문 틀
// (SlideFrame + BodyChrome)을 그대로 재사용한다. 캔버스 A4(가로) 27.517×19.05cm.
// ════════════════════════════════════════════════════════════
const HCW = 27.517;
const HCH = 19.05;
// house 본문 가용 폭(cm) — **출력(builders_house.py `BODY_W_CM`)의 단일 진실원본과 일치**해야 한다.
// 이 값이 파이썬과 어긋나면 미리보기 열 폭/사이드바이사이드 판정이 다운로드 .pptx 와 드리프트한다.
// 값 변경 시 builders_house.py BODY_W_CM 도 함께 바꿀 것. (이하 본문폭 리터럴은 모두 이 상수를 참조)
const H_BODY_W = 25.9;
// cm → 캔버스 대비 %, pt → cqw
const HY = (cm: number) => `${((cm / HCH) * 100).toFixed(3)}%`;
const HFT = (pt: number) => `${(((pt * 0.03528) / HCW) * 100).toFixed(3)}cqw`;

// builders_house.py COLORS 와 1:1
const HC = {
  white: '#FFFFFF',
  ink: '#1A1A1A',
  blue: '#1F4E9C',
  link: '#2540C0',
  hdr: '#DCE6F1',
  grid: '#808080',
  red: '#E2231A',
  g400: '#9CA3AF',
  dwNavy: '#1B3A8B',
  dwOrange: '#F26A21',
  oleMarker: '#969696',
  oleMarkerBorder: '#646464',
} as const;

// 사내 요청: 우측 정렬('r')은 쓰지 않는다 → 좌측으로(출력 builders_house 와 동일). 헤더 'c'는 유지.
const H_ALIGN: Record<string, 'left' | 'center' | 'right'> = {
  l: 'left',
  c: 'center',
  r: 'left',
};

function hColor(token: unknown): string {
  if (token == null) return HC.ink;
  const k = String(token).trim();
  if (k in HC) return (HC as Record<string, string>)[k];
  if (/^#?[0-9a-fA-F]{6}$/.test(k)) return k.startsWith('#') ? k : `#${k}`;
  return HC.ink;
}

// 한 run/문단 정의
type HRun = { t?: string; b?: boolean; c?: string; u?: boolean; al?: string };

// LLM 이 셀 줄바꿈을 <br>(또는 \n)으로 넣는 경우가 많아, 런 텍스트를 줄 단위로 쪼개
// 여러 문단으로 펼친다(그대로 두면 '<br>' 가 글자로 보임). pptx 빌더(builders_house)와 동일.
const BR_RE = /<br\s*\/?>|\n/i;
function emitBrParas(run: HRun, al: string): { al: string; runs: HRun[] }[] {
  return String(run.t ?? '')
    .split(BR_RE)
    .map((seg) => ({ al, runs: [{ ...run, t: seg }] }));
}

// 셀 값(4형태) → 문단 배열. 각 문단 = {al, runs:[HRun]}
function normalizeCell(
  value: unknown,
  colAlign: string,
): { al: string; runs: HRun[] }[] {
  if (typeof value === 'string') return emitBrParas({ t: value }, colAlign);
  if (value && typeof value === 'object') {
    const v = value as Record<string, unknown>;
    // lines/runs 가 (LLM 실수로) 문자열로 올 수 있다 → 단일 항목으로 보정(세로 쪼개짐 방지).
    if (typeof v.lines === 'string') {
      return emitBrParas({ t: v.lines }, (v.al as string) || colAlign);
    }
    if (Array.isArray(v.lines)) {
      const al = (v.al as string) || colAlign;
      return (v.lines as unknown[]).flatMap((line) =>
        emitBrParas({ t: String(line) }, al),
      );
    }
    if (typeof v.runs === 'string') {
      return emitBrParas({ t: v.runs }, colAlign);
    }
    if (Array.isArray(v.runs)) {
      return (v.runs as unknown[]).flatMap((r) =>
        r && typeof r === 'object'
          ? emitBrParas(r as HRun, ((r as HRun).al as string) || colAlign)
          : emitBrParas({ t: String(r) }, colAlign),
      );
    }
    return emitBrParas(v as HRun, (v.al as string) || colAlign);
  }
  return emitBrParas({ t: String(value ?? '') }, colAlign);
}

// 인라인 강조: **단어** → 그 단어만 굵게(출력 _emit_emph_runs 와 동일). 색은 그대로 검정 유지.
function emphNodes(s: string): ReactNode {
  const parts = String(s ?? '').split(/\*\*(.+?)\*\*/g);
  return parts.map((p, i) =>
    i % 2 === 1 ? (
      <strong key={i} style={{ fontWeight: 700 }}>
        {p}
      </strong>
    ) : (
      p
    ),
  );
}

function HouseCell({
  value,
  colAlign,
  fs,
  header,
}: {
  value: unknown;
  colAlign: string;
  fs: number;
  header?: boolean;
}) {
  const paras = normalizeCell(value, colAlign);
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        height: '100%',
        padding: '0.4cqw 0.5cqw',
      }}
    >
      {paras.map((p, i) => (
        <div
          key={i}
          style={{ textAlign: H_ALIGN[p.al] ?? 'left', lineHeight: 1.25 }}
        >
          {p.runs.map((r, j) => (
            <span
              key={j}
              style={{
                // 본문 셀(!header)은 사내 요청에 따라 평범한 검정 — 굵게·색·밑줄 무시. 헤더만 굵게.
                fontWeight: header ? 700 : 400,
                color: hColor('ink'),
                textDecoration: 'none',
                fontSize: HFT(fs),
              }}
            >
              {emphNodes(String(r.t ?? ''))}
            </span>
          ))}
        </div>
      ))}
    </div>
  );
}

// 표의 한 행을 셀 리스트로 정규화 — 출력 _as_cells 와 동일. LLM 이 행을 셀 형식 dict
// ({lines|runs})로 감싸 보내는 실수를 풀어낸다(빈칸/깨짐 방지).
function asCells(r: unknown): unknown[] {
  if (Array.isArray(r)) return r;
  if (r && typeof r === 'object') {
    const v = r as Record<string, unknown>;
    if (Array.isArray(v.lines)) return v.lines as unknown[];
    if (Array.isArray(v.runs))
      return (v.runs as unknown[]).map((x) =>
        x && typeof x === 'object' ? ((x as Dict).t ?? '') : x,
      );
    return Object.values(v);
  }
  return [r];
}

// 내용 기반 열 폭 % — 출력 _norm_colw 와 동일(긴 내용 열에 더 넓게, 최소폭 보장).
function houseColWidthsPct(block: Dict, cols: number): number[] {
  const header = (Array.isArray(block.header) ? block.header : []) as unknown[];
  const rows = (Array.isArray(block.rows) ? block.rows : []) as unknown[][];
  const floor = Math.min(1.6, H_BODY_W / cols);
  const cw = new Array(cols).fill(0);
  // 렌더 줄바꿈과 같은 계수(1.3em)로 열 폭을 잡아, 배분된 폭에서 실제로 1줄에 들어가게 한다.
  for (let c = 0; c < cols; c++)
    if (c < header.length)
      cw[c] = Math.max(cw[c], textWidthCm(String(header[c]), 12, true));
  for (const r of rows) {
    const rr = asCells(r);
    for (let c = 0; c < Math.min(cols, rr.length); c++)
      cw[c] = Math.max(cw[c], cellMaxLineWidthCm(rr[c], 12, true));
  }
  const nat = cw.map((n) => Math.max(floor, n + 0.35)); // 셀 여백(0.28+여유) — 출력 _norm_colw 와 동일
  const total = nat.reduce((a: number, b: number) => a + b, 0) || cols;
  return nat.map((n) => (n / total) * 100);
}

// 짧은 값(수치·% 등) 열 자동 가운데 정렬 — 출력(builders_house._auto_center_cols)과 동일.
const SHORT_CELL_CHARS = 6;
function cellLongestSeg(value: unknown): { any: boolean; longest: number } {
  const split = (s: string) => s.split(/<br\s*\/?>|\n/);
  let segs: string[] = [];
  if (typeof value === 'string') segs = split(value);
  else if (value && typeof value === 'object') {
    const v = value as Record<string, unknown>;
    if (typeof v.lines === 'string') segs = split(v.lines);
    else if (Array.isArray(v.lines))
      segs = v.lines.flatMap((l) => split(String(l)));
    else if (typeof v.runs === 'string') segs = split(v.runs);
    else if (Array.isArray(v.runs))
      segs = v.runs.flatMap((r) =>
        split(String(r && typeof r === 'object' ? ((r as Dict).t ?? '') : r)),
      );
    else segs = [String(v.t ?? '')];
  } else segs = [String(value ?? '')];
  let any = false;
  let longest = 0;
  for (const s of segs) {
    const t = s.trim();
    if (t) {
      any = true;
      longest = Math.max(longest, t.length);
    }
  }
  return { any, longest };
}
function autoCenterAligns(
  block: Dict,
  cols: number,
  align: string[],
): string[] {
  const rows = (Array.isArray(block.rows) ? block.rows : []) as unknown[][];
  const out = [...align];
  while (out.length < cols) out.push('l');
  for (let c = 0; c < cols; c++) {
    let any = false;
    let longest = 0;
    for (const r of rows) {
      const cells = asCells(r);
      if (c >= cells.length) continue;
      const m = cellLongestSeg(cells[c]);
      if (m.any) {
        any = true;
        longest = Math.max(longest, m.longest);
      }
    }
    if (any && longest <= SHORT_CELL_CHARS) out[c] = 'c';
  }
  return out.slice(0, cols);
}

function HouseTable({ block }: { block: Dict }) {
  const header = (Array.isArray(block.header) ? block.header : []) as unknown[];
  const rows = (Array.isArray(block.rows) ? block.rows : []) as unknown[][];
  const cols = header.length || (rows[0]?.length ?? 1);
  const fs = 12; // 본문 글자 12pt 고정(사내 요청) — 출력(builders_house BODY_FS)과 일치
  const hfs = numv(block.hfs, 12);
  const colPct = houseColWidthsPct(block, cols);
  // 짧은 값(수치·% 등 ≤6자)으로만 채워진 열은 가운데 정렬(출력 _auto_center_cols 와 동일).
  const align = autoCenterAligns(
    block,
    cols,
    (Array.isArray(block.align) ? block.align : []) as string[],
  );

  // 표는 옆 블록 높이에 맞추려 행을 늘리지 않는다 — 내용 적은 표는 행마다 공백이 생겨 보기 싫다.
  // 항상 내용에 맞는 자연 높이로 컴팩트하게(출력 _table 과 동일). 차트·timeline 만 fill 로 늘린다.
  return (
    <table
      style={{
        width: '100%',
        borderCollapse: 'collapse',
        tableLayout: 'fixed',
      }}
    >
      <colgroup>
        {Array.from({ length: cols }).map((_, i) => (
          <col key={i} style={{ width: `${colPct[i] ?? 100 / cols}%` }} />
        ))}
      </colgroup>
      <tbody>
        {header.length > 0 ? (
          <tr>
            {Array.from({ length: cols }).map((_, c) => (
              <td
                key={c}
                style={{
                  background: HC.hdr,
                  border: `0.75pt solid ${HC.grid}`,
                  verticalAlign: 'middle',
                  height: HY(numv(block.headerH, 0.6)),
                }}
              >
                <HouseCell
                  value={{ t: String(header[c] ?? ''), al: 'c' }}
                  colAlign="c"
                  fs={hfs}
                  header
                />
              </td>
            ))}
          </tr>
        ) : null}
        {rows.map((row, r) => {
          const cells = asCells(row);
          return (
            <tr key={r}>
              {Array.from({ length: cols }).map((_, c) => (
                <td
                  key={c}
                  style={{
                    border: `0.75pt solid ${HC.grid}`,
                    verticalAlign: 'middle',
                  }}
                >
                  <HouseCell
                    value={cells[c] ?? ''}
                    colAlign={align[c] ?? 'l'}
                    fs={fs}
                  />
                </td>
              ))}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function HouseTimeline({ block }: { block: Dict }) {
  const nodes = arr(block, 'nodes');
  if (!nodes.length) return null;
  return (
    <div
      style={{
        position: 'relative',
        width: '100%',
        minHeight: '5cqw',
        display: 'flex',
        alignItems: 'center',
      }}
    >
      {/* 가는 네이비 가로선 + 우측 끝 화살촉(굵은 블록 화살표 대신) */}
      <div
        style={{
          position: 'absolute',
          left: '1cqw',
          right: '1.6cqw',
          top: '50%',
          transform: 'translateY(-50%)',
          height: '0.18cqw',
          background: HC.dwNavy,
        }}
      />
      <div
        style={{
          position: 'absolute',
          right: '0.4cqw',
          top: '50%',
          transform: 'translateY(-50%)',
          width: 0,
          height: 0,
          borderTop: '0.55cqw solid transparent',
          borderBottom: '0.55cqw solid transparent',
          borderLeft: `0.9cqw solid ${HC.dwNavy}`,
        }}
      />
      <div
        style={{
          position: 'relative',
          width: '100%',
          display: 'flex',
          justifyContent: 'space-between',
          padding: '0 2cqw',
        }}
      >
        {nodes.map((n, i) => {
          const state = str(n, 'state', 'todo');
          const todo = state === 'todo';
          return (
            <div
              key={i}
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                width: '8cqw',
              }}
            >
              <div
                style={{
                  fontSize: HFT(10),
                  fontWeight: 700,
                  color: HC.ink,
                  textAlign: 'center',
                  marginBottom: '0.4cqw',
                  whiteSpace: 'nowrap',
                }}
              >
                {str(n, 'label')}
              </div>
              <div
                style={{
                  width: '1.2cqw',
                  height: '1.2cqw',
                  borderRadius: '50%',
                  background: todo ? HC.white : HC.dwNavy,
                  border: `0.18cqw solid ${HC.dwNavy}`,
                }}
              />
              <div
                style={{
                  fontSize: HFT(9.5),
                  color: HC.g400,
                  textAlign: 'center',
                  marginTop: '0.3cqw',
                  whiteSpace: 'nowrap',
                }}
              >
                ({str(n, 'date')})
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// compare 블록 — 큰 열 비교 그리드. 셀에 텍스트 또는 타임라인을 담는다(출력 builders_house._compare 와 동일).
function compareCellIsTimeline(cell: unknown): boolean {
  return (
    !!cell &&
    typeof cell === 'object' &&
    str(cell as Dict, 'type') === 'timeline'
  );
}
function compareCellLines(cell: unknown): string[] {
  const split = (s: string) => s.split(/<br\s*\/?>|\n/);
  if (typeof cell === 'string') return split(cell);
  if (cell && typeof cell === 'object') {
    const v = cell as Dict;
    if (Array.isArray(v.lines))
      return (v.lines as unknown[]).flatMap((l) => split(String(l)));
    if (Array.isArray(v.bullets))
      return (v.bullets as unknown[]).map((b) => `• ${b}`);
    if (v.text != null) return split(String(v.text));
    if (v.t != null) return split(String(v.t));
  }
  return [String(cell)];
}
function HouseCompare({ block }: { block: Dict }) {
  const rows = arr(block, 'rows');
  if (!rows.length) return null;
  const headers = (
    Array.isArray(block.headers) ? (block.headers as unknown[]) : []
  ).map(String);
  const ncol = Math.max(
    1,
    ...rows.map((r) => arr(r, 'cells').length),
    headers.length > 1 ? headers.length - 1 : 1,
  );
  const labelPct = (1.9 / H_BODY_W) * 100;
  const colPct = (100 - labelPct) / ncol;
  const border = `0.75pt solid ${HC.grid}`;
  const hdrCell = {
    background: HC.hdr,
    border,
    textAlign: 'center' as const,
    verticalAlign: 'middle' as const,
    fontWeight: 700,
    fontSize: HFT(12),
    color: HC.ink,
  };
  return (
    <table
      style={{
        width: '100%',
        borderCollapse: 'collapse',
        tableLayout: 'fixed',
      }}
    >
      <colgroup>
        <col style={{ width: `${labelPct}%` }} />
        {Array.from({ length: ncol }).map((_, i) => (
          <col key={i} style={{ width: `${colPct}%` }} />
        ))}
      </colgroup>
      <tbody>
        {headers.length ? (
          <tr>
            <td style={hdrCell}>{headers[0] ?? ''}</td>
            {Array.from({ length: ncol }).map((_, j) => (
              <td key={j} style={hdrCell}>
                {headers[j + 1] ?? ''}
              </td>
            ))}
          </tr>
        ) : null}
        {rows.map((r, ri) => {
          const cells = arr(r, 'cells');
          return (
            <tr key={ri}>
              <td
                style={{
                  border,
                  textAlign: 'center',
                  verticalAlign: 'middle',
                  fontWeight: 700,
                  fontSize: HFT(12),
                  color: HC.ink,
                }}
              >
                {str(r, 'label')}
              </td>
              {Array.from({ length: ncol }).map((_, j) => {
                const cell = cells[j];
                const tl = compareCellIsTimeline(cell);
                return (
                  <td
                    key={j}
                    style={{
                      border,
                      verticalAlign: tl ? 'middle' : 'top',
                      padding: tl ? '0.3cqw' : '0.4cqw 0.6cqw',
                    }}
                  >
                    {tl ? (
                      <HouseTimeline block={cell as Dict} />
                    ) : (
                      <div
                        style={{
                          fontSize: HFT(12),
                          color: HC.ink,
                          lineHeight: 1.35,
                        }}
                      >
                        {compareCellLines(cell).map((s, k) => (
                          <div key={k}>{s}</div>
                        ))}
                      </div>
                    )}
                  </td>
                );
              })}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

// outline 블록 — 번호가 붙는 계층 목록(출력 builders_house._outline 과 동일). 1)대항목 + ①②③ 하위.
const OUTLINE_CIRCLED = '①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳';
function outlineLines(
  block: Dict,
): { level: number; marker: string; text: string; bold: boolean }[] {
  const out: { level: number; marker: string; text: string; bold: boolean }[] =
    [];
  let c1 = 0;
  let c2 = 0;
  for (const it of arr(block, 'items') as unknown[]) {
    let text = '';
    let level = 1;
    let bold: boolean | undefined;
    if (typeof it === 'string') text = it.trim();
    else if (it && typeof it === 'object') {
      text = String((it as Dict).text ?? '').trim();
      level = Number((it as Dict).level) || 1;
      bold = (it as Dict).bold as boolean | undefined;
    }
    if (!text) continue;
    level = level < 1 ? 1 : level > 3 ? 3 : level;
    let marker = '-';
    if (level === 1) {
      c1 += 1;
      c2 = 0;
      marker = `${c1})`;
    } else if (level === 2) {
      c2 += 1;
      marker =
        c2 <= OUTLINE_CIRCLED.length ? OUTLINE_CIRCLED[c2 - 1] : `(${c2})`;
    }
    out.push({
      level,
      marker,
      text,
      bold: bold === undefined ? level === 1 : !!bold,
    });
  }
  return out;
}
function HouseOutline({ block }: { block: Dict }) {
  const lines = outlineLines(block);
  // 출력 _OUTLINE_INDENT {1:0.6, 2:1.5, 3:2.4}cm 와 동일(cm→cqw = cm/27.517*100).
  const indent = (lvl: number) =>
    lvl === 1 ? '2.18cqw' : lvl === 2 ? '5.45cqw' : '8.72cqw';
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3cqw' }}>
      {lines.map((l, i) => (
        <div
          key={i}
          style={{
            marginLeft: indent(l.level),
            fontSize: HFT(12.5),
            color: HC.ink,
            fontWeight: l.bold ? 700 : 400,
            lineHeight: 1.4,
          }}
        >
          {l.marker} {emphNodes(l.text)}
        </div>
      ))}
    </div>
  );
}

// 높이(cm) → cqw (컨테이너가 inline-size 라 폭 기준; aspect 고정이라 세로도 동일 스케일)
const HHcq = (cm: number) => `${((cm / HCW) * 100).toFixed(3)}cqw`;
const CHART_PALETTE = [
  HC.blue,
  HC.dwOrange,
  HC.dwNavy,
  HC.g400,
  HC.link,
  HC.red,
];
const chartColor = (i: number) => CHART_PALETTE[i % CHART_PALETTE.length];

function chartSeries(block: Dict): { name: string; values: number[] }[] {
  const raw = Array.isArray(block.series) ? (block.series as Dict[]) : [];
  return raw.map((s) => ({
    name: str(s, 'name'),
    values: (Array.isArray(s.values) ? (s.values as unknown[]) : []).map((v) =>
      numv(v, 0),
    ),
  }));
}

function HouseLegend({ items }: { items: { name: string; color: string }[] }) {
  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: '0.7cqw',
        justifyContent: 'center',
        marginTop: '0.4cqw',
      }}
    >
      {items.map((it, i) => (
        <div
          key={i}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.3cqw',
            fontSize: HFT(9),
          }}
        >
          <span
            style={{
              width: '0.9cqw',
              height: '0.9cqw',
              background: it.color,
              display: 'inline-block',
            }}
          />
          <span style={{ color: HC.ink }}>{it.name}</span>
        </div>
      ))}
    </div>
  );
}

// PowerPoint 네이티브 차트의 웹 근사(미리보기 전용). 다운로드 .pptx 는 편집 가능한 실제 차트.
function HouseChart({ block }: { block: Dict }) {
  const type = str(block, 'chart', 'column').toLowerCase();
  let cats = (
    Array.isArray(block.categories) ? (block.categories as unknown[]) : []
  ).map((c) => String(c));
  let series = chartSeries(block);
  if (!series.length) return null;
  // 출력(builders_house)과 동일하게 빈 라벨 + 값 없는 뒤쪽 카테고리 정리.
  const keep = cats.map((c, i) => (c.trim() ? i : -1)).filter((i) => i >= 0);
  if (keep.length && keep.length !== cats.length) {
    cats = keep.map((i) => cats[i]);
    series = series.map((s) => ({
      ...s,
      values: keep.map((i) => s.values[i] ?? 0),
    }));
  }
  const maxVals = Math.max(0, ...series.map((s) => s.values.length));
  if (maxVals > 0 && maxVals < cats.length) cats = cats.slice(0, maxVals);
  const isPie = type === 'pie' || type === 'doughnut';
  const h = numv(block.h, isPie ? 4.8 : 5.2);
  const all = series.flatMap((s) => s.values);
  const max = Math.max(1, ...all);
  const multi = series.length > 1;

  if (isPie) {
    const vals = series[0].values;
    const total = vals.reduce((a, b) => a + b, 0) || 1;
    let acc = 0;
    const stops = vals.map((v, i) => {
      const s = (acc / total) * 360;
      acc += v;
      return `${chartColor(i)} ${s}deg ${(acc / total) * 360}deg`;
    });
    // 원형은 좌측에 파이, 우측에 범례를 둬 좌우 여백을 덜 잡아먹게(출력과 동일).
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'row',
          alignItems: 'center',
          gap: '1.5cqw',
          height: HHcq(h),
        }}
      >
        <div
          style={{
            flex: '0 0 auto',
            height: '100%',
            aspectRatio: '1',
            position: 'relative',
            borderRadius: '50%',
            background: `conic-gradient(${stops.join(',')})`,
          }}
        >
          {type === 'doughnut' ? (
            <div
              style={{
                position: 'absolute',
                inset: '30%',
                background: HC.white,
                borderRadius: '50%',
              }}
            />
          ) : null}
        </div>
        <div
          style={{ display: 'flex', flexDirection: 'column', gap: '0.6cqw' }}
        >
          {cats.map((c, i) => (
            <div
              key={i}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.4cqw',
                fontSize: HFT(10),
              }}
            >
              <span
                style={{
                  width: '1cqw',
                  height: '1cqw',
                  background: chartColor(i),
                  display: 'inline-block',
                }}
              />
              <span style={{ color: HC.ink }}>
                {c} ({vals[i] ?? 0})
              </span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (type === 'bar') {
    return (
      <div
        style={{ display: 'flex', flexDirection: 'column', height: HHcq(h) }}
      >
        <div
          style={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
            gap: '0.5cqw',
            minHeight: 0,
          }}
        >
          {cats.map((c, ci) => (
            <div
              key={ci}
              style={{ display: 'flex', alignItems: 'center', gap: '0.5cqw' }}
            >
              <div
                style={{
                  width: '18%',
                  fontSize: HFT(9),
                  color: HC.ink,
                  textAlign: 'right',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                }}
              >
                {c}
              </div>
              <div
                style={{
                  flex: 1,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '1px',
                }}
              >
                {series.map((s, si) => (
                  <div
                    key={si}
                    style={{
                      width: `${((s.values[ci] ?? 0) / max) * 100}%`,
                      minWidth: '1px',
                      height: multi ? '0.7cqw' : '1.1cqw',
                      background: chartColor(si),
                    }}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
        {multi ? (
          <HouseLegend
            items={series.map((s, i) => ({
              name: s.name,
              color: chartColor(i),
            }))}
          />
        ) : null}
      </div>
    );
  }

  if (type === 'line') {
    const n = Math.max(cats.length, series[0].values.length);
    const xat = (i: number) => (n > 1 ? (i / (n - 1)) * 100 : 50);
    const yat = (v: number) => 100 - (v / max) * 100;
    return (
      <div
        style={{ display: 'flex', flexDirection: 'column', height: HHcq(h) }}
      >
        <div style={{ flex: 1, position: 'relative', minHeight: 0 }}>
          <svg
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
            style={{
              position: 'absolute',
              inset: 0,
              width: '100%',
              height: '100%',
            }}
          >
            {series.map((s, si) => (
              <polyline
                key={si}
                fill="none"
                stroke={chartColor(si)}
                strokeWidth={1.5}
                vectorEffect="non-scaling-stroke"
                points={s.values.map((v, i) => `${xat(i)},${yat(v)}`).join(' ')}
              />
            ))}
          </svg>
        </div>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            fontSize: HFT(9),
            color: HC.ink,
          }}
        >
          {cats.map((c, i) => (
            <span key={i}>{c}</span>
          ))}
        </div>
        {multi ? (
          <HouseLegend
            items={series.map((s, i) => ({
              name: s.name,
              color: chartColor(i),
            }))}
          />
        ) : null}
      </div>
    );
  }

  // column (default)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: HHcq(h) }}>
      <div
        style={{
          flex: 1,
          display: 'flex',
          alignItems: 'flex-end',
          gap: '0.6cqw',
          minHeight: 0,
        }}
      >
        {cats.map((c, ci) => (
          <div
            key={ci}
            style={{
              flex: 1,
              display: 'flex',
              alignItems: 'flex-end',
              justifyContent: 'center',
              gap: '1px',
              height: '100%',
            }}
          >
            {series.map((s, si) => (
              <div
                key={si}
                style={{
                  flex: 1,
                  maxWidth: '2.5cqw',
                  height: `${((s.values[ci] ?? 0) / max) * 100}%`,
                  background: chartColor(si),
                  position: 'relative',
                }}
              >
                {!multi ? (
                  <span
                    style={{
                      position: 'absolute',
                      top: '-1.5cqw',
                      left: 0,
                      right: 0,
                      textAlign: 'center',
                      fontSize: HFT(8.5),
                      color: HC.ink,
                    }}
                  >
                    {s.values[ci] ?? 0}
                  </span>
                ) : null}
              </div>
            ))}
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', gap: '0.6cqw' }}>
        {cats.map((c, i) => (
          <div
            key={i}
            style={{
              flex: 1,
              textAlign: 'center',
              fontSize: HFT(9),
              color: HC.ink,
            }}
          >
            {c}
          </div>
        ))}
      </div>
      {multi ? (
        <HouseLegend
          items={series.map((s, i) => ({ name: s.name, color: chartColor(i) }))}
        />
      ) : null}
    </div>
  );
}

function HouseText({ block }: { block: Dict }) {
  const bullets = Array.isArray(block.bullets)
    ? (block.bullets as unknown[]).map(String)
    : null;
  if (bullets && bullets.length) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3cqw' }}>
        {bullets.map((b, i) => (
          <div
            key={i}
            style={{ fontSize: HFT(12), color: HC.ink, lineHeight: 1.4 }}
          >
            • {emphNodes(b)}
          </div>
        ))}
      </div>
    );
  }
  return (
    <div
      style={{
        fontSize: HFT(12),
        color: HC.ink,
        lineHeight: 1.4,
        whiteSpace: 'pre-wrap',
      }}
    >
      {emphNodes(str(block, 'text').replace(/<br\s*\/?>/gi, '\n'))}
    </div>
  );
}

// 블록 1개(섹션 헤딩 포함) 렌더 — 본문/2단 컬럼 공용.
// fill: 2단 row 에서 옆 컬럼과 세로 높이를 맞추도록 표/차트를 컬럼 높이만큼 늘린다.
function HouseBlock({ block, fill }: { block: Dict; fill?: boolean }) {
  const type = str(block, 'type');
  const section = stripBullet(str(block, 'section'));
  const showSection = section && type !== 'lead';
  // 섹션 똑딱이(OLE) 마커 — 출력에선 제목 옆 0.6cm 아이콘이 OLE 로 교체된다. 미리보기엔 표식만.
  const hasSectionOle = !!(block.ole && typeof block.ole === 'object');
  // fill 시 basis 를 auto 로 둬야(=1 0 auto) 자연 높이를 잡으면서 늘어난다. basis 0(=flex:1)이면
  // 높이 auto 인 row 가 0 으로 붕괴해 블록이 서로 겹친다.
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        flex: fill ? '1 0 auto' : '0 0 auto',
        minHeight: 0,
      }}
    >
      {showSection ? (
        // 제목-내용 간격 0.3cm(≈1.1cqw) — 출력 _SECTION_GAP 와 동일(사내 요청: 너무 붙지 않게)
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.6cqw',
            fontWeight: 700,
            color: HC.ink,
            fontSize: HFT(15.5),
            marginBottom: '1.1cqw',
          }}
        >
          <span>■ {section}</span>
          {hasSectionOle ? (
            <span
              style={{
                width: '2.15cqw',
                height: '2.15cqw',
                background: HC.oleMarker,
                border: `0.13cqw solid ${HC.oleMarkerBorder}`,
                flex: '0 0 auto',
              }}
            />
          ) : null}
        </div>
      ) : null}
      {type === 'lead' ? (
        <div style={{ fontSize: HFT(12.5), color: HC.ink, lineHeight: 1.3 }}>
          <span style={{ fontWeight: 700, fontSize: HFT(15.5) }}>
            ■ {stripBullet(str(block, 'label', '목적')) || '목적'} :{' '}
          </span>
          {emphNodes(str(block, 'text'))}
        </div>
      ) : null}
      {type === 'table' ? (
        <div style={{ display: 'flex', minHeight: 0 }}>
          <HouseTable block={block} />
        </div>
      ) : null}
      {type === 'chart' ? (
        // 사내 요청: 차트(원형+범례 등)를 1행1열 표처럼 테두리 박스로 감싼다(출력과 동일).
        <div
          style={{
            border: `0.75pt solid ${HC.grid}`,
            padding: '0.4cqw',
            flex: fill ? '1 0 auto' : undefined,
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
          }}
        >
          <HouseChart block={block} />
        </div>
      ) : null}
      {type === 'text' ? <HouseText block={block} /> : null}
      {type === 'timeline'
        ? (() => {
            // 사내 요청: 타임라인도 차트처럼 테두리 박스로 감싼다(출력과 동일).
            // 단독 배치(!fill)면 노드 개수·라벨 길이에 맞춰 박스 폭을 줄이고 좌측 정렬(출력
            // _timeline 의 fill_h is None 분기와 동일). row 안(fill)이면 칸을 가득 채운다.
            const widthStyle: CSSProperties = {};
            if (!fill) {
              const tlNodes = arr(block, 'nodes');
              const nn = tlNodes.length;
              let drawW: number;
              if (nn > 1) {
                const needs = tlNodes.map((nd) =>
                  Math.max(
                    textWidthCm(str(nd as Dict, 'label'), 10),
                    textWidthCm(`(${str(nd as Dict, 'date')})`, 9.5),
                    1.4,
                  ),
                );
                const stepWant = Math.max(
                  2.6,
                  Math.min(Math.max(...needs) + 0.9, 5.5),
                );
                drawW = Math.min(
                  H_BODY_W,
                  Math.max(stepWant * (nn - 1) + 2.2, 6.0),
                );
              } else {
                drawW = Math.min(H_BODY_W, 8.0);
              }
              widthStyle.alignSelf = 'flex-start';
              widthStyle.width = `${((drawW / 27.517) * 100).toFixed(2)}cqw`;
            }
            return (
              <div
                style={{
                  border: `0.75pt solid ${HC.grid}`,
                  padding: '0.4cqw',
                  flex: fill ? '1 0 auto' : undefined,
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'center',
                  ...widthStyle,
                }}
              >
                <HouseTimeline block={block} />
              </div>
            );
          })()
        : null}
      {type === 'conclusion' ? (
        <div
          style={{
            fontWeight: 700,
            color: HC.blue,
            fontSize: HFT(14),
            lineHeight: 1.3,
          }}
        >
          {str(block, 'text')}
        </div>
      ) : null}
      {type === 'compare' ? <HouseCompare block={block} /> : null}
      {type === 'outline' ? <HouseOutline block={block} /> : null}
    </div>
  );
}

// 셀/블록의 '한 줄' 자연 폭(cm) 추정 — 출력 _block_natural_width 와 동일 로직(2단 폭 자동 배분).
// wrap=false: 컬럼 폭 산정용(1.1em, _text_width_cm). wrap=true: '1줄 필요폭'/자연폭용(1.3em,
// _text_width_wrap_cm) — 렌더 줄바꿈(_wrap_lines)과 같은 계수라 side-by-side 판정이 실제와 맞는다.
const WRAP_NARROW = new Set(' ,.:;·|/\\-–—()[]{}\'"~!?%'.split(''));
function textWidthCm(s: string, fs = 12, wrap = false): number {
  const em = fs * 0.03528;
  // 현대하모니 M COM 실측: 한글 1.03, ascii 0.6, 공백·문장부호 0.33em. wrap 모드에서 좁은 문자 반영
  // (예전엔 공백·쉼표를 0.6으로 세어 부풀어 행 팽창·표 과대추정).
  const ko = wrap ? 1.03 : 1.1;
  const ascii = wrap ? 0.6 : 0.6;
  let w = 0;
  for (const ch of String(s)) {
    if (wrap && (ch === ' ' || WRAP_NARROW.has(ch))) w += 0.33;
    else if (ch.charCodeAt(0) <= 0x7f) w += ascii;
    else w += ko;
  }
  return w * em;
}
function cellMaxLineWidthCm(value: unknown, fs = 12, wrap = false): number {
  let segs: string[] = [];
  const split = (s: string) => s.split(/<br\s*\/?>|\n/);
  if (typeof value === 'string') segs = split(value);
  else if (value && typeof value === 'object') {
    const v = value as Record<string, unknown>;
    if (typeof v.lines === 'string') segs = split(v.lines);
    else if (Array.isArray(v.lines))
      segs = v.lines.flatMap((l) => split(String(l)));
    else if (typeof v.runs === 'string') segs = split(v.runs);
    else if (Array.isArray(v.runs))
      segs = v.runs.flatMap((r) =>
        split(String(r && typeof r === 'object' ? ((r as Dict).t ?? '') : r)),
      );
    else segs = [String(v.t ?? '')];
  } else segs = [String(value ?? '')];
  return Math.max(0, ...segs.map((s) => textWidthCm(s, fs, wrap)));
}
function houseBlockNaturalWidth(block: Dict): number {
  const type = str(block, 'type');
  if (type === 'row') {
    // 중첩 row 는 자식을 가로로 나란히 둔다고 보고 자연 폭 합(+ 컬럼 간격 0.5cm). 출력과 동일.
    const kids = (
      (Array.isArray(block.blocks)
        ? block.blocks
        : Array.isArray(block.cols)
          ? block.cols
          : []) as Dict[]
    ).filter((b) => b && typeof b === 'object');
    if (!kids.length) return 2;
    return (
      kids.reduce((a, k) => a + houseBlockNaturalWidth(k), 0) +
      0.5 * (kids.length - 1)
    );
  }
  if (type === 'compare') return 26; // 비교 그리드는 항상 풀폭
  if (type === 'outline') {
    const segs = outlineLines(block).map((l) => l.text);
    return Math.max(
      2,
      Math.max(0, ...segs.map((s) => textWidthCm(s, 12.5, true))) + 1,
    );
  }
  if (type === 'table') {
    const header = (
      Array.isArray(block.header) ? block.header : []
    ) as unknown[];
    const rows = (Array.isArray(block.rows) ? block.rows : []) as unknown[][];
    const cols = header.length || (rows[0]?.length ?? 1);
    const cw = new Array(cols).fill(0);
    for (let c = 0; c < cols; c++)
      if (c < header.length)
        cw[c] = Math.max(cw[c], textWidthCm(String(header[c]), 12, true));
    for (const r of rows) {
      const rr = Array.isArray(r) ? r : [r];
      for (let c = 0; c < Math.min(cols, rr.length); c++)
        cw[c] = Math.max(cw[c], cellMaxLineWidthCm(rr[c], 12, true));
    }
    return Math.max(
      2,
      cw.reduce((a: number, b: number) => a + b + 0.35, 0),
    ); // 출력 _block_natural_width 와 동일
  }
  if (type === 'chart')
    return ['pie', 'doughnut'].includes(
      str(block, 'chart', 'column').toLowerCase(),
    )
      ? 10
      : 14;
  if (type === 'text' || type === 'lead' || type === 'conclusion') {
    const segs = Array.isArray(block.bullets)
      ? (block.bullets as unknown[]).map(String)
      : [str(block, 'text')];
    return Math.max(
      2,
      Math.max(0, ...segs.map((s) => textWidthCm(s, 12, true))) + 0.5,
    );
  }
  return 5;
}

// 2단(좌우) row 블록 — ratio 가 있으면 그 비율, 없으면 내용 기반 자연 폭으로 나란히.
// 중첩 row 는 평탄화하지 않고 그대로 처리(출력 _render_row 와 동일) — 자식이 row 면 HouseRow 재귀.
function HouseRow({ block }: { block: Dict }) {
  const kids = (
    (Array.isArray(block.blocks)
      ? block.blocks
      : Array.isArray(block.cols)
        ? block.cols
        : []) as Dict[]
  )
    .filter((b) => b && typeof b === 'object')
    .slice(0, 3);
  if (!kids.length) return null;
  const renderChild = (k: Dict, fill?: boolean) =>
    str(k, 'type') === 'row' ? (
      <HouseRow block={k} />
    ) : (
      <HouseBlock block={k} fill={fill} />
    );
  const ratio = Array.isArray(block.ratio) ? (block.ratio as number[]) : [];
  const hasRatio = ratio.some((r) => typeof r === 'number' && r > 0);
  const CM2CQW = 100 / 27.517; // cm → cqw (슬라이드 폭 27.517cm 기준)
  const nats = kids.map((k, i) =>
    hasRatio
      ? ratio[i] && ratio[i] > 0
        ? ratio[i]
        : 1
      : houseBlockNaturalWidth(k),
  );
  // 출력(_row_side_by_side)과 동일: 거의 1줄로 들어가는 쌍(자연폭 합 ≤ 가용폭×1.12)만 가로 배치.
  // 넓은 텍스트 표를 억지로 붙이면 컬럼이 반토막→줄바꿈→행이 커져 세로 공백이 커지므로 세로로 쌓는다.
  // (python builders_house._ROW_FIT_FACTOR 와 동일하게 유지.)
  const NONTABLE_MIN: Record<string, number> = {
    chart: 7,
    timeline: 5,
    text: 4,
    lead: 4,
    conclusion: 4,
  };
  const ROW_FIT_FACTOR = 1.0;
  // 표가 없는 row(outline/text 만)는 완화(1.4) — 짧은 outline 을 세로로 쌓으면 각 박스가 full-width 라
  // 우측 여백이 크게 남는다. 표와 달리 outline/text 는 좁아져도 줄 하나 늘 뿐이라 옆으로 붙여 가로를 쓴다.
  const ROW_FIT_FACTOR_SOFT = 1.4;
  // 표·목록·텍스트는 좁아지면 줄바꿈돼 세로로 커지므로 1줄 자연폭으로 잡는다. 차트·타임라인만 최소폭.
  const COMPRESSIBLE = new Set(['chart', 'timeline']);
  const AVAIL_CM = H_BODY_W - 0.5 * (kids.length - 1);
  const need = kids.reduce(
    (a, k) =>
      a +
      (COMPRESSIBLE.has(str(k, 'type'))
        ? (NONTABLE_MIN[str(k, 'type')] ?? 4)
        : houseBlockNaturalWidth(k)),
    0,
  );
  const hasTable = kids.some((k) => str(k, 'type') === 'table');
  const fitFactor = hasTable ? ROW_FIT_FACTOR : ROW_FIT_FACTOR_SOFT;
  if (!hasRatio && kids.length > 1 && need > AVAIL_CM * fitFactor) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: '1.3cqw',
          flex: '0 0 auto',
        }}
      >
        {kids.map((k, i) => (
          <div key={i}>{renderChild(k)}</div>
        ))}
      </div>
    );
  }
  // 출력(_row_widths)과 동일: 자연 폭을 basis 로, 남는 폭은 표가 아닌 블록이 흡수(표는 자연 폭
  // 유지). **표(박스 포함)만 있는 줄이면 표들이 나눠 가져 가로를 가득 채운다**(우측 여백 제거).
  const hasGrower = kids.some((k) => str(k, 'type') !== 'table');
  const growOf = (i: number) =>
    hasRatio
      ? nats[i]
      : !hasGrower
        ? nats[i]
        : str(kids[i], 'type') === 'table'
          ? 0
          : nats[i];
  const basisOf = (i: number) =>
    hasRatio ? '0' : `${(nats[i] * CM2CQW).toFixed(2)}cqw`;
  // alignItems:stretch + 자식 fill → 차트+표가 같은 세로 높이로 정렬된다.
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'row',
        gap: '1.6cqw',
        alignItems: 'stretch',
        flex: '0 0 auto',
      }}
    >
      {kids.map((k, i) => (
        <div
          key={i}
          style={{
            flex: `${growOf(i)} 1 ${basisOf(i)}`,
            minWidth: 0,
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {renderChild(k, true)}
        </div>
      ))}
    </div>
  );
}

function HouseReportSlide({ data }: { data: Dict }) {
  // 세미나(A4) 본문 틀을 그대로 재사용: ▣ 제목 + 우상단 날짜 + 가로선 사이 로고 +
  // 사선 DCC 워터마크 + 하단 영문 저작권 + Confidential 배지. ('N. 제목 [태그]'·'N/total' 제거)
  // 태그는 헤더에 붙이지 않는다(제목+태그가 길면 말줄임 발생 → 출력과 불일치).
  const header = str(data, 'title');
  const blocks = arr(data, 'blocks');
  const oleIcon =
    data.ole_icon && typeof data.ole_icon === 'object'
      ? (data.ole_icon as Dict)
      : null;

  return (
    <SlideFrame>
      <BodyChrome header={header}>
        {/* 블록은 위에서부터 빽빽이 쌓는다(컴팩트). 하단 공백은 간격을 벌려 메우지 않는다 —
            리패킹이 더 많은 블록을 끌어올려 채운다(출력 _layout_blocks 와 동일). row 는 좌우 2단. */}
        <div
          style={{
            flex: 1,
            minHeight: 0,
            display: 'flex',
            flexDirection: 'column',
            gap: '1.3cqw',
          }}
        >
          {blocks.map((block, i) =>
            str(block, 'type') === 'row' ? (
              <HouseRow key={i} block={block} />
            ) : (
              <HouseBlock key={i} block={block} />
            ),
          )}
        </div>
        {/* 똑딱이(OLE) 아이콘 — 출력 _draw_ole_icon 과 동일(우하단, 0.6×0.6cm 작은 회색 사각형).
            라벨/삼각형 없이 아이콘만. 브라우저엔 더블클릭 동작이 없으므로 표식만 표시(상세는
            아래 '똑딱이 내용'에 펼쳐짐). */}
        {oleIcon ? (
          <div
            style={{
              position: 'absolute',
              right: '0.55cqw',
              bottom: '0.55cqw',
              width: '2.15cqw',
              height: '2.15cqw',
              background: HC.oleMarker,
              border: `0.13cqw solid ${HC.oleMarkerBorder}`,
            }}
          />
        ) : null}
      </BodyChrome>
    </SlideFrame>
  );
}

// ── 디스패처 ─────────────────────────────────────────────────
const RENDERERS: Record<string, (p: { data: Dict }) => ReactNode> = {
  'a4-cover': A4CoverSlide,
  'a4-exec-kpi-dashboard': A4ExecKpiSlide,
  'house-report': HouseReportSlide,
  'a4-division-scorecard': A4ScorecardSlide,
  'a4-meeting-minutes': A4MeetingMinutesSlide,
  brandlogy: BrandlogySlide,
};

export function PptSlideRenderer({ slide }: { slide: PptSlide }) {
  const { t } = useTranslation('apps');
  const Renderer = RENDERERS[slide.layout];
  const data = (slide.data || {}) as Dict;
  if (!Renderer) {
    return (
      <SlideFrame>
        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: C.muted,
            fontSize: '1.6cqw',
          }}
        >
          {t('ai.pptGenerator.renderer.unsupportedLayout', {
            layout: slide.layout,
          })}
        </div>
      </SlideFrame>
    );
  }
  return <Renderer data={data} />;
}
