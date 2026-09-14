import { ChevronDown, Loader2, Wrench } from 'lucide-react';
import { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { ToolCallBuffer } from '../../api/agent-events';
import { ToolCallCard } from './ToolCallCard';

/** Execution details belong to their answer, never the composer. */
export function ToolCallGroup({
  calls,
  isRunning = false,
}: {
  calls: readonly ToolCallBuffer[];
  isRunning?: boolean;
}) {
  const { t } = useTranslation('apps');
  const contentId = useId();
  const [expanded, setExpanded] = useState(false);
  if (calls.length === 0) return null;
  const hasActiveTool =
    isRunning && calls.some((call) => call.status === 'running');
  const failures = calls.filter((call) => call.status === 'error').length;
  const rejections = calls.filter((call) => call.status === 'rejected').length;
  const Icon = hasActiveTool ? Loader2 : Wrench;

  return (
    <section
      className="my-2 min-w-0 border-y border-app-border"
      data-tool-call-group
    >
      <button
        type="button"
        aria-expanded={expanded}
        aria-controls={contentId}
        onClick={() => setExpanded((value) => !value)}
        className="flex w-full items-center gap-2 py-2 text-left app-text-caption text-app-ink/65"
      >
        <Icon
          size={14}
          className={hasActiveTool ? 'animate-spin' : undefined}
        />
        <span>
          {t(hasActiveTool ? 'ai.toolCall.groupRunning' : 'ai.toolCall.group', {
            count: calls.length,
          })}
        </span>
        {failures > 0 ? (
          <span className="text-app-danger-text">
            {t('ai.toolCall.groupFailures', { count: failures })}
          </span>
        ) : null}
        {rejections > 0 ? (
          <span className="text-app-danger-text">
            {t('ai.toolCall.groupRejections', { count: rejections })}
          </span>
        ) : null}
        <ChevronDown
          size={14}
          className={`ml-auto transition-transform ${expanded ? 'rotate-180' : ''}`}
        />
      </button>
      {expanded ? (
        <div id={contentId}>
          {failures > 0 || rejections > 0 ? (
            <p className="px-5 py-2 app-text-caption text-app-ink/65">
              {t('ai.toolCall.attemptsExplanation')}
            </p>
          ) : null}
          {calls.map((call, index) => (
            <ToolCallCard
              key={call.call_id || `unidentified-${index}`}
              call={
                !isRunning && call.status === 'running'
                  ? { ...call, status: 'unknown' }
                  : call
              }
            />
          ))}
        </div>
      ) : null}
    </section>
  );
}
