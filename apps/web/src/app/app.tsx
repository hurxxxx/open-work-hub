import type { AuthUser } from './auth-api';
import {
  AppShell,
  Button,
  MetricInline,
  Panel,
  SidebarNav,
  SplitPane,
  StatusBadge,
  ToastProvider,
  ToastViewport,
  Topbar,
} from '@aidoo/ui';
import { useEffect, useState } from 'react';

import {
  AUTH_TOKEN_STORAGE_KEY,
  getBootstrapStatus,
  login,
  logout,
  me,
  setupFirstUser,
} from './auth-api';
import { AuthScreen } from './auth-screen';

import { SearchWorkbench } from '../domains/documents/search-workbench';
import { DraftPreview } from '../domains/drafts/draft-preview';
import { PmsPreview } from '../domains/pms/pms-preview';
import { PmsWorkspace } from '../domains/pms/pms-workspace';
import { PlmPreview } from '../domains/plm/plm-preview';

type AuthPhase = 'loading' | 'login' | 'setup' | 'authenticated';
type PortalRouteId =
  | 'search'
  | 'meeting'
  | 'mailwriter'
  | 'patent-interpret'
  | 'patent-file'
  | 'patent-report'
  | 'drafteditor'
  | 'document'
  | 'compare'
  | 'fmea'
  | 'ppthelper'
  | 'qna'
  | 'news'
  | 'research'
  | 'meal'
  | 'requests'
  | 'plm'
  | 'pms'
  | 'admin-features'
  | 'admin-monitor'
  | 'admin-logs';

interface PortalRoute {
  id: PortalRouteId;
  path: string;
  aliases?: string[];
  label: string;
  breadcrumb: string;
  title: string;
  description: string;
  section:
    | 'core'
    | 'assistants'
    | 'patent'
    | 'platform'
    | 'operations'
    | 'admin';
  hint?: string;
  adminOnly?: boolean;
}

