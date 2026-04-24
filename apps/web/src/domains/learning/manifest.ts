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

export const LEARNING_COURSES: LearningCourse[] = [
  {
    slug: VCF,
    title: '바이브 코딩 입문',
    description:
      '소프트웨어·프로그래밍 기본 개념부터 AIDOO 스택, 실전 바이브 코딩 워크플로까지. 전 구성원 공용 온보딩 트랙입니다.',
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
        title: 'AIDOO 기술 스택',
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
