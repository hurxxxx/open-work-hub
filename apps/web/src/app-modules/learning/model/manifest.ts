export interface LearningLesson {
  /** Immutable identifier used as the stable key for DB-backed features
   *  (page notes, future reactions, etc.). Never change once assigned —
   *  title, slug, and file may be renamed but `id` must not. */
  id: string;
  /** ASCII URL slug — used in `/learning/<course>/<lesson>` path. */
  slug: string;
  /** Display title shown in the sidebar and breadcrumb. */
  title: string;
  /** Relative path from the repo-root `learning/` directory. Matches
   *  the key emitted by `content.ts` (course-slug/filename.md). */
  file: string;
  /** Optional one-liner for listing views. */
  summary?: string;
}

export interface LearningPart {
  /** Stable identifier, not shown in URLs today but reserved for future use. */
  slug: string;
  /** Section header rendered above the part's lessons in the sidebar. */
  title: string;
  /** Optional one-liner; reserved for future UI that introduces the part. */
  description?: string;
  lessons: LearningLesson[];
}

export interface LearningCourse {
  slug: string;
  title: string;
  description: string;
  parts: LearningPart[];
}

const VCF = 'vibe-coding-foundations';
const DSB = 'database-storage-basics';
const SLJ = 'service-launch-journey';
const ABC = 'ai-do-business-ai-curriculum';

