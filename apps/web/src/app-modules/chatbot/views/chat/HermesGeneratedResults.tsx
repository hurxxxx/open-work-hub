import { FileText } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { formatDateTime } from '@/src/platform/time/time-utils';
import type {
  HermesFile,
  HermesFileRevision,
  HermesRun,
} from '../../api/hermes-agent-api';
import { hermesFilePreviewKind } from './hermes-file-preview';

const activeStatuses = new Set([
  'pending',
  'dispatching',
  'queued',
  'running',
  'awaiting_approval',
  'stopping',
]);

/** Only server-owned revision metadata establishes a generated result. */
export function generatedPreviews(
  files: HermesFile[],
  revisions: HermesFileRevision[],
  sessionId: string,
) {
  const current = new Map(files.map((file) => [file.id, file]));
  const seen = new Set<string>();
  return revisions.filter((revision) => {
    const file = current.get(revision.file_id);
    if (revision.session_id !== sessionId || !file || seen.has(file.id))
      return false;
    seen.add(file.id);
    if (!revision.run_id || file.sha256 !== revision.sha256) return false;
    const kind = hermesFilePreviewKind(revision);
    return kind !== null && kind !== 'code';
  });
}

export function HermesGeneratedResults({
  sessionId,
  files,
  revisions,
  runs,
  canAutoOpen,
  loaded = true,
  onOpenFile,
}: {
  sessionId: string;
  files: HermesFile[];
  revisions: HermesFileRevision[];
  runs: HermesRun[];
  canAutoOpen: boolean;
  loaded?: boolean;
  onOpenFile: (fileId: string, revisionId?: string) => void;
}) {
  const { t } = useTranslation('apps');
  const [autoOpen, setAutoOpen] = useState(false);
  const observedRuns = useRef(new Set<string>());
  const handledRuns = useRef(new Set<string>());
  const knownRuns = useRef<Set<string> | null>(null);
  const results = useMemo(
    () => generatedPreviews(files, revisions, sessionId),
    [files, revisions, sessionId],
  );

  useEffect(() => {
    if (!loaded) return;
    const currentRunIds = new Set(
      runs
        .filter((run) => run.session_binding_id === sessionId)
        .map((run) => run.id),
    );
    if (knownRuns.current) {
      for (const id of currentRunIds) {
        if (!knownRuns.current.has(id)) observedRuns.current.add(id);
      }
    }
    knownRuns.current = currentRunIds;
    const hasActiveRun = runs.some(
      (run) =>
        run.session_binding_id === sessionId && activeStatuses.has(run.status),
    );
    for (const run of runs) {
      if (run.session_binding_id !== sessionId) continue;
      if (activeStatuses.has(run.status)) {
        observedRuns.current.add(run.id);
        continue;
      }
      if (!observedRuns.current.has(run.id) || handledRuns.current.has(run.id))
        continue;
      const result = results.find((item) => item.run_id === run.id);
      if (run.status === 'completed' && !result) continue;
      handledRuns.current.add(run.id);
      const activeElement = document.activeElement;
      const editing =
        activeElement instanceof HTMLElement &&
        (activeElement.matches('select') ||
          ((activeElement instanceof HTMLTextAreaElement ||
            (activeElement instanceof HTMLInputElement &&
              !['checkbox', 'radio', 'button', 'submit'].includes(
                activeElement.type,
              ))) &&
            activeElement.value.length > 0) ||
          (activeElement.isContentEditable &&
            !!activeElement.textContent?.trim()));
      if (
        run.status === 'completed' &&
        result &&
        autoOpen &&
        canAutoOpen &&
        !hasActiveRun &&
        document.visibilityState === 'visible' &&
        !editing
      ) {
        onOpenFile(result.file_id, result.id);
        break;
      }
    }
  }, [runs, results, sessionId, autoOpen, canAutoOpen, onOpenFile, loaded]);

  return (
    <section
      aria-label={t('ai.generatedResults.title')}
      className="min-w-0 px-4 pb-2 text-app-ink"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 app-text-caption text-app-ink/65">
        <span>
          {loaded
            ? t('ai.generatedResults.count', { count: results.length })
            : t('hermesWorkspace.loading')}
        </span>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={autoOpen}
            disabled={!loaded}
            onChange={(event) => setAutoOpen(event.target.checked)}
          />
          {t('ai.generatedResults.autoOpen')}
        </label>
      </div>
      {results.length > 0 ? (
        <ul className="mt-2 flex max-h-32 gap-2 overflow-auto pb-1">
          {results.map((result) => (
            <li key={result.id} className="w-64 shrink-0">
              <button
                type="button"
                onClick={() => onOpenFile(result.file_id, result.id)}
                className="flex w-full items-center gap-2 rounded-md border border-app-border px-3 py-2 text-left hover:bg-app-surface-hover focus-visible:ring-2 focus-visible:ring-app-accent"
              >
                <FileText size={18} className="shrink-0 text-app-ink/65" />
                <span className="min-w-0">
                  <span
                    className="block truncate app-text-body-sm"
                    title={result.relative_path}
                  >
                    {result.relative_path}
                  </span>
                  <span className="block app-text-caption text-app-ink/65">
                    {t('ai.generatedResults.openVersion', {
                      time: formatDateTime(result.created_at, {
                        dateStyle: 'short',
                        timeStyle: 'short',
                      }),
                    })}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