const PORTAL_ROUTES: PortalRoute[] = [
  {
    id: 'search',
    path: '/search',
    aliases: ['/documents'],
    label: '아이두 통합검색',
    breadcrumb: 'Legacy / Search / Grounded workspace',
    title: '아이두 통합검색',
    description:
      '레거시 통합검색 진입점을 현재 documents-rag 작업면으로 연결한 메인 검색 허브입니다.',
    section: 'core',
    hint: 'live',
  },
  {
    id: 'meeting',
    path: '/meeting',
    label: '회의록',
    breadcrumb: 'Legacy / Meeting / STT + summarization',
    title: '회의록',
    description:
      'WhisperX 기반 STT, 화자 분리, 회의록 요약을 현재 포털 구조로 이관할 대상입니다.',
    section: 'assistants',
    hint: 'stt',
  },
  {
    id: 'mailwriter',
    path: '/mailwriter',
    label: '메일 작성 도우미',
    breadcrumb: 'Legacy / Mail / Assist',
    title: '메일 작성 도우미',
    description:
      '수신 메일과 전달 의도를 바탕으로 업무 메일 초안을 생성하던 레거시 기능입니다.',
    section: 'assistants',
    hint: 'llm',
  },
  {
    id: 'patent-interpret',
    path: '/patent',
    label: '특허 해석 도우미',
    breadcrumb: 'Legacy / Patent / Interpretation',
    title: '특허 해석 도우미',
    description:
      'KIPRIS 연계와 문헌 해석 흐름을 새 포털에서 다시 설계해야 하는 특허 업무 진입점입니다.',
    section: 'patent',
    hint: 'kipris',
  },
  {
    id: 'patent-file',
    path: '/patent-file',
    label: '특허 출원 도우미',
    breadcrumb: 'Legacy / Patent / Filing',
    title: '특허 출원 도우미',
    description:
      '특허 출원 초안과 제출 보조 흐름을 이관할 대상입니다.',
    section: 'patent',
    hint: 'draft',
  },
  {
    id: 'patent-report',
    path: '/patent-analyze2',
    label: 'AI 특허 보고서',
    breadcrumb: 'Legacy / Patent / Report',
    title: 'AI 특허 보고서',
    description:
      '특허 분석 결과를 보고서 형태로 정리하던 레거시 기능입니다.',
    section: 'patent',
    hint: 'report',
  },
  {
    id: 'drafteditor',
    path: '/drafteditor',
    aliases: ['/drafts'],
    label: '기안작성 도우미',
    breadcrumb: 'Legacy / Draft / Generation',
    title: '기안작성 도우미',
    description:
      '공문, 협조전, 구매 요청, 보고서 등 업무 기안 작성과 내보내기 흐름을 담당합니다.',
    section: 'core',
    hint: 'live',
  },
  {
    id: 'document',
    path: '/document',
    label: '문서 번역/요약',
    breadcrumb: 'Legacy / Document / OCR + summarization',
    title: '문서 번역/요약',
    description:
      '문서 업로드, OCR, 번역, 요약을 결합하던 레거시 기능입니다.',
    section: 'core',
    hint: 'ocr',
  },
  {
    id: 'compare',
    path: '/compare',
    label: '규격서 비교',
    breadcrumb: 'Legacy / Compare / Specifications',
    title: '규격서 비교',
    description:
      '규격 변경을 나란히 비교해 검토 포인트를 찾는 비교 작업면입니다.',
    section: 'core',
    hint: 'spec',
  },
  {
    id: 'fmea',
    path: '/fmea',
    label: 'FMEA 비교',
    breadcrumb: 'Legacy / Compare / FMEA',
    title: 'FMEA 비교',
    description:
      '위험 항목과 조치안을 비교하는 FMEA 전용 검토 화면입니다.',
    section: 'core',
    hint: 'risk',
  },
  {
    id: 'ppthelper',
    path: '/ppthelper',
    label: 'PPT 발표 도우미',
    breadcrumb: 'Legacy / Presentation / Coaching',
    title: 'PPT 발표 도우미',
    description:
      '발표 자료 요약, 발표 스크립트, 질의응답 준비를 돕는 기능입니다.',
    section: 'assistants',
    hint: 'coach',
  },
  {
    id: 'qna',
    path: '/qna',
    label: '사내 관리팀 Q&A',
    breadcrumb: 'Legacy / Q&A / Internal support',
    title: '사내 관리팀 Q&A',
    description:
      '사내 관리팀 문서와 자주 묻는 질문을 근거 기반으로 찾는 지원 기능입니다.',
    section: 'assistants',
    hint: 'faq',
  },
  {
    id: 'news',
    path: '/news',
    label: '뉴스',
    breadcrumb: 'Legacy / News / Monitoring',
    title: '뉴스',
    description:
      '자동차 공조와 산업 이슈를 수집해 빠르게 훑는 외부 뉴스 모니터링 화면입니다.',
    section: 'assistants',
    hint: 'crawl',
  },
  {
    id: 'research',
    path: '/research',
    label: '산업 리포트',
    breadcrumb: 'Legacy / Research / Industry reports',
    title: '산업 리포트',
    description:
      '외부 산업 리포트와 동향 요약을 모아 보는 연구 지원 기능입니다.',
    section: 'assistants',
    hint: 'intel',
  },
  {
    id: 'meal',
    path: '/meal',
    label: '구내식당 식단표',
    breadcrumb: 'Legacy / Ops / Meal board',
    title: '구내식당 식단표',
    description:
      '그룹웨어에서 식단표 이미지를 가져와 OCR로 정리하던 생활형 지원 기능입니다.',
    section: 'operations',
    hint: 'ocr',
  },
  {
    id: 'requests',
    path: '/requests',
    label: '요청사항',
    breadcrumb: 'Legacy / Ops / Feature requests',
    title: '요청사항',
    description:
      '사용자 요청을 접수하고 운영자가 상태를 관리하던 피드백 보드입니다.',
    section: 'operations',
    hint: 'ops',
  },
  {
    id: 'plm',
    path: '/plm',
    label: 'PLM',
    breadcrumb: 'Platform / PLM / Approved queries',
    title: 'PLM 조회 작업면',
    description:
      '승인된 PLM 조회 템플릿과 결과 미리보기를 검토하고, 이후 읽기 전용 조회 흐름으로 확장할 수 있는 화면입니다.',
    section: 'platform',
    hint: 'preview',
  },
  {
    id: 'pms',
    path: '/pms',
    label: 'PMS',
    breadcrumb: 'Platform / PMS / Projects / Issues',
    title: 'PMS 프로젝트 관리',
    description:
      '프로젝트, 마일스톤, 이슈, 진행률을 API 중심 구조로 운영하는 실제 PMS 작업면입니다.',
    section: 'platform',
    hint: 'live',
  },
  {
    id: 'admin-features',
    path: '/admin-features',
    label: '기능 관리',
    breadcrumb: 'Admin / Features / Controls',
    title: '기능 관리',
    description:
      '레거시의 기능 토글과 접근 제어를 새 관리자 화면으로 옮길 대상입니다.',
    section: 'admin',
    hint: 'admin',
    adminOnly: true,
  },
  {
    id: 'admin-monitor',
    path: '/admin-monitor',
    label: '시스템 모니터링',
    breadcrumb: 'Admin / Monitor / Runtime',
    title: '시스템 모니터링',
    description:
      '크롤러, 배치, 자원 상태를 한 화면에서 보는 운영 모니터링 영역입니다.',
    section: 'admin',
    hint: 'admin',
    adminOnly: true,
  },
  {
    id: 'admin-logs',
    path: '/admin-logs',
    label: '사용 로그',
    breadcrumb: 'Admin / Usage / Logs',
    title: '사용 로그',
    description:
      '기능 사용량과 요청 로그를 확인하는 관리자 감사 화면입니다.',
    section: 'admin',
    hint: 'admin',
    adminOnly: true,
  },
];