export const LEARNING_COURSES: LearningCourse[] = [
  {
    slug: ABC,
    title: 'AI-DO LLM/RAG 운영 전문 교육',
    description:
      '기존 교재와 중복되는 AI 협업·저장소·서비스 출시 내용은 원본 코스로 연결하고, AI-DO PoC에 필요한 LLM/RAG 모델 지형, 검색, 승인, 평가 운영을 깊게 다룹니다.',
    parts: [
      {
        slug: 'intro',
        title: '시작하기',
        lessons: [
          { id: 'abc-000-index', slug: '00-index', title: '목차', file: `${ABC}/00-index.md` },
        ],
      },
      {
        slug: 'rag-operations',
        title: 'LLM/RAG 운영 전문 교육',
        lessons: [
          { id: 'abc-004-llm-routing', slug: '04-llm-routing', title: 'LLM 모델 지형과 모델 라우팅', file: `${ABC}/04-LLM기초와-모델라우팅.md` },
          { id: 'abc-005-rag-grounding', slug: '05-rag-grounding', title: 'RAG 패턴과 근거 기반 답변 설계', file: `${ABC}/05-RAG와-근거기반답변.md` },
          { id: 'abc-006-indexing-pipeline', slug: '06-indexing-pipeline', title: '문서 인덱싱 파이프라인', file: `${ABC}/06-문서인덱싱-파이프라인.md` },
          { id: 'abc-007-search-quality', slug: '07-search-quality', title: '검색 품질: 키워드·벡터·재정렬', file: `${ABC}/07-검색품질-키워드-벡터-재정렬.md` },
          { id: 'abc-008-approval-gate', slug: '08-approval-gate', title: 'AI 도구 호출과 승인 게이트', file: `${ABC}/08-AI도구호출과-승인게이트.md` },
          { id: 'abc-009-ops-quality', slug: '09-ops-quality', title: '평가·관측·운영 품질', file: `${ABC}/09-평가관측-운영품질.md` },
        ],
      },
    ],
  },
  {
    slug: VCF,
    title: '바이브 코딩 입문',
    description:
      '소프트웨어·프로그래밍 기본 개념부터 AI-DO 스택, 실전 바이브 코딩 워크플로까지. 전 구성원 공용 온보딩 트랙입니다.',
    parts: [
      {
        slug: 'intro',
        title: '시작하기',
        lessons: [
          { id: 'vcf-000-index', slug: '00-index', title: '목차', file: `${VCF}/00-index.md` },
        ],
      },
      {
        slug: 'foundations',
        title: '소프트웨어 공학 기초',
        lessons: [
          { id: 'vcf-001-orientation', slug: '01-orientation', title: '오리엔테이션', file: `${VCF}/01-오리엔테이션.md` },
          { id: 'vcf-002-software-basics', slug: '02-software-basics', title: '소프트웨어란 무엇인가', file: `${VCF}/02-소프트웨어란-무엇인가.md` },
          { id: 'vcf-003-programming-languages', slug: '03-programming-languages', title: '프로그래밍 언어와 런타임', file: `${VCF}/03-프로그래밍-언어와-런타임.md` },
          { id: 'vcf-004-git', slug: '04-git', title: '버전관리 · Git', file: `${VCF}/04-버전관리-Git.md` },
          { id: 'vcf-005-methodologies', slug: '05-methodologies', title: '개발 방법론', file: `${VCF}/05-개발-방법론.md` },
          { id: 'vcf-006-architecture-basics', slug: '06-architecture-basics', title: '아키텍처 기초', file: `${VCF}/06-아키텍처-기초.md` },
          { id: 'vcf-007-design-patterns', slug: '07-design-patterns', title: '설계 원칙과 디자인 패턴', file: `${VCF}/07-설계-원칙과-디자인패턴.md` },
          { id: 'vcf-008-databases', slug: '08-databases', title: '데이터베이스', file: `${VCF}/08-데이터베이스.md` },
          { id: 'vcf-009-api-web', slug: '09-api-web', title: 'API와 웹 통신', file: `${VCF}/09-API와-웹통신.md` },
          { id: 'vcf-010-testing-quality-security', slug: '10-testing-quality-security', title: '테스트 · 품질 · 보안', file: `${VCF}/10-테스트-품질-보안.md` },
          { id: 'vcf-011-deployment-devops', slug: '11-deployment-devops', title: '배포와 DevOps', file: `${VCF}/11-배포와-DevOps.md` },
          { id: 'vcf-012-ai-era', slug: '12-ai-era', title: 'AI 시대의 개발과 바이브 코딩', file: `${VCF}/12-AI시대의-개발과-바이브코딩.md` },
          { id: 'vcf-013-verification-testing', slug: '13-verification-testing', title: '검증과 테스트 (AI 결과 검증법)', file: `${VCF}/13-검증과-테스트.md` },
          { id: 'vcf-014-prompt-workbook', slug: '14-prompt-workbook', title: '프롬프트 워크북 (실습)', file: `${VCF}/14-프롬프트-워크북.md` },
          { id: 'vcf-015-security-basics', slug: '15-security-basics', title: '비개발자를 위한 보안 기초', file: `${VCF}/15-비개발자-보안-기초.md` },
          { id: 'vcf-016-software-lifecycle', slug: '16-software-lifecycle', title: '소프트웨어 생애주기', file: `${VCF}/16-소프트웨어-생애주기.md` },
          { id: 'vcf-017-planning-requirements', slug: '17-planning-requirements', title: '기획과 요구사항 정의', file: `${VCF}/17-기획과-요구사항-정의.md` },
          { id: 'vcf-018-design-implementation-management', slug: '18-design-implementation-management', title: '설계와 구현 관리', file: `${VCF}/18-설계와-구현-관리.md` },
          { id: 'vcf-019-testing-release-operations', slug: '19-testing-release-operations', title: '테스트 · 출시 · 운영', file: `${VCF}/19-테스트-출시-운영.md` },
        ],
      },
      {
        slug: 'stack',
        title: 'AI-DO 기술 스택',
        lessons: [
          { id: 'vcf-020-system-overview', slug: '20-system-overview', title: '시스템 조감도', file: `${VCF}/20-시스템-조감도.md` },
          { id: 'vcf-021-monorepo', slug: '21-monorepo', title: '모노레포 · Nx · pnpm', file: `${VCF}/21-모노레포-Nx-pnpm.md` },
          { id: 'vcf-022-typescript', slug: '22-typescript', title: 'TypeScript', file: `${VCF}/22-TypeScript.md` },
          { id: 'vcf-023-react-vite', slug: '23-react-vite', title: 'React 19 · Vite', file: `${VCF}/23-React19-Vite.md` },
          { id: 'vcf-024-ui-system', slug: '24-ui-system', title: 'UI 시스템 (Mantine · Radix · Tailwind)', file: `${VCF}/24-UI시스템-Mantine-Radix-Tailwind.md` },
          { id: 'vcf-025-routing-domains', slug: '25-routing-domains', title: '라우팅과 도메인 구조', file: `${VCF}/25-라우팅과-도메인구조.md` },
          { id: 'vcf-026-editor-collab', slug: '26-editor-collab', title: '에디터와 실시간 협업 (BlockNote · Yjs)', file: `${VCF}/26-에디터와-실시간협업-BlockNote-Yjs.md` },
          { id: 'vcf-027-ux-libraries', slug: '27-ux-libraries', title: 'UX 라이브러리들', file: `${VCF}/27-UX라이브러리들.md` },
          { id: 'vcf-028-fastapi', slug: '28-fastapi', title: 'FastAPI · Pydantic', file: `${VCF}/28-FastAPI-Pydantic.md` },
          { id: 'vcf-029-postgres', slug: '29-postgres', title: 'PostgreSQL · SQLAlchemy · Alembic', file: `${VCF}/29-PostgreSQL-SQLAlchemy-Alembic.md` },
          { id: 'vcf-030-celery-redis', slug: '30-celery-redis', title: 'Celery · Redis', file: `${VCF}/30-Celery-Redis.md` },
          { id: 'vcf-031-minio', slug: '31-minio', title: 'MinIO 객체 저장소', file: `${VCF}/31-MinIO-객체저장소.md` },
          { id: 'vcf-032-ai-layer', slug: '32-ai-layer', title: 'AI 레이어 (OpenAI · SSE · MCP)', file: `${VCF}/32-AI레이어-OpenAI-SSE-MCP.md` },
          { id: 'vcf-033-infra', slug: '33-infra', title: '인프라 (Docker · Nginx)', file: `${VCF}/33-인프라-Docker-Nginx.md` },
          { id: 'vcf-034-testing-tools', slug: '34-testing-tools', title: '테스트와 품질 도구', file: `${VCF}/34-테스트와-품질도구.md` },
          { id: 'vcf-035-vibe-coding-workflow', slug: '35-vibe-coding-workflow', title: '바이브 코딩 실전 워크플로', file: `${VCF}/35-바이브코딩-실전워크플로.md` },
        ],
      },
      {
        slug: 'appendix',
        title: '부록',
        lessons: [
          { id: 'vcf-appendix-a-glossary', slug: 'appendix-a-glossary', title: '부록 A — 용어 사전', file: `${VCF}/A-용어사전.md` },
        ],
      },
    ],
  },
  {
    slug: DSB,
    title: '데이터베이스 입문 — 저장소를 고르는 법',
    description:
      'SQL, NoSQL, 캐시, 검색, 벡터 DB, 객체 저장소까지 초보자 눈높이로 비교하며 처음 서비스의 저장소 선택 기준을 익힙니다.',
    parts: [
      {
        slug: 'intro',
        title: '시작하기',
        lessons: [
          { id: 'dsb-000-index', slug: '00-index', title: '목차', file: `${DSB}/00-index.md` },
        ],
      },
      {
        slug: 'storage-types',
        title: '저장소 종류 이해',
        lessons: [
          { id: 'dsb-001-why-database', slug: '01-why-database', title: '데이터베이스가 필요한 이유', file: `${DSB}/01-데이터베이스가-필요한-이유.md` },
          { id: 'dsb-002-relational-sql', slug: '02-relational-sql', title: '관계형 DB와 SQL', file: `${DSB}/02-관계형-DB와-SQL.md` },
          { id: 'dsb-003-document-nosql', slug: '03-document-nosql', title: 'Document DB와 NoSQL', file: `${DSB}/03-Document-DB와-NoSQL.md` },
          { id: 'dsb-004-key-value-cache', slug: '04-key-value-cache', title: 'Key-Value와 캐시', file: `${DSB}/04-Key-Value와-캐시.md` },
          { id: 'dsb-005-column-analytics', slug: '05-column-analytics', title: 'Wide-column, columnar, 분석용 저장소', file: `${DSB}/05-Wide-column-columnar-분석용-저장소.md` },
          { id: 'dsb-006-graph-time-series', slug: '06-graph-time-series', title: 'Graph DB와 Time-series DB', file: `${DSB}/06-Graph-DB와-Time-series-DB.md` },
          { id: 'dsb-007-distributed-cloud', slug: '07-distributed-cloud', title: 'Distributed DB와 클라우드 DB', file: `${DSB}/07-Distributed-DB와-클라우드-DB.md` },
          { id: 'dsb-008-search-vector-object', slug: '08-search-vector-object', title: 'Search DB, Vector DB, Object Storage', file: `${DSB}/08-Search-Vector-Object-Storage.md` },
        ],
      },
      {
        slug: 'decision',
        title: '선택 기준',
        lessons: [
          { id: 'dsb-009-selection-checklist', slug: '09-selection-checklist', title: '처음 서비스에서 DB를 고르는 체크리스트', file: `${DSB}/09-처음-서비스에서-DB를-고르는-체크리스트.md` },
        ],
      },
    ],
  },
  {
    slug: SLJ,
    title: '아이디어에서 출시까지 — 서비스 개발 여정',
    description:
      '한 사람이 서비스 하나를 처음 떠올린 순간부터 출시·운영·수익화까지 따라가는 실전 여정. ' +
      '각 단계의 결정이 다음 단계에 어떻게 이어지는지를 28편의 레슨에 담았습니다.',
    parts: [
      {
        slug: 'intro',
        title: '시작하기',
        lessons: [
          { id: 'slj-001-orientation', slug: '01-orientation', title: '코스 안내 — 왜 "여정"인가', file: `${SLJ}/01-코스안내.md` },
          { id: 'slj-002-overview', slug: '02-overview', title: '서비스 개발 한눈에 보기', file: `${SLJ}/02-서비스개발-한눈에보기.md` },
        ],
      },
      {
        slug: 'planning',
        title: '만들 것을 정한다 — 기획',
        lessons: [
          { id: 'slj-003-idea', slug: '03-idea', title: '아이디어를 잡는 법', file: `${SLJ}/03-아이디어를-잡는-법.md` },
          { id: 'slj-004-market-research', slug: '04-market-research', title: '시장 관찰과 경쟁 분석', file: `${SLJ}/04-시장관찰과-경쟁분석.md` },
          { id: 'slj-005-mvp', slug: '05-mvp', title: 'MVP의 진짜 의미', file: `${SLJ}/05-MVP의-진짜의미.md` },
          { id: 'slj-006-persona', slug: '06-persona', title: '페르소나와 타겟 — 좁힐수록 강해진다', file: `${SLJ}/06-페르소나와-타겟.md` },
          { id: 'slj-007-core-features', slug: '07-core-features', title: '핵심 기능 도출 & 차별화 전략', file: `${SLJ}/07-핵심기능-차별화전략.md` },
        ],
      },
      {
        slug: 'design',
        title: '그림을 그린다 — 설계',
        lessons: [
          { id: 'slj-008-wireframe', slug: '08-wireframe', title: '화면 설계와 와이어프레임', file: `${SLJ}/08-화면설계와-와이어프레임.md` },
          { id: 'slj-009-ux-scenario', slug: '09-ux-scenario', title: 'UX·사용자 시나리오', file: `${SLJ}/09-UX-사용자시나리오.md` },
          { id: 'slj-010-data-design', slug: '10-data-design', title: '데이터 설계 (테이블·ERD)', file: `${SLJ}/10-데이터설계-ERD.md` },
          { id: 'slj-011-api-design', slug: '11-api-design', title: 'API 설계 — 프론트와 백을 잇는 계약', file: `${SLJ}/11-API설계.md` },
          { id: 'slj-012-design-system', slug: '12-design-system', title: '디자인 시스템과 비주얼 설계', file: `${SLJ}/12-디자인시스템.md` },
        ],
      },
      {
        slug: 'development',
        title: '코드를 짠다 — 개발 & 연동',
        lessons: [
          { id: 'slj-013-frontend', slug: '13-frontend', title: '프론트엔드 개발 한 바닥', file: `${SLJ}/13-프론트엔드-개발.md` },
          { id: 'slj-014-backend', slug: '14-backend', title: '백엔드 API 개발 — CRUD부터 로직까지', file: `${SLJ}/14-백엔드-API개발.md` },
          { id: 'slj-015-database', slug: '15-database', title: '데이터베이스 구축과 운영', file: `${SLJ}/15-데이터베이스-구축.md` },
          { id: 'slj-016-integration', slug: '16-integration', title: '프론트-백 연동의 실제', file: `${SLJ}/16-프론트백-연동.md` },
          { id: 'slj-017-auth', slug: '17-auth', title: '회원가입·로그인·소셜 인증', file: `${SLJ}/17-인증.md` },
          { id: 'slj-018-mobile', slug: '18-mobile', title: '모바일 대응 (반응형·네이티브)', file: `${SLJ}/18-모바일-대응.md` },
        ],
      },
      {
        slug: 'testing',
        title: '검증한다 — 테스트',
        lessons: [
          { id: 'slj-019-unit-integration', slug: '19-unit-integration', title: '단위·통합 테스트', file: `${SLJ}/19-단위-통합테스트.md` },
          { id: 'slj-020-perf-security', slug: '20-perf-security', title: '성능·보안·시나리오 테스트', file: `${SLJ}/20-성능-보안테스트.md` },
        ],
      },
      {
        slug: 'deploy',
        title: '세상에 내보낸다 — 빌드·배포·출시',
        lessons: [
          { id: 'slj-021-build', slug: '21-build', title: '빌드와 산출물 관리', file: `${SLJ}/21-빌드와-산출물.md` },
          { id: 'slj-022-git-branch', slug: '22-git-branch', title: 'Git 브랜치 전략 — 개발/운영 분리', file: `${SLJ}/22-Git-브랜치전략.md` },
          { id: 'slj-023-deploy-infra', slug: '23-deploy-infra', title: '배포 인프라 — 클라우드 vs Vercel/CF', file: `${SLJ}/23-배포-인프라.md` },
          { id: 'slj-024-domain-https', slug: '24-domain-https', title: '도메인·HTTPS·SSL 설정', file: `${SLJ}/24-도메인-HTTPS.md` },
          { id: 'slj-025-app-store', slug: '25-app-store', title: '앱스토어·구글플레이 등록과 심사', file: `${SLJ}/25-앱스토어-등록.md` },
        ],
      },
      {
        slug: 'operate',
        title: '살아 움직이게 한다 — 운영·수익화',
        lessons: [
          { id: 'slj-026-operate', slug: '26-operate', title: '운영·유지보수 — 출시는 시작', file: `${SLJ}/26-운영-유지보수.md` },
          { id: 'slj-027-monitoring', slug: '27-monitoring', title: '장애 대응과 모니터링', file: `${SLJ}/27-장애대응-모니터링.md` },
          { id: 'slj-028-monetization', slug: '28-monetization', title: '수익화는 기획부터', file: `${SLJ}/28-수익화.md` },
        ],
      },
    ],
  },
];

export function findCourse(slug: string): LearningCourse | null {
  return LEARNING_COURSES.find((course) => course.slug === slug) ?? null;
}

/** Flatten every part's lessons, preserving part declaration order.
 *  This is the canonical reading sequence — prev/next navigation and the
 *  "레슨 N / total" counter both operate on this flat view. */
export function getAllLessons(course: LearningCourse): LearningLesson[] {
  return course.parts.flatMap((part) => part.lessons);
}

export function findLesson(
  course: LearningCourse,
  lessonSlug: string,
): { lesson: LearningLesson; index: number } | null {
  const all = getAllLessons(course);
  const index = all.findIndex((lesson) => lesson.slug === lessonSlug);
  if (index < 0) return null;
  return { lesson: all[index], index };
}
