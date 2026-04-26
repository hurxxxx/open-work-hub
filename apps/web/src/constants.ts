import { 
  Search, 
  FileText, 
  Languages, 
  FileSearch, 
  AlertTriangle, 
  Mic, 
  Mail, 
  Presentation, 
  HelpCircle, 
  User,
  Share2,
  Lock,
  History,
  Files,
  Plus,
  Newspaper, 
  BarChart3, 
  Gavel, 
  FilePlus, 
  FileBarChart, 
  Database, 
  LayoutDashboard, 
  Utensils, 
  MessageSquare, 
  Settings, 
  Activity, 
  Home,
  Inbox,
  Layout,
  Brain,
  CheckCircle2,
  Calendar,
  FolderKanban,
  Users,
  List as ListIcon,
  Video,
  GraduationCap,
} from 'lucide-react';

export interface NavItem {
  id: string;
  title: string;
  icon: any;
  description?: string;
  category: string;
  /** SubSidebar 필터링 기준 — 어느 AppBar 의 sub 항목인지 */
  appId: 'home' | 'ai' | 'pms' | 'docs' | 'planner' | 'meeting' | 'learning' | 'settings';
  /**
   * URL 빌드 시 실제 타겟 workspace app. 미지정 시 appId 사용.
   * `meeting-minutes` 처럼 AI sidebar 에 있지만 meeting 앱으로 딥링크하는 케이스에 사용.
   */
  linkAppId?: 'ai' | 'pms' | 'docs' | 'planner' | 'meeting' | 'learning';
  /** workspace app path 뒤에 붙는 query/hash suffix (예: `?tab=recordings`) */
  pathSuffix?: string;
  /** workspace-aware 가 아닌 절대 경로 (admin/settings 등) */
  absolutePath?: string;
  /**
   * legacy_ai_portal_prototype에서 포팅 대기 중인 도구는 true.
   * 사이드바에서 (준비중) 배지로 표시되고 클릭 시 ComingSoonView로 라우팅된다.
   */
  comingSoon?: boolean;
}

export interface AppBarItem {
  id: 'home' | 'ai' | 'pms' | 'docs' | 'planner' | 'meeting' | 'learning' | 'settings';
  title: string;
  icon: any;
}

export const APP_BAR_ITEMS: AppBarItem[] = [
  { id: 'home', title: 'HOME', icon: Home },
  { id: 'ai', title: 'AI', icon: Brain },
  { id: 'pms', title: 'PMS', icon: FolderKanban },
  { id: 'docs', title: 'DOCS', icon: Files },
  { id: 'planner', title: 'Planner', icon: Calendar },
  { id: 'meeting', title: 'MEETING', icon: Users },
  { id: 'learning', title: '학습', icon: GraduationCap },
  { id: 'settings', title: 'Settings', icon: Settings },
];

