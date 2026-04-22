export interface LearningLesson {
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
          { slug: '00-index', title: '목차', file: `${VCF}/00-index.md` },
        ],
      },
      {
        slug: 'foundations',
        title: '소프트웨어 공학 기초',
        lessons: [
          { slug: '01-orientation', title: '오리엔테이션', file: `${VCF}/01-오리엔테이션.md` },
          { slug: '02-software-basics', title: '소프트웨어란 무엇인가', file: `${VCF}/02-소프트웨어란-무엇인가.md` },
          { slug: '03-programming-languages', title: '프로그래밍 언어와 런타임', file: `${VCF}/03-프로그래밍-언어와-런타임.md` },
          { slug: '04-git', title: '버전관리 · Git', file: `${VCF}/04-버전관리-Git.md` },
          { slug: '05-methodologies', title: '개발 방법론', file: `${VCF}/05-개발-방법론.md` },
          { slug: '06-architecture-basics', title: '아키텍처 기초', file: `${VCF}/06-아키텍처-기초.md` },
          { slug: '07-design-patterns', title: '설계 원칙과 디자인 패턴', file: `${VCF}/07-설계-원칙과-디자인패턴.md` },
          { slug: '08-databases', title: '데이터베이스', file: `${VCF}/08-데이터베이스.md` },
          { slug: '09-api-web', title: 'API와 웹 통신', file: `${VCF}/09-API와-웹통신.md` },
          { slug: '10-testing-quality-security', title: '테스트 · 품질 · 보안', file: `${VCF}/10-테스트-품질-보안.md` },
          { slug: '11-deployment-devops', title: '배포와 DevOps', file: `${VCF}/11-배포와-DevOps.md` },
          { slug: '12-ai-era', title: 'AI 시대의 개발과 바이브 코딩', file: `${VCF}/12-AI시대의-개발과-바이브코딩.md` },
          { slug: '13-verification-testing', title: '검증과 테스트 (AI 결과 검증법)', file: `${VCF}/13-검증과-테스트.md` },
          { slug: '14-prompt-workbook', title: '프롬프트 워크북 (실습)', file: `${VCF}/14-프롬프트-워크북.md` },
          { slug: '15-security-basics', title: '비개발자를 위한 보안 기초', file: `${VCF}/15-비개발자-보안-기초.md` },
        ],
      },
      {
        slug: 'stack',
        title: 'AIDOO 기술 스택',
        lessons: [
          { slug: '20-system-overview', title: '시스템 조감도', file: `${VCF}/20-시스템-조감도.md` },
          { slug: '21-monorepo', title: '모노레포 · Nx · pnpm', file: `${VCF}/21-모노레포-Nx-pnpm.md` },
          { slug: '22-typescript', title: 'TypeScript', file: `${VCF}/22-TypeScript.md` },
          { slug: '23-react-vite', title: 'React 19 · Vite', file: `${VCF}/23-React19-Vite.md` },
          { slug: '24-ui-system', title: 'UI 시스템 (Mantine · Radix · Tailwind)', file: `${VCF}/24-UI시스템-Mantine-Radix-Tailwind.md` },
          { slug: '25-routing-domains', title: '라우팅과 도메인 구조', file: `${VCF}/25-라우팅과-도메인구조.md` },
          { slug: '26-editor-collab', title: '에디터와 실시간 협업 (BlockNote · Yjs)', file: `${VCF}/26-에디터와-실시간협업-BlockNote-Yjs.md` },
          { slug: '27-ux-libraries', title: 'UX 라이브러리들', file: `${VCF}/27-UX라이브러리들.md` },
          { slug: '28-fastapi', title: 'FastAPI · Pydantic', file: `${VCF}/28-FastAPI-Pydantic.md` },
          { slug: '29-postgres', title: 'PostgreSQL · SQLAlchemy · Alembic', file: `${VCF}/29-PostgreSQL-SQLAlchemy-Alembic.md` },
          { slug: '30-celery-redis', title: 'Celery · Redis', file: `${VCF}/30-Celery-Redis.md` },
          { slug: '31-minio', title: 'MinIO 객체 저장소', file: `${VCF}/31-MinIO-객체저장소.md` },
          { slug: '32-ai-layer', title: 'AI 레이어 (OpenAI · SSE · MCP)', file: `${VCF}/32-AI레이어-OpenAI-SSE-MCP.md` },
          { slug: '33-infra', title: '인프라 (Docker · Nginx)', file: `${VCF}/33-인프라-Docker-Nginx.md` },
          { slug: '34-testing-tools', title: '테스트와 품질 도구', file: `${VCF}/34-테스트와-품질도구.md` },
          { slug: '35-vibe-coding-workflow', title: '바이브 코딩 실전 워크플로', file: `${VCF}/35-바이브코딩-실전워크플로.md` },
        ],
      },
      {
        slug: 'appendix',
        title: '부록',
        lessons: [
          { slug: 'appendix-a-glossary', title: '부록 A — 용어 사전', file: `${VCF}/A-용어사전.md` },
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