const DEFAULT_PORTAL_PATH = '/search';

interface PortalWorkspaceProps {
  user: AuthUser;
  token: string;
  onLogout: () => Promise<void>;
}

function normalizePortalPath(pathname: string): string {
  const normalized =
    pathname.length > 1 && pathname.endsWith('/') ? pathname.slice(0, -1) : pathname;

  if (!normalized || normalized === '/') {
    return DEFAULT_PORTAL_PATH;
  }

  return (
    PORTAL_ROUTES.find(
      (route) => route.path === normalized || route.aliases?.includes(normalized),
    )?.path ?? DEFAULT_PORTAL_PATH
  );
}

function PlaceholderPage({
  eyebrow,
  title,
  description,
  actionLabel,
}: {
  eyebrow: string;
  title: string;
  description: string;
  actionLabel?: string;
}) {
  return (
    <Panel eyebrow={eyebrow} title={title} description={description}>
      <div className="grid gap-3">
        <div className="grid gap-1.5 rounded-[var(--ui-radius-md)] border border-dashed border-[var(--ui-color-border-strong)] bg-[var(--ui-color-surface-subtle)] px-4 py-4">
          <strong className="text-[0.92rem] text-[var(--ui-color-ink)]">
            {title} 연결 준비 중
          </strong>
          <p className="m-0 text-[0.84rem] text-[var(--ui-color-ink-muted)]">{description}</p>
        </div>
        {actionLabel ? (
          <div className="flex justify-end">
            <Button variant="secondary">{actionLabel}</Button>
          </div>
        ) : null}
      </div>
    </Panel>
  );
}

function MigrationPage({
  eyebrow,
  title,
  description,
  status,
  legacyRefs,
  nextConnection,
  metrics,
}: {
  eyebrow: string;
  title: string;
  description: string;
  status: string;
  legacyRefs: string[];
  nextConnection: string;
  metrics: Array<{ label: string; value: string }>;
}) {
  return (
    <div className="grid gap-4">
      <Panel
        eyebrow={eyebrow}
        title={title}
        description={description}
        status={<StatusBadge>{status}</StatusBadge>}
      >
        <div className="grid gap-4">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {metrics.map((metric) => (
              <MetricInline key={metric.label} label={metric.label} value={metric.value} />
            ))}
          </div>
          <div className="overflow-hidden rounded-[var(--ui-radius-md)] border border-[var(--ui-color-border)] bg-[var(--ui-color-surface-subtle)]">
            <div className="grid grid-cols-[140px_minmax(0,1fr)] gap-3 border-b border-b-[var(--ui-color-border)] px-4 py-3">
              <strong className="text-[0.72rem] font-semibold uppercase tracking-[0.08em] text-[var(--ui-color-ink-subtle)]">
                Legacy source
              </strong>
              <span className="text-[0.86rem] text-[var(--ui-color-ink)]">
                {legacyRefs.join(' · ')}
              </span>
            </div>
            <div className="grid grid-cols-[140px_minmax(0,1fr)] gap-3 border-b border-b-[var(--ui-color-border)] px-4 py-3">
              <strong className="text-[0.72rem] font-semibold uppercase tracking-[0.08em] text-[var(--ui-color-ink-subtle)]">
                Current surface
              </strong>
              <span className="text-[0.86rem] text-[var(--ui-color-ink)]">
                AIDOO workspace scaffold
              </span>
            </div>
            <div className="grid grid-cols-[140px_minmax(0,1fr)] gap-3 px-4 py-3">
              <strong className="text-[0.72rem] font-semibold uppercase tracking-[0.08em] text-[var(--ui-color-ink-subtle)]">
                Next connection
              </strong>
              <span className="text-[0.86rem] text-[var(--ui-color-ink)]">
                {nextConnection}
              </span>
            </div>
          </div>
        </div>
      </Panel>
    </div>
  );
}

