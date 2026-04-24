import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertTriangle,
  FileText,
  Languages,
  Search,
  type LucideIcon,
} from 'lucide-react';

interface Suggestion {
  id: string;
  title: string;
  description: string;
  icon: LucideIcon;
}

const SUGGESTIONS: Suggestion[] = [
  {
    id: 'search',
    title: '아이두 통합검색',
    description: '사내 문서 검색',
    icon: Search,
  },
  {
    id: 'fmea-compare',
    title: 'FMEA 비교',
    description: '리스크 항목 비교',
    icon: AlertTriangle,
  },
  {
    id: 'drafting',
    title: '기안 초안',
    description: '공문/협조전 초안',
    icon: FileText,
  },
  {
    id: 'translate',
    title: '문서 번역/요약',
    description: 'OCR/번역/요약',
    icon: Languages,
  },
];

interface EmptyStateProps {
  composer: ReactNode;
  greeting?: string;
  subline?: string;
  getSuggestionHref?: (suggestion: Suggestion) => string;
}

export function EmptyState({
  composer,
  greeting = '안녕하세요, 업무를 도와드릴게요.',
  subline = '아래 도구로 바로 이동하거나 궁금한 것을 입력해 보세요.',
  getSuggestionHref,
}: EmptyStateProps) {
  return (
    <div className="flex flex-1 items-center justify-center px-6 py-10">
      <div className="w-full max-w-2xl space-y-6">
        <div className="text-center">
          <h2 className="app-text-title-lg text-app-ink">{greeting}</h2>
          <p className="mt-1 app-text-body-sm text-gray-500 dark:text-gray-400">
            {subline}
          </p>
        </div>
        {composer}
        <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
          {SUGGESTIONS.map((item) => (
            <Link
              key={item.id}
              to={getSuggestionHref?.(item) ?? `/tool/${item.id}`}
              className="group flex items-start gap-2 rounded-lg border border-app-border bg-app-surface px-3 py-3 no-underline transition-colors hover:border-app-accent"
            >
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-app-border bg-app-bg text-app-accent">
                <item.icon size={14} />
              </div>
              <div className="min-w-0">
                <div className="app-text-control-sm truncate text-app-ink">
                  {item.title}
                </div>
                <div className="app-text-micro truncate text-gray-500">
                  {item.description}
                </div>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
