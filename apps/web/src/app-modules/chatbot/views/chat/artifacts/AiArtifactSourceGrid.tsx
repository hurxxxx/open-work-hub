import { Database } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { AiArtifactSource } from '../../../api/ai-artifacts-api';

export function AiArtifactSourceGrid({
  sources,
}: {
  sources: readonly AiArtifactSource[];
}) {
  const { t } = useTranslation('apps');

  if (sources.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-app-border bg-app-bg p-6 text-center app-text-body-sm text-app-ink/55">
        {t('ai.artifacts.reportDetail.sources.empty')}
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {sources.map((source) => (
        <section
          key={source.id}
          className="overflow-hidden rounded-md border border-app-border bg-app-surface"
          aria-labelledby={`ai-artifact-source-${source.id}`}
        >
          <header className="flex flex-wrap items-start justify-between gap-2 border-b border-app-border bg-app-surface-sidebar px-3 py-2.5">
            <div className="min-w-0">
              <h3
                id={`ai-artifact-source-${source.id}`}
                className="truncate app-text-body-sm font-semibold text-app-ink"
              >
                {source.title ||
                  t('ai.artifacts.reportDetail.sources.untitled')}
              </h3>
            </div>
            <span className="inline-flex shrink-0 items-center gap-1 rounded-md border border-app-border bg-app-bg px-2 py-1 app-text-micro text-app-ink/60">
              <Database aria-hidden="true" size={12} />
              {t('ai.artifacts.reportDetail.sources.rowCount', {
                count: source.rowCount,
              })}
            </span>
          </header>

          {source.columns.length === 0 || source.rows.length === 0 ? (
            <div className="px-3 py-6 text-center app-text-body-sm text-app-ink/55">
              {t('ai.artifacts.reportDetail.sources.noRows')}
            </div>
          ) : (
            <div className="custom-scrollbar overflow-auto">
              <table className="min-w-full border-collapse app-text-caption">
                <caption className="sr-only">
                  {source.title ||
                    t('ai.artifacts.reportDetail.sources.untitled')}
                </caption>
                <thead className="bg-app-bg text-left text-app-ink/55">
                  <tr>
                    {source.columns.map((column) => (
                      <th
                        key={column.key}
                        scope="col"
                        className="whitespace-nowrap border-b border-app-border px-3 py-2 font-semibold"
                      >
                        {column.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-app-border">
                  {source.rows.map((row, index) => (
                    <tr key={`${source.id}-${index}`}>
                      {source.columns.map((column) => (
                        <td
                          key={column.key}
                          className="max-w-[32rem] whitespace-pre-wrap break-words px-3 py-2 align-top text-app-ink/75"
                        >
                          {formatSourceCell(row[column.key])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {source.truncated ? (
            <p className="border-t border-app-border px-3 py-2 app-text-micro text-app-ink/55">
              {t('ai.artifacts.reportDetail.sources.truncated')}
            </p>
          ) : null}
        </section>
      ))}
    </div>
  );
}

function formatSourceCell(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}