function renderWorkspaceContent(routeId: PortalRouteId, token: string) {
  switch (routeId) {
    case 'search':
      return (
        <SplitPane
          main={<SearchWorkbench token={token} />}
          mobileAsideLabel="보조 작업 패널 보기"
          aside={
            <>
              <PlmPreview />
              <DraftPreview />
              <PmsPreview />
            </>
          }
        />
      );
    case 'meeting':
      return (
        <MigrationPage
          description="오디오 업로드, STT 진행 상태, 화자 분리, 요약 프롬프트를 한 흐름으로 묶었던 회의록 기능입니다."
          eyebrow="Legacy assistant"
          legacyRefs={[
            'routes/meeting.py',
            'templates/sections/meeting.html',
            'static/screenshots/meeting.png',
          ]}
          metrics={[
            { label: 'Input', value: '회의 음성 파일 업로드 + STT 상태 폴링' },
            { label: 'Core flow', value: 'WhisperX STT + diarization + 회의록 생성' },
            { label: 'Migration target', value: '파일 업로드 파이프라인 + 요약 템플릿' },
          ]}
          nextConnection="업로드/작업 큐를 붙인 뒤 회의록 생성 시나리오를 별도 도메인으로 분리"
          status="legacy reference"
          title="회의록"
        />
      );
    case 'mailwriter':
      return (
        <MigrationPage
          description="기존 메일 본문과 전달 의도, 말투, 언어를 받아 메일 초안을 생성하던 보조 기능입니다."
          eyebrow="Legacy assistant"
          legacyRefs={[
            'routes/mailwriter.py',
            'templates/sections/mailwriter.html',
            'static/screenshots/mailwriter.png',
          ]}
          metrics={[
            { label: 'Input', value: '원문 메일 + 전달 의도 + tone + lang' },
            { label: 'Output', value: '제목 포함 업무 메일 초안' },
            { label: 'Migration target', value: '사내 커뮤니케이션 보조 작업면' },
          ]}
          nextConnection="메일 초안 생성 API와 승인 전 미리보기 편집기를 연결"
          status="legacy reference"
          title="메일 작성 도우미"
        />
      );
    case 'patent-interpret':
      return (
        <MigrationPage
          description="특허 문헌을 읽고 해석 포인트를 요약하던 특허 지원 기능입니다."
          eyebrow="Legacy patent"
          legacyRefs={[
            'routes/patent.py',
            'templates/sections/patent.html',
            'static/screenshots/patent.png',
          ]}
          metrics={[
            { label: 'Input', value: '특허 번호 또는 본문 문헌' },
            { label: 'Core flow', value: 'KIPRIS 조회 + LLM 해석 보조' },
            { label: 'Migration target', value: '특허 문헌 리뷰 작업면' },
          ]}
          nextConnection="특허 검색 계약과 문헌 요약 출력 구조를 먼저 정의"
          status="legacy reference"
          title="특허 해석 도우미"
        />
      );
    case 'patent-file':
      return (
        <MigrationPage
          description="특허 출원 보조와 초안 구성을 돕던 기능입니다."
          eyebrow="Legacy patent"
          legacyRefs={[
            'routes/patent.py',
            'templates/sections/patent_file.html',
            'static/screenshots/patent-file.png',
          ]}
          metrics={[
            { label: 'Input', value: '발명 개요 + 청구항 관련 메모' },
            { label: 'Core flow', value: '출원 초안 보조 + 문안 정리' },
            { label: 'Migration target', value: 'draft-generation 확장' },
          ]}
          nextConnection="출원 초안 전용 템플릿과 근거 구조를 draft-generation에 연결"
          status="legacy reference"
          title="특허 출원 도우미"
        />
      );
    case 'patent-report':
      return (
        <MigrationPage
          description="특허 분석 결과를 보고서 형태로 묶어주는 기능입니다."
          eyebrow="Legacy patent"
          legacyRefs={[
            'routes/patent.py',
            'templates/sections/patent_analyze2.html',
            'static/screenshots/patent-analyze2.png',
          ]}
          metrics={[
            { label: 'Input', value: '특허군 또는 분석 요청' },
            { label: 'Output', value: 'AI 특허 보고서' },
            { label: 'Migration target', value: '보고서 생성 워크플로우' },
          ]}
          nextConnection="특허 분석 출력 스키마와 보고서 export 경로를 정의"
          status="legacy reference"
          title="AI 특허 보고서"
        />
      );
    case 'drafteditor':
      return (
        <div className="grid gap-5">
          <DraftPreview />
          <MigrationPage
            description="협조전, 구매 요청, 보고서, 회의록 등 다양한 업무 기안 형식을 생성하고 그룹웨어용 HTML로 내보내던 기능입니다."
            eyebrow="Legacy draft"
            legacyRefs={[
              'routes/drafteditor.py',
              'templates/sections/drafteditor.html',
              'static/screenshots/drafteditor.png',
            ]}
            metrics={[
              { label: 'Input', value: '업무 메모 + 기안 타입' },
              { label: 'Output', value: '정형 기안서 + 그룹웨어 호환 HTML' },
              { label: 'Migration target', value: 'draft-generation + export queue' },
            ]}
            nextConnection="템플릿 선택과 편집기, 내보내기 큐를 연결"
            status="connected preview"
            title="기안작성 도우미"
          />
        </div>
      );
    case 'document':
      return (
        <MigrationPage
          description="업로드 문서의 OCR, 번역, 요약을 하나의 작업면에서 처리하던 기능입니다."
          eyebrow="Legacy document"
          legacyRefs={[
            'routes/document.py',
            'templates/sections/document.html',
            'static/screenshots/document.png',
          ]}
          metrics={[
            { label: 'Input', value: 'PDF/이미지/문서 업로드' },
            { label: 'Core flow', value: 'OCR + 번역 + 요약' },
            { label: 'Migration target', value: 'ocr-pipeline + documents-rag' },
          ]}
          nextConnection="OCR 파이프라인 결과를 검색 인덱스와 연결"
          status="legacy reference"
          title="문서 번역/요약"
        />
      );
    case 'compare':
      return (
        <MigrationPage
          description="규격서 두 버전을 비교해 변경점을 검토하는 문서 비교 기능입니다."
          eyebrow="Legacy compare"
          legacyRefs={[
            'templates/sections/compare.html',
            'static/screenshots/compare.png',
          ]}
          metrics={[
            { label: 'Input', value: '비교 대상 규격 문서 2종' },
            { label: 'Output', value: '변경 포인트와 검토 항목' },
            { label: 'Migration target', value: 'documents-rag side-by-side diff' },
          ]}
          nextConnection="문서 선택과 변경 하이라이트 뷰를 설계"
          status="legacy reference"
          title="규격서 비교"
        />
      );
    case 'fmea':
      return (
        <MigrationPage
          description="FMEA 항목 변경과 리스크 차이를 검토하던 비교 기능입니다."
          eyebrow="Legacy compare"
          legacyRefs={['templates/sections/fmea.html', 'static/screenshots/fmea.png']}
          metrics={[
            { label: 'Input', value: 'FMEA 시트 2종' },
            { label: 'Output', value: '리스크/조치 변경 검토' },
            { label: 'Migration target', value: '도메인 전용 diff workbench' },
          ]}
          nextConnection="표 구조 diff와 리스크 강조 규칙을 정리"
          status="legacy reference"
          title="FMEA 비교"
        />
      );
    case 'ppthelper':
      return (
        <MigrationPage
          description="발표 자료의 요약과 발표 스크립트 정리를 보조하던 기능입니다."
          eyebrow="Legacy assistant"
          legacyRefs={[
            'templates/sections/ppthelper.html',
            'static/screenshots/ppthelper.png',
          ]}
          metrics={[
            { label: 'Input', value: '발표 자료 핵심 포인트' },
            { label: 'Output', value: '발표 스크립트 + 예상 질문' },
            { label: 'Migration target', value: '프레젠테이션 보조 작업면' },
          ]}
          nextConnection="문서/초안 근거와 연결된 발표 스크립트 생성으로 확장"
          status="legacy reference"
          title="PPT 발표 도우미"
        />
      );
    case 'qna':
      return (
        <MigrationPage
          description="관리팀 문서와 FAQ를 기반으로 답변을 찾는 사내 질의응답 기능입니다."
          eyebrow="Legacy assistant"
          legacyRefs={['routes/search.py', 'templates/sections/qna.html', 'static/screenshots/qna.png']}
          metrics={[
            { label: 'Input', value: '사내 제도/운영 질문' },
            { label: 'Core flow', value: 'FAQ 문서 검색 + 답변 생성' },
            { label: 'Migration target', value: '권한 필터된 내부 지원 검색' },
          ]}
          nextConnection="사내 운영 문서를 별도 인덱스로 분리하고 ACL을 적용"
          status="legacy reference"
          title="사내 관리팀 Q&A"
        />
      );
    case 'news':
      return (
        <MigrationPage
          description="차량 공조와 자동차 산업 관련 뉴스를 크롤링해 보여주던 기능입니다."
          eyebrow="Legacy monitoring"
          legacyRefs={['templates/sections/news.html', 'static/screenshots/news.png']}
          metrics={[
            { label: 'Input', value: '자동차 공조 관련 키워드' },
            { label: 'Core flow', value: '뉴스 수집 + 선별' },
            { label: 'Migration target', value: '외부 신호 모니터링 보드' },
          ]}
          nextConnection="뉴스 수집 계약과 저장소를 API로 분리"
          status="legacy reference"
          title="뉴스"
        />
      );
    case 'research':
      return (
        <MigrationPage
          description="산업 리포트와 시장 자료를 수집해 보여주던 연구 지원 화면입니다."
          eyebrow="Legacy monitoring"
          legacyRefs={[
            'routes/research.py',
            'templates/sections/research.html',
            'static/screenshots/research.png',
          ]}
          metrics={[
            { label: 'Input', value: '산업 리포트 수집 대상' },
            { label: 'Output', value: '요약된 리포트 목록' },
            { label: 'Migration target', value: '외부 인텔리전스 허브' },
          ]}
          nextConnection="리포트 수집 파이프라인과 요약 저장 계약을 정의"
          status="legacy reference"
          title="산업 리포트"
        />
      );
    case 'meal':
      return (
        <MigrationPage
          description="그룹웨어에 올라온 식단표 이미지를 가져와 OCR로 보여주던 생활형 지원 기능입니다."
          eyebrow="Legacy ops"
          legacyRefs={['routes/meal.py', 'templates/sections/meal.html', 'static/screenshots/meal.png']}
          metrics={[
            { label: 'Input', value: '그룹웨어 식단표 이미지' },
            { label: 'Core flow', value: '다운로드 + OCR + 질의응답' },
            { label: 'Migration target', value: '사내 생활 정보 보드' },
          ]}
          nextConnection="그룹웨어 연동 여부를 정한 뒤 별도 생활형 도메인으로 분리"
          status="legacy reference"
          title="구내식당 식단표"
        />
      );
    case 'requests':
      return (
        <MigrationPage
          description="사용자 요청 등록과 관리자 피드백, 상태 변경을 다루던 운영 피드백 기능입니다."
          eyebrow="Legacy ops"
          legacyRefs={[
            'routes/requests.py',
            'templates/sections/requests.html',
            'static/screenshots/requests.png',
          ]}
          metrics={[
            { label: 'Input', value: '요청 제목/내용/분류' },
            { label: 'Core flow', value: '사용자 등록 + 관리자 상태 관리' },
            { label: 'Migration target', value: '제품 피드백 보드' },
          ]}
          nextConnection="DB 기반 요청사항 CRUD와 관리자 응답 화면을 추가"
          status="legacy reference"
          title="요청사항"
        />
      );
    case 'plm':
      return (
        <div className="grid gap-5">
          <PlmPreview />
          <PlaceholderPage
            actionLabel="읽기 전용 조회 확장 예정"
            description="승인된 조회 템플릿을 실제 PLM 검색 실행 흐름에 연결하는 다음 단계 작업면입니다."
            eyebrow="PLM"
            title="실행 쿼리 미리보기"
          />
        </div>
      );
    case 'pms':
      return <PmsWorkspace token={token} />;
    case 'admin-features':
      return (
        <MigrationPage
          description="레거시의 기능 활성화, 부서별 접근 제어, 메뉴 노출 관리 기능을 옮길 관리자 화면입니다."
          eyebrow="Admin"
          legacyRefs={[
            'routes/admin.py',
            'templates/sections/admin.html',
            'static/screenshots/admin-features.png',
          ]}
          metrics={[
            { label: 'Input', value: '기능 플래그 + 부서 접근 규칙' },
            { label: 'Core flow', value: '관리자 기능 활성/비활성 제어' },
            { label: 'Migration target', value: 'RBAC + feature controls' },
          ]}
          nextConnection="역할 기반 권한 모델과 기능 플래그 저장소를 정의"
          status="admin preview"
          title="기능 관리"
        />
      );
    case 'admin-monitor':
      return (
        <MigrationPage
          description="배치 작업, 모델 상태, 시스템 자원 상태를 모니터링하던 운영 화면입니다."
          eyebrow="Admin"
          legacyRefs={[
            'templates/sections/admin_monitor.html',
            'static/screenshots/admin-monitor.png',
          ]}
          metrics={[
            { label: 'Input', value: '작업 큐/자원 상태/크롤러 상태' },
            { label: 'Core flow', value: '시스템 상태 한눈에 확인' },
            { label: 'Migration target', value: '운영 대시보드' },
          ]}
          nextConnection="잡 상태와 서버 헬스 데이터를 API로 노출"
          status="admin preview"
          title="시스템 모니터링"
        />
      );
    case 'admin-logs':
      return (
        <MigrationPage
          description="레거시의 기능 사용량과 요청 로그를 조회하던 관리자 감사 화면입니다."
          eyebrow="Admin"
          legacyRefs={[
            'routes/analytics.py',
            'templates/sections/admin_logs.html',
            'static/screenshots/admin-logs.png',
          ]}
          metrics={[
            { label: 'Input', value: '사용자/기능/기간 필터' },
            { label: 'Core flow', value: '기능 사용량 집계 + 로그 조회' },
            { label: 'Migration target', value: '감사 로그와 제품 분석' },
          ]}
          nextConnection="인증/검색/생성 사용 이력을 DB에 적재"
          status="admin preview"
          title="사용 로그"
        />
      );
  }
}

