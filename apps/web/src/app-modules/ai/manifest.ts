import {
  AlertTriangle,
  BarChart3,
  Brain,
  FileBarChart,
  FilePlus,
  FileSearch,
  FileText,
  Gavel,
  HelpCircle,
  Languages,
  Mail,
  MessageSquare,
  Mic,
  Newspaper,
  Presentation,
  Search,
} from 'lucide-react';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const aiManifest: AppModuleManifest = {
  appBarItem: { id: 'ai', title: 'AI', icon: Brain },
  defaultActiveNavItemId: 'chatbot',
  navItems: [
    { id: 'chatbot', title: 'AI 챗봇', icon: MessageSquare, category: 'Core Tools', appId: 'ai', description: '사내 데이터와 도구를 활용하는 대화형 어시스턴트' },
    { id: 'search', title: '아이두 통합검색', icon: Search, category: 'Core Tools', appId: 'ai', description: '사내 문서를 근거 기반으로 찾는 메인 검색 허브' },
    { id: 'drafting', title: '기안작성 도우미', icon: FileText, category: 'Core Tools', appId: 'ai', description: '공문, 협조전, 구매 요청 같은 업무 기안 초안 작성', comingSoon: true },
    { id: 'translate', title: '문서 번역/요약', icon: Languages, category: 'Core Tools', appId: 'ai', description: '업로드 문서의 OCR, 번역, 요약 작업', comingSoon: true },
    { id: 'spec-compare', title: '규격서 비교', icon: FileSearch, category: 'Core Tools', appId: 'ai', description: '규격 문서 두 버전의 변경점 비교', comingSoon: true },
    { id: 'fmea-compare', title: 'FMEA 비교', icon: AlertTriangle, category: 'Core Tools', appId: 'ai', description: 'FMEA 리스크 항목과 조치안 비교', comingSoon: true },
    { id: 'meeting-minutes', title: '회의록', icon: Mic, category: 'Assistants', appId: 'ai', linkAppId: 'meeting', pathSuffix: '?tab=recordings', description: '음성 파일 STT, 화자 분리, 회의록 요약' },
    { id: 'email-assistant', title: '메일 작성 도우미', icon: Mail, category: 'Assistants', appId: 'ai', description: '업무 메일 초안 생성', comingSoon: true },
    { id: 'ppt-assistant', title: 'PPT 발표 도우미', icon: Presentation, category: 'Assistants', appId: 'ai', description: '발표 스크립트와 예상 질문 정리', comingSoon: true },
    { id: 'qa-assistant', title: '사내 관리팀 Q&A', icon: HelpCircle, category: 'Assistants', appId: 'ai', description: '내부 운영 문서와 FAQ 검색', comingSoon: true },
    { id: 'news', title: '뉴스', icon: Newspaper, category: 'Assistants', appId: 'ai', description: '산업/공조 관련 외부 뉴스 모니터링', comingSoon: true },
    { id: 'industry-report', title: '산업 리포트', icon: BarChart3, category: 'Assistants', appId: 'ai', description: '외부 산업 리포트와 동향 요약', comingSoon: true },
    { id: 'patent-interpret', title: '특허 해석 도우미', icon: Gavel, category: 'Patent', appId: 'ai', description: '특허 문헌 해석 지원', comingSoon: true },
    { id: 'patent-apply', title: '특허 출원 도우미', icon: FilePlus, category: 'Patent', appId: 'ai', description: '특허 출원 초안 보조', comingSoon: true },
    { id: 'patent-report', title: 'AI 특허 보고서', icon: FileBarChart, category: 'Patent', appId: 'ai', description: '특허 분석 결과를 보고서 형태로 정리', comingSoon: true },
  ],
  workspaceRoutePaths: ['/w/:workspaceSlug/ai'],
};
