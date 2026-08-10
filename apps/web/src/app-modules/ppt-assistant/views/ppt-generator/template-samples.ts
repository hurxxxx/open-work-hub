// i18n-exempt-file: 템플릿 미리보기용 데모 콘텐츠(슬라이드 샘플 데이터) — 번역 리소스 대상 아님.
import type { PptSlide } from '../../api/ppt-generator-api';

/**
 * 템플릿 미리보기용 대표 샘플 슬라이드. 결과 미리보기에 쓰는 PptSlideRenderer 로
 * 실시간 렌더해, 미리보기 이미지를 따로 업로드하지 않아도 양식을 바로 보여준다.
 *
 * 키 = family id. 네이티브 렌더러가 있는 양식(a4-*, house-report)은 본문까지,
 * HTML 경로(corporate-*)는 Open ALM 표지(a4-cover)까지 보여준다.
 */
const COVER = (title: string): PptSlide => ({
  layout: 'a4-cover',
  data: {
    TITLE: title,
    DATE: '2026. 6. 16',
    AUTHOR: 'Open ALM',
    VERSION: 'Ver 1',
  },
});

const SAMPLES: Record<string, PptSlide[]> = {
  // 경영진 보고 — KPI 대시보드
  'a4-exec-kpi': [
    COVER('2026년 5월 경영실적 보고'),
    {
      layout: 'a4-exec-kpi-dashboard',
      data: {
        HEADER: '경영실적 종합 (2026. 5)',
        KPIS: [
          { label: '매출', value: '1,284', unit: '억', delta: '+8.2%', vs: 'YoY', up: true },
          { label: '영업이익', value: '142', unit: '억', delta: '+12.1%', vs: 'YoY', up: true },
          { label: '영업이익률', value: '11.0', unit: '%', delta: '+0.4%p', vs: 'MoM', up: true },
          { label: '재고일수', value: '38', unit: '일', delta: '-3일', vs: 'MoM', up: false },
        ],
        SUMMARY_TITLE: '핵심 요약',
        SUMMARY_ITEMS: [
          '전동화 부품 매출 증가로 전사 매출 8.2% 성장',
          '원가 개선·고부가 믹스로 영업이익률 11% 회복',
          '재고일수 단축으로 운전자본 부담 완화',
        ],
        CHART_TITLE: '월별 매출 추이 (억)',
        CHART_LABELS: ['1월', '2월', '3월', '4월', '5월'],
        CHART_VALUES: [1080, 1120, 1185, 1210, 1284],
        ISSUES_TITLE: '주요 이슈',
        ISSUES: [
          { sev: 'HIGH', title: '원자재가 변동', desc: '구리·알루미늄 단가 상승 압박' },
          { sev: 'MID', title: '해외법인 환율', desc: '달러 약세로 환차손 발생' },
        ],
        ACTIONS_TITLE: '차월 액션 아이템',
        ACTIONS: [
          { num: '01', title: '원가절감 TF 가동', owner: '구매본부' },
          { num: '02', title: '환헤지 비중 확대', owner: '재무팀' },
        ],
      },
    },
  ],

  // 경영진 보고 — 사업부 스코어카드
  'a4-scorecard': [
    COVER('사업부별 실적 스코어카드'),
    {
      layout: 'a4-division-scorecard',
      data: {
        HEADER: '사업부별 실적 스코어카드 (2026. 5)',
        HEADLINE_EYEBROW: 'EXECUTIVE HEADLINE',
        HEADLINE_MAIN: '전동화 사업부가 전사 성장을 견인',
        HEADLINE_SUB: '공조 사업부는 계획 대비 부진 — 원가 개선 필요',
        AGG_KPIS: [
          { label: '전사 매출', value: '1,284', unit: '억', delta: '+8.2%', up: true },
          { label: '평균 달성률', value: '102', unit: '%', delta: '+3%p', up: true },
          { label: '영업이익', value: '142', unit: '억', delta: '+12%', up: true },
        ],
        DIVISIONS: [
          { name: '전동화', plan: 520, actual: 588, delta: '+13%', delta_up: true, bold: true, status: 'good' },
          { name: '공조', plan: 480, actual: 441, delta: '-8%', delta_up: false, status: 'bad' },
          { name: '열관리', plan: 300, actual: 312, delta: '+4%', delta_up: true, status: 'warn' },
        ],
        ISSUES_TITLE: '핵심 이슈 · 위험 신호',
        ISSUES: [
          { div: '공조', title: '수주 감소', desc: '신규 고객 확보 지연' },
          { div: '전사', title: '원자재가', desc: '구리 단가 상승 지속' },
        ],
        DECISIONS_TITLE: '차월 의사결정 사항',
        DECISIONS: [
          { q: '공조 사업부 원가 개선안 승인 여부', owner: '경영회의' },
          { q: '전동화 증설 투자 집행 시점', owner: '투자심의' },
        ],
      },
    },
  ],

  // 경영회의 회의록
  'a4-minutes': [
    COVER('2026년 6월 경영회의 회의록'),
    {
      layout: 'a4-meeting-minutes',
      data: {
        HEADER: '경영회의 회의록 (2026. 6. 16)',
        META_ITEMS: [
          { label: '일시', value: '2026.6.16 14:00' },
          { label: '장소', value: '본사 대회의실' },
          { label: '주재', value: '대표이사' },
          { label: '참석', value: '임원 7명' },
        ],
        AGENDAS: [
          { num: '01', title: '5월 실적 검토', discussion: '매출 8.2% 성장, 공조 부진 공유', decision: '공조 원가 TF 구성' },
          { num: '02', title: '하반기 투자', discussion: '전동화 증설 필요성 논의', decision: '투자심의 상정' },
          { num: '03', title: '품질 이슈', discussion: '외관검사 자동화 진행현황', decision: 'AI 비전 확대 적용' },
        ],
        ACTION_ITEMS: [
          { no: '1', task: '공조 원가절감 TF 구성', owner: '생산본부', due: '6/30', status: 'in_progress' },
          { no: '2', task: '전동화 증설안 작성', owner: '전략기획', due: '7/15', status: 'planned' },
          { no: '3', task: 'AI 비전 라인 확대 계획', owner: '기술연구소', due: '7/31', status: 'planned' },
        ],
        NEXT_MEETING: '2026.7.14 14:00',
        SIGNOFF: '작성 경영기획팀 / 승인 대표이사',
      },
    },
  ],

  // Open ALM 사내 진행보고 "하우스 스타일"(corporate-house / TEST)은 미리보기를 노출하지 않는다
  // (테스트용 양식 — 템플릿 카드의 미리보기 버튼 숨김). 샘플 슬라이드를 정의하지 않으면
  // getTemplateSampleSlides 가 빈 배열을 반환해 canPreview 가 false 가 된다.

  // HTML 경로(corporate-*) — 본문은 HTML 렌더라 React 샘플이 없어 Open ALM 표지까지 보여준다.
  'corporate-seminar': [COVER('AI 컨퍼런스 참석 보고')],
  'corporate-education': [COVER('AI 비전 실무 교육 참가 보고서')],
  'corporate-meeting': [COVER('주간 업무 회의록')],
};

/** family 의 미리보기 샘플 슬라이드. 없으면 빈 배열. */
export function getTemplateSampleSlides(familyId: string | null | undefined): PptSlide[] {
  if (!familyId) return [];
  return SAMPLES[familyId] ?? [];
}

// Customer-specific static previews are intentionally not bundled. Live samples above
// remain available without carrying branded screenshots in the repository.
const STATIC_PREVIEWS: Record<string, string[]> = {};

/** family 의 번들 정적 미리보기 이미지 URL. 없으면 빈 배열. */
export function getTemplateStaticPreviews(familyId: string | null | undefined): string[] {
  if (!familyId) return [];
  return STATIC_PREVIEWS[familyId] ?? [];
}