function PortalWorkspace({ user, token, onLogout }: PortalWorkspaceProps) {
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [currentPath, setCurrentPath] = useState(() =>
    normalizePortalPath(window.location.pathname),
  );
  const visibleRoutes = PORTAL_ROUTES.filter((route) => !route.adminOnly || user.is_admin);

  useEffect(() => {
    const syncedPath = normalizePortalPath(window.location.pathname);
    if (window.location.pathname !== syncedPath) {
      window.history.replaceState({}, '', syncedPath);
    }
    setCurrentPath(syncedPath);

    function handlePopState() {
      setCurrentPath(normalizePortalPath(window.location.pathname));
    }

    window.addEventListener('popstate', handlePopState);
    return () => {
      window.removeEventListener('popstate', handlePopState);
    };
  }, []);

  useEffect(() => {
    setMobileSidebarOpen(false);
  }, [currentPath]);

  const currentRoute =
    visibleRoutes.find((route) => route.path === currentPath) ?? visibleRoutes[0];

  useEffect(() => {
    if (!visibleRoutes.some((route) => route.path === currentPath)) {
      const fallbackPath = visibleRoutes[0]?.path ?? DEFAULT_PORTAL_PATH;
      window.history.replaceState({}, '', fallbackPath);
      setCurrentPath(fallbackPath);
    }
  }, [currentPath, visibleRoutes]);

  function navigateTo(path: string) {
    if (window.location.pathname !== path) {
      window.history.pushState({}, '', path);
    }
    setCurrentPath(path);
  }

  return (
    <ToastProvider>
      <AppShell
        mobileSidebar={{
          open: mobileSidebarOpen,
          onOpenChange: setMobileSidebarOpen,
          label: '업무 메뉴',
        }}
        sidebar={
          <SidebarNav
            brand={{ eyebrow: '두원공조', title: '아이두' }}
            launcher={{
              label: '아이두 통합검색',
              hint: '⌘K',
              onSelect: () => navigateTo('/search'),
            }}
            sections={[
              {
                id: 'core',
                label: 'Core tools',
                items: visibleRoutes
                  .filter((route) => route.section === 'core')
                  .map((route) => ({
                    id: route.id,
                    label: route.label,
                    hint: route.hint,
                    active: currentRoute.id === route.id,
                    onSelect: () => navigateTo(route.path),
                  })),
              },
              {
                id: 'assistants',
                label: 'Assistants',
                items: visibleRoutes
                  .filter((route) => route.section === 'assistants')
                  .map((route) => ({
                    id: route.id,
                    label: route.label,
                    hint: route.hint,
                    active: currentRoute.id === route.id,
                    onSelect: () => navigateTo(route.path),
                  })),
              },
              {
                id: 'patent',
                label: 'Patent',
                items: visibleRoutes
                  .filter((route) => route.section === 'patent')
                  .map((route) => ({
                    id: route.id,
                    label: route.label,
                    hint: route.hint,
                    active: currentRoute.id === route.id,
                    onSelect: () => navigateTo(route.path),
                  })),
              },
              {
                id: 'platform',
                label: 'Platform',
                items: visibleRoutes
                  .filter((route) => route.section === 'platform')
                  .map((route) => ({
                    id: route.id,
                    label: route.label,
                    hint: route.hint,
                    active: currentRoute.id === route.id,
                    onSelect: () => navigateTo(route.path),
                  })),
              },
              {
                id: 'operations',
                label: 'Operations',
                items: visibleRoutes
                  .filter((route) => route.section === 'operations')
                  .map((route) => ({
                    id: route.id,
                    label: route.label,
                    hint: route.hint,
                    active: currentRoute.id === route.id,
                    onSelect: () => navigateTo(route.path),
                  })),
              },
              ...(user.is_admin
                ? [
                    {
                      id: 'admin',
                      label: 'Admin',
                      items: visibleRoutes
                        .filter((route) => route.section === 'admin')
                        .map((route) => ({
                          id: route.id,
                          label: route.label,
                          hint: route.hint,
                          active: currentRoute.id === route.id,
                          onSelect: () => navigateTo(route.path),
                        })),
                    },
                  ]
                : []),
            ]}
            footerBadges={['Legacy menu mapped', user.is_admin ? 'Admin' : 'Self account']}
          />
        }
        header={
          <Topbar
            breadcrumb={currentRoute.breadcrumb}
            title={currentRoute.title}
            actions={
              <>
                <StatusBadge>{user.full_name}</StatusBadge>
                {currentRoute.id === 'search' ? (
                  <>
                    <Button className="max-[980px]:hidden" variant="secondary">
                      근거 새로고침
                    </Button>
                    <Button className="max-[980px]:hidden" variant="secondary">
                      저장된 질의
                    </Button>
                    <Button className="max-[980px]:hidden" variant="primary">
                      초안 만들기
                    </Button>
                  </>
                ) : null}
                <StatusBadge className="max-[980px]:hidden">{currentRoute.label}</StatusBadge>
                <Button variant="secondary" onClick={() => void onLogout()}>
                  로그아웃
                </Button>
              </>
            }
          />
        }
      >
        {renderWorkspaceContent(currentRoute.id, token)}
      </AppShell>
      <ToastViewport />
    </ToastProvider>
  );
}