export const NAV_ITEMS: NavItem[] = [
  // AI - Core Tools
  { id: 'chatbot', title: 'AI 챗봇', icon: MessageSquare, category: 'Core Tools', appId: 'ai', description: '사내 데이터와 도구를 활용하는 대화형 어시스턴트' },
  { id: 'search', title: '아이두 통합검색', icon: Search, category: 'Core Tools', appId: 'ai', description: '사내 문서를 근거 기반으로 찾는 메인 검색 허브' },
  { id: 'drafting', title: '기안작성 도우미', icon: FileText, category: 'Core Tools', appId: 'ai', description: '공문, 협조전, 구매 요청 같은 업무 기안 초안 작성', comingSoon: true },
  { id: 'translate', title: '문서 번역/요약', icon: Languages, category: 'Core Tools', appId: 'ai', description: '업로드 문서의 OCR, 번역, 요약 작업', comingSoon: true },
  { id: 'spec-compare', title: '규격서 비교', icon: FileSearch, category: 'Core Tools', appId: 'ai', description: '규격 문서 두 버전의 변경점 비교', comingSoon: true },
  { id: 'fmea-compare', title: 'FMEA 비교', icon: AlertTriangle, category: 'Core Tools', appId: 'ai', description: 'FMEA 리스크 항목과 조치안 비교', comingSoon: true },

  // AI - Assistants
  { id: 'meeting-minutes', title: '회의록', icon: Mic, category: 'Assistants', appId: 'ai', linkAppId: 'meeting', pathSuffix: '?tab=recordings', description: '음성 파일 STT, 화자 분리, 회의록 요약' },
  { id: 'email-assistant', title: '메일 작성 도우미', icon: Mail, category: 'Assistants', appId: 'ai', description: '업무 메일 초안 생성', comingSoon: true },
  { id: 'ppt-assistant', title: 'PPT 발표 도우미', icon: Presentation, category: 'Assistants', appId: 'ai', description: '발표 스크립트와 예상 질문 정리', comingSoon: true },
  { id: 'qa-assistant', title: '사내 관리팀 Q&A', icon: HelpCircle, category: 'Assistants', appId: 'ai', description: '내부 운영 문서와 FAQ 검색', comingSoon: true },
  { id: 'news', title: '뉴스', icon: Newspaper, category: 'Assistants', appId: 'ai', description: '산업/공조 관련 외부 뉴스 모니터링', comingSoon: true },
  { id: 'industry-report', title: '산업 리포트', icon: BarChart3, category: 'Assistants', appId: 'ai', description: '외부 산업 리포트와 동향 요약', comingSoon: true },

  // AI - Patent
  { id: 'patent-interpret', title: '특허 해석 도우미', icon: Gavel, category: 'Patent', appId: 'ai', description: '특허 문헌 해석 지원', comingSoon: true },
  { id: 'patent-apply', title: '특허 출원 도우미', icon: FilePlus, category: 'Patent', appId: 'ai', description: '특허 출원 초안 보조', comingSoon: true },
  { id: 'patent-report', title: 'AI 특허 보고서', icon: FileBarChart, category: 'Patent', appId: 'ai', description: '특허 분석 결과를 보고서 형태로 정리', comingSoon: true },

  // PMS
  { id: 'pms-inbox', title: 'Inbox', icon: Inbox, category: 'Personal', appId: 'pms' },
  { id: 'pms-tasks', title: 'My Tasks', icon: CheckCircle2, category: 'Personal', appId: 'pms', pathSuffix: '/assigned' },
  { id: 'pms-tasks-assigned', title: 'Assigned to me', icon: User, category: 'Personal', appId: 'pms', pathSuffix: '/assigned' },
  { id: 'pms-tasks-today', title: 'Today & Overdue', icon: Calendar, category: 'Personal', appId: 'pms', pathSuffix: '/today' },
  { id: 'pms-tasks-personal', title: 'Personal List', icon: ListIcon, category: 'Personal', appId: 'pms', pathSuffix: '/personal' },

  // DOCS
  { id: 'docs-all', title: 'All Docs', icon: Files, category: 'Library', appId: 'docs' },
  { id: 'docs-my', title: 'My Docs', icon: User, category: 'Library', appId: 'docs' },
  { id: 'docs-shared', title: 'Shared with me', icon: Share2, category: 'Library', appId: 'docs' },
  { id: 'docs-private', title: 'Private', icon: Lock, category: 'Library', appId: 'docs' },
  { id: 'docs-notes', title: 'Meeting Notes', icon: Mic, category: 'Library', appId: 'docs' },
  { id: 'docs-recent', title: 'Recent Pages', icon: History, category: 'Library', appId: 'docs' },
  { id: 'docs-archived', title: 'Archived', icon: History, category: 'Library', appId: 'docs' },

  // Planner
  { id: 'planner-calendar', title: '캘린더', icon: Calendar, category: 'Schedule', appId: 'planner' },
  { id: 'planner-timeline', title: '타임라인', icon: Activity, category: 'Schedule', appId: 'planner' },

  // Meeting
  { id: 'meeting-upcoming', title: 'Upcoming', icon: Calendar, category: 'Meetings', appId: 'meeting' },
  { id: 'meeting-mine', title: 'My Meetings', icon: User, category: 'Meetings', appId: 'meeting', pathSuffix: '?scope=mine' },
  { id: 'meeting-recordings', title: 'Recordings', icon: Video, category: 'Meetings', appId: 'meeting', pathSuffix: '?tab=recordings' },

  // Learning — one top-level entry. The in-course table of contents is a
  // floating popover attached to the lesson header (see LearningCourseView),
  // so the sub-sidebar stays minimal and the reading area is not crowded.
  { id: 'learning-home', title: '전체 학습 홈', icon: GraduationCap, category: 'Courses', appId: 'learning', description: '모든 구성원이 열람할 수 있는 교육 콘텐츠 모음' },

  // Settings
  { id: 'settings-general', title: 'General', icon: Settings, category: 'Admin', appId: 'settings', absolutePath: '/admin/general' },
  { id: 'settings-people', title: 'People', icon: User, category: 'Admin', appId: 'settings', absolutePath: '/admin/people' },
  { id: 'settings-workspaces', title: 'Workspaces', icon: Database, category: 'Admin', appId: 'settings', absolutePath: '/admin/workspaces' },
  { id: 'settings-security', title: 'Permissions', icon: Lock, category: 'Security', appId: 'settings', absolutePath: '/admin/security' },
  { id: 'settings-audit', title: 'Audit Logs', icon: Activity, category: 'Security', appId: 'settings', absolutePath: '/admin/audit' },
];
