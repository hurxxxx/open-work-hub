export interface LearningLesson {
  /** ASCII URL slug — used in `/learning/<course>/<lesson>` path. */
  slug: string;
  /** Display title shown in the sidebar and breadcrumb. */
  title: string;
  /** Filename inside the repo-root `learning/` directory. Matches
   *  import.meta.glob output from `content.ts`. */
  file: string;
  /** Optional one-liner for listing views. */
  summary?: string;
}

export interface LearningCourse {
  slug: string;
  title: string;
  description: string;
  lessons: LearningLesson[];
}

export const LEARNING_COURSES: LearningCourse[] = [
  {
    slug: 'vibe-coding-foundations',
    title: '바이브 코딩 입문',
    description:
      '소프트웨어·프로그래밍 기본 개념부터 AIDOO 스택, 실전 바이브 코딩 워크플로까지. 전 구성원 공용 온보딩 트랙입니다.',
    lessons: [
      { slug: '00-index', title: '목차', file: '00-index.md' },
      { slug: '01-orientation', title: '오리엔테이션', file: '01-오리엔테이션.md' },
      { slug: '02-software-basics', title: '소프트웨어란 무엇인가', file: '02-소프트웨어란-무엇인가.md' },
      { slug: '03-programming-languages', title: '프로그래밍 언어와 런타임', file: '03-프로그래밍-언어와-런타임.md' },
      { slug: '04-git', title: '버전관리 · Git', file: '04-버전관리-Git.md' },
      { slug: '05-methodologies', title: '개발 방법론', file: '05-개발-방법론.md' },
      { slug: '06-architecture-basics', title: '아키텍처 기초', file: '06-아키텍처-기초.md' },
      { slug: '07-design-patterns', title: '설계 원칙과 디자인 패턴', file: '07-설계-원칙과-디자인패턴.md' },
      { slug: '08-databases', title: '데이터베이스', file: '08-데이터베이스.md' },
      { slug: '09-api-web', title: 'API와 웹 통신', file: '09-API와-웹통신.md' },
      { slug: '10-testing-quality-security', title: '테스트 · 품질 · 보안', file: '10-테스트-품질-보안.md' },
      { slug: '11-deployment-devops', title: '배포와 DevOps', file: '11-배포와-DevOps.md' },
      { slug: '12-ai-era', title: 'AI 시대의 개발과 바이브 코딩', file: '12-AI시대의-개발과-바이브코딩.md' },
      { slug: '20-system-overview', title: '시스템 조감도', file: '20-시스템-조감도.md' },
      { slug: '21-monorepo', title: '모노레포 · Nx · pnpm', file: '21-모노레포-Nx-pnpm.md' },
      { slug: '22-typescript', title: 'TypeScript', file: '22-TypeScript.md' },
      { slug: '23-react-vite', title: 'React 19 · Vite', file: '23-React19-Vite.md' },
      { slug: '24-ui-system', title: 'UI 시스템 (Mantine · Radix · Tailwind)', file: '24-UI시스템-Mantine-Radix-Tailwind.md' },
      { slug: '25-routing-domains', title: '라우팅과 도메인 구조', file: '25-라우팅과-도메인구조.md' },
      { slug: '26-editor-collab', title: '에디터와 실시간 협업 (BlockNote · Yjs)', file: '26-에디터와-실시간협업-BlockNote-Yjs.md' },
      { slug: '27-ux-libraries', title: 'UX 라이브러리들', file: '27-UX라이브러리들.md' },
      { slug: '28-fastapi', title: 'FastAPI · Pydantic', file: '28-FastAPI-Pydantic.md' },
      { slug: '29-postgres', title: 'PostgreSQL · SQLAlchemy · Alembic', file: '29-PostgreSQL-SQLAlchemy-Alembic.md' },
      { slug: '30-celery-redis', title: 'Celery · Redis', file: '30-Celery-Redis.md' },
      { slug: '31-minio', title: 'MinIO 객체 저장소', file: '31-MinIO-객체저장소.md' },
      { slug: '32-ai-layer', title: 'AI 레이어 (OpenAI · SSE · MCP)', file: '32-AI레이어-OpenAI-SSE-MCP.md' },
      { slug: '33-infra', title: '인프라 (Docker · Nginx)', file: '33-인프라-Docker-Nginx.md' },
      { slug: '34-testing-tools', title: '테스트와 품질 도구', file: '34-테스트와-품질도구.md' },
      { slug: '35-vibe-coding-workflow', title: '바이브 코딩 실전 워크플로', file: '35-바이브코딩-실전워크플로.md' },
      { slug: 'appendix-a-glossary', title: '부록 A — 용어 사전', file: 'A-용어사전.md' },
    ],
  },
];

export function findCourse(slug: string): LearningCourse | null {
  return LEARNING_COURSES.find((course) => course.slug === slug) ?? null;
}

export function findLesson(
  course: LearningCourse,
  lessonSlug: string,
): { lesson: LearningLesson; index: number } | null {
  const index = course.lessons.findIndex((lesson) => lesson.slug === lessonSlug);
  if (index < 0) return null;
  return { lesson: course.lessons[index], index };
}