export function App() {
  const [phase, setPhase] = useState<AuthPhase>('loading');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [token, setToken] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function bootstrap() {
      try {
        const status = await getBootstrapStatus();
        if (!active) {
          return;
        }

        if (status.requires_setup) {
          localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
          setToken(null);
          setCurrentUser(null);
          setPhase('setup');
          return;
        }

        const savedToken = localStorage.getItem(AUTH_TOKEN_STORAGE_KEY);
        if (!savedToken) {
          setPhase('login');
          return;
        }

        try {
          const user = await me(savedToken);
          if (!active) {
            return;
          }
          setToken(savedToken);
          setCurrentUser(user);
          setPhase('authenticated');
        } catch {
          localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
          setToken(null);
          setCurrentUser(null);
          setPhase('login');
        }
      } catch (caughtError) {
        if (!active) {
          return;
        }
        setError(
          caughtError instanceof Error
            ? caughtError.message
            : '인증 서버에 연결하지 못했습니다.',
        );
        setPhase('login');
      }
    }

    void bootstrap();

    return () => {
      active = false;
    };
  }, []);

  async function handleSetup(payload: {
    fullName: string;
    email: string;
    password: string;
  }) {
    setBusy(true);
    setError(null);
    try {
      const session = await setupFirstUser(payload);
      localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, session.token);
      setToken(session.token);
      setCurrentUser(session.user);
      setPhase('authenticated');
    } catch (caughtError) {
      setError(
        caughtError instanceof Error ? caughtError.message : '계정 생성에 실패했습니다.',
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleLogin(payload: { email: string; password: string }) {
    setBusy(true);
    setError(null);
    try {
      const session = await login(payload);
      localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, session.token);
      setToken(session.token);
      setCurrentUser(session.user);
      setPhase('authenticated');
    } catch (caughtError) {
      setError(
        caughtError instanceof Error ? caughtError.message : '로그인에 실패했습니다.',
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleLogout() {
    if (token) {
      try {
        await logout(token);
      } catch {
        // Best-effort revoke; local state still needs to clear.
      }
    }

    localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
    setToken(null);
    setCurrentUser(null);
    setError(null);
    setPhase('login');
  }

  if (phase !== 'authenticated' || currentUser === null) {
    return (
      <AuthScreen
        busy={busy}
        error={error}
        mode={phase === 'authenticated' ? 'loading' : phase}
        onLogin={handleLogin}
        onSetup={handleSetup}
      />
    );
  }

  return <PortalWorkspace onLogout={handleLogout} token={token ?? ''} user={currentUser} />;
}

export default App;
