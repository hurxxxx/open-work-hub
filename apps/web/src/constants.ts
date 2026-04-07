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
  List as ListIcon,
} from 'lucide-react';

export interface NavItem {
  id: string;
  title: string;
  icon: any;
  description?: string;
  category: string;
  appId: 'home' | 'ai' | 'pms' | 'docs' | 'planner' | 'settings';
  path?: string;
}

export interface AppBarItem {
  id: 'home' | 'ai' | 'pms' | 'docs' | 'planner' | 'settings';
  title: string;
  icon: any;
  path: string;
}

export const APP_BAR_ITEMS: AppBarItem[] = [
  { id: 'home', title: 'HOME', icon: Home, path: '/' },
  { id: 'ai', title: 'AI', icon: Brain, path: '/ai' },
  { id: 'pms', title: 'PMS', icon: FolderKanban, path: '/pms' },
  { id: 'docs', title: 'DOCS', icon: Files, path: '/docs' },
  { id: 'planner', title: 'Planner', icon: Calendar, path: '/planner' },
  { id: 'settings', title: 'Settings', icon: Settings, path: '/admin/people' },
];

export const NAV_ITEMS: NavItem[] = [
  // AI - Core Tools
  { id: 'search', title: '아이두 통합검색', icon: Search, category: 'Core Tools', appId: 'ai', description: '사내 문서를 근거 기반으로 찾는 메인 검색 허브' },
  { id: 'drafting', title: '기안작성 도우미', icon: FileText, category: 'Core Tools', appId: 'ai', description: '공문, 협조전, 구매 요청 같은 업무 기안 초안 작성' },
  { id: 'translate', title: '문서 번역/요약', icon: Languages, category: 'Core Tools', appId: 'ai', description: '업로드 문서의 OCR, 번역, 요약 작업' },
  { id: 'spec-compare', title: '규격서 비교', icon: FileSearch, category: 'Core Tools', appId: 'ai', description: '규격 문서 두 버전의 변경점 비교' },
  { id: 'fmea-compare', title: 'FMEA 비교', icon: AlertTriangle, category: 'Core Tools', appId: 'ai', description: 'FMEA 리스크 항목과 조치안 비교' },

  // AI - Assistants
  { id: 'meeting-minutes', title: '회의록', icon: Mic, category: 'Assistants', appId: 'ai', description: '음성 파일 STT, 화자 분리, 회의록 요약' },
  { id: 'email-assistant', title: '메일 작성 도우미', icon: Mail, category: 'Assistants', appId: 'ai', description: '업무 메일 초안 생성' },
  { id: 'ppt-assistant', title: 'PPT 발표 도우미', icon: Presentation, category: 'Assistants', appId: 'ai', description: '발표 스크립트와 예상 질문 정리' },
  { id: 'qa-assistant', title: '사내 관리팀 Q&A', icon: HelpCircle, category: 'Assistants', appId: 'ai', description: '내부 운영 문서와 FAQ 검색' },
  { id: 'news', title: '뉴스', icon: Newspaper, category: 'Assistants', appId: 'ai', description: '산업/공조 관련 외부 뉴스 모니터링' },
  { id: 'industry-report', title: '산업 리포트', icon: BarChart3, category: 'Assistants', appId: 'ai', description: '외부 산업 리포트와 동향 요약' },

  // AI - Patent
  { id: 'patent-interpret', title: '특허 해석 도우미', icon: Gavel, category: 'Patent', appId: 'ai', description: '특허 문헌 해석 지원' },
  { id: 'patent-apply', title: '특허 출원 도우미', icon: FilePlus, category: 'Patent', appId: 'ai', description: '특허 출원 초안 보조' },
  { id: 'patent-report', title: 'AI 특허 보고서', icon: FileBarChart, category: 'Patent', appId: 'ai', description: '특허 분석 결과를 보고서 형태로 정리' },

  // PMS
  { id: 'pms-home', title: 'Home', icon: Home, category: 'Personal', appId: 'pms' },
  { id: 'pms-inbox', title: 'Inbox', icon: Inbox, category: 'Personal', appId: 'pms' },
  { id: 'pms-tasks', title: 'My Tasks', icon: CheckCircle2, category: 'Personal', appId: 'pms' },
  { id: 'pms-tasks-assigned', title: 'Assigned to me', icon: User, category: 'Personal', appId: 'pms' },
  { id: 'pms-tasks-today', title: 'Today & Overdue', icon: Calendar, category: 'Personal', appId: 'pms' },
  { id: 'pms-tasks-personal', title: 'Personal List', icon: ListIcon, category: 'Personal', appId: 'pms' },
  { id: 'pms-space-team', title: 'Team Space', icon: Layout, category: 'Spaces', appId: 'pms' },
  { id: 'pms-space-project1', title: 'Project 1', icon: FolderKanban, category: 'Spaces', appId: 'pms' },
  { id: 'pms-space-project2', title: 'Project 2', icon: FolderKanban, category: 'Spaces', appId: 'pms' },

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

  // Settings
  { id: 'settings-general', title: 'General', icon: Settings, category: 'Admin', appId: 'settings', path: '/admin/general' },
  { id: 'settings-people', title: 'People', icon: User, category: 'Admin', appId: 'settings', path: '/admin/people' },
  { id: 'settings-teams', title: 'Teams', icon: Layout, category: 'Admin', appId: 'settings', path: '/admin/teams' },
  { id: 'settings-workspaces', title: 'Workspaces', icon: Database, category: 'Admin', appId: 'settings', path: '/admin/workspaces' },
  { id: 'settings-security', title: 'Security & Permissions', icon: Lock, category: 'Security & Permissions', appId: 'settings', path: '/admin/security' },
  { id: 'settings-audit', title: 'Audit Logs', icon: Activity, category: 'Security & Permissions', appId: 'settings', path: '/admin/audit' },
];
