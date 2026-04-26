import type { ReactNode } from 'react';

interface EmptyStateProps {
  composer: ReactNode;
  greeting?: string;
  subline?: string;
}

export function EmptyState({
  composer,
  greeting = '안녕하세요, 업무를 도와드릴게요.',
  subline = '궁금한 것을 입력하거나 슬래시(/)로 도구를 호출해 보세요.',
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
      </div>
    </div>
  );
}
