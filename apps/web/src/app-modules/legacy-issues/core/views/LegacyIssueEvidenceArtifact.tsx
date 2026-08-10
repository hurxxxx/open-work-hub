import { Database, Paperclip, Search } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  resolveLegacyIssueAssistantEvidence,
  type LegacyIssueAssistantEvidenceRef,
} from '../api/legacy-issue-assistant-api';

interface LegacyIssueEvidencePayload {
  version?: number;
  mode?: string;
  retrieval_profile?: Record<string, unknown>;
  evidence?: LegacyIssueEvidenceRow[];
  evidence_refs?: LegacyIssueAssistantEvidenceRef[];
}

interface LegacyIssueEvidenceRow {
  id?: string;
  evidence_id?: string;
  dataset_key?: string;
  dataset_title?: string;
  record_id?: string;
  label?: string;
  score?: number;
  methods?: string[];
  matched_fields?: string[];
  matched_chunks?: Array<{
    attachment_filename?: string | null;
    attachment_page?: number | null;
    field_label?: string | null;
    excerpt?: string;
    methods?: string[];
  }>;
  attachments?: Array<{
    id: string;
    filename: string;
    description?: string | null;
    index_status?: string;
    matched_chunks?: Array<{
      attachment_page?: number | null;
      excerpt?: string;
    }>;
  }>;
  values?: Record<string, string>;
}

export function LegacyIssueEvidenceArtifact({ content }: { content: string }) {
  const { t } = useTranslation('apps');
  const { token } = useAuth();
  const { workspaceSlug } = useParams();
  const parsed = useMemo(() => parseEvidencePayload(content), [content]);
  const [resolved, setResolved] = useState<
    | { status: 'idle'; payload: LegacyIssueEvidencePayload | null }
    | { status: 'loading'; payload: LegacyIssueEvidencePayload | null }
    | { status: 'error'; payload: LegacyIssueEvidencePayload | null }
    | { status: 'ready'; payload: LegacyIssueEvidencePayload }
  >({ status: 'idle', payload: parsed.ok ? parsed.payload : null });

  useEffect(() => {
    if (!parsed.ok) {
      setResolved({ status: 'error', payload: null });
      return;
    }
    if (parsed.payload.evidence || !parsed.payload.evidence_refs?.length) {
      setResolved({ status: 'ready', payload: parsed.payload });
      return;
    }
    if (!token || !workspaceSlug) {
      setResolved({ status: 'error', payload: parsed.payload });
      return;
    }
    let cancelled = false;
    setResolved({ status: 'loading', payload: parsed.payload });
    resolveLegacyIssueAssistantEvidence({
      evidenceRefs: parsed.payload.evidence_refs,
      retrievalProfile: parsed.payload.retrieval_profile,
      token,
      workspaceSlug,
    })
      .then((response) => {
        if (cancelled) return;
        setResolved({
          status: 'ready',
          payload: {
            ...parsed.payload,
            retrieval_profile: response.retrieval_profile,
            evidence: response.evidence,
          },
        });
      })
      .catch(() => {
        if (cancelled) return;
        setResolved({ status: 'error', payload: parsed.payload });
      });
    return () => {
      cancelled = true;
    };
  }, [parsed, token, workspaceSlug]);

  if (!parsed.ok) {
    return <InvalidEvidence content={content} />;
  }

  if (resolved.status === 'loading') {
    return (
      <div className="rounded-md border border-app-border bg-app-bg p-6 text-center app-text-body-sm text-app-ink/60">
        {t('ai.processing')}
      </div>
    );
  }

  if (resolved.status === 'error' && !resolved.payload?.evidence) {
    return <InvalidEvidence content={content} />;
  }

  const payload = resolved.payload ?? parsed.payload;
  const evidence = payload.evidence ?? [];
  const profile = payload.retrieval_profile ?? {};
  const methods = asStringArray(profile.methods);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-flex h-7 items-center gap-1.5 rounded-md border border-app-border bg-app-bg px-2 app-text-caption text-app-ink/70">
          <Database size={13} />
          {t('ai.artifacts.legacyIssueEvidence.rowCount', {
            count: evidence.length,
          })}
        </span>
        {typeof profile.semantic_enabled === 'boolean' ? (
          <span className="inline-flex h-7 items-center gap-1.5 rounded-md border border-app-border bg-app-bg px-2 app-text-caption text-app-ink/70">
            <Search size={13} />
            {profile.semantic_enabled
              ? t('ai.artifacts.legacyIssueEvidence.semanticOn')
              : t('ai.artifacts.legacyIssueEvidence.semanticOff')}
          </span>
        ) : null}
        {methods.map((method) => (
          <span
            key={method}
            className="inline-flex h-7 items-center rounded-md border border-app-border bg-app-bg px-2 app-text-caption text-app-ink/60"
          >
            {method}
          </span>
        ))}
      </div>

      {evidence.length === 0 ? (
        <div className="rounded-md border border-dashed border-app-border bg-app-bg p-6 text-center app-text-body-sm text-app-ink/55">
          {t('ai.artifacts.legacyIssueEvidence.empty')}
        </div>
      ) : (
        <div className="custom-scrollbar overflow-auto rounded-md border border-app-border">
          <table className="min-w-[980px] w-full border-collapse bg-app-surface app-text-caption">
            <thead className="sticky top-0 bg-app-surface-sidebar text-left text-app-ink/55">
              <tr>
                <th className="w-20 border-b border-app-border px-3 py-2 font-semibold">
                  {t('ai.artifacts.legacyIssueEvidence.id')}
                </th>
                <th className="w-44 border-b border-app-border px-3 py-2 font-semibold">
                  {t('ai.artifacts.legacyIssueEvidence.dataset')}
                </th>
                <th className="w-44 border-b border-app-border px-3 py-2 font-semibold">
                  {t('ai.artifacts.legacyIssueEvidence.record')}
                </th>
                <th className="border-b border-app-border px-3 py-2 font-semibold">
                  {t('ai.artifacts.legacyIssueEvidence.summary')}
                </th>
                <th className="w-28 border-b border-app-border px-3 py-2 font-semibold">
                  {t('ai.artifacts.legacyIssueEvidence.score')}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-app-border">
              {evidence.map((row, index) => (
                <tr key={`${rowId(row, index)}-${row.record_id ?? ''}`}>
                  <td className="align-top px-3 py-2 font-semibold text-app-accent">
                    {rowId(row, index)}
                  </td>
                  <td className="align-top px-3 py-2 text-app-ink/75">
                    <div className="font-medium text-app-ink">
                      {row.dataset_title || row.dataset_key || '-'}
                    </div>
                    {row.dataset_key ? (
                      <div className="mt-0.5 text-app-ink/45">
                        {row.dataset_key}
                      </div>
                    ) : null}
                  </td>
                  <td className="align-top px-3 py-2 text-app-ink/65">
                    <div className="max-w-[12rem] truncate">
                      {row.record_id || '-'}
                    </div>
                    {row.matched_fields?.length ? (
                      <div className="mt-1 flex flex-wrap gap-1">
                        {row.matched_fields.slice(0, 3).map((field) => (
                          <span
                            key={field}
                            className="rounded border border-app-border bg-app-bg px-1.5 py-0.5 app-text-micro text-app-ink/55"
                          >
                            {field}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </td>
                  <td className="align-top px-3 py-2 text-app-ink/80">
                    <div className="max-w-[44rem]">
                      <div className="font-medium text-app-ink">
                        {row.label || summaryFromValues(row.values)}
                      </div>
                      <div className="mt-1 line-clamp-3 text-app-ink/60">
                        {summaryFromChunks(row) ||
                          summaryFromValues(row.values)}
                      </div>
                      {row.attachments?.length ? (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {row.attachments.slice(0, 4).map((attachment) => (
                            <span
                              key={attachment.id}
                              className="inline-flex max-w-[18rem] items-center gap-1 truncate rounded border border-app-border bg-app-bg px-1.5 py-0.5 app-text-micro text-app-ink/60"
                              title={attachment.description || attachment.filename}
                            >
                              <Paperclip size={11} className="shrink-0" />
                              <span className="truncate">
                                {attachment.filename}
                              </span>
                            </span>
                          ))}
                        </div>
                      ) : null}
                      {row.methods?.length ? (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {row.methods.map((method) => (
                            <span
                              key={method}
                              className="rounded border border-app-border bg-app-bg px-1.5 py-0.5 app-text-micro text-app-ink/55"
                            >
                              {method}
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  </td>
                  <td className="align-top px-3 py-2 text-app-ink/65">
                    {formatScore(row.score)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function InvalidEvidence({ content }: { content: string }) {
  const { t } = useTranslation('apps');

  return (
    <div className="rounded-md border border-app-border bg-app-bg p-4">
      <p className="app-text-body-sm text-app-ink">
        {t('ai.artifacts.legacyIssueEvidence.invalid')}
      </p>
      <pre className="custom-scrollbar mt-3 max-h-[32rem] overflow-auto rounded-md bg-app-surface p-3 app-text-caption text-app-ink/75">
        {content}
      </pre>
    </div>
  );
}

function parseEvidencePayload(
  content: string,
): { ok: true; payload: LegacyIssueEvidencePayload } | { ok: false } {
  try {
    const parsed = JSON.parse(content) as unknown;
    if (Array.isArray(parsed)) {
      return {
        ok: true,
        payload: { evidence: parsed as LegacyIssueEvidenceRow[] },
      };
    }
    if (parsed && typeof parsed === 'object') {
      return { ok: true, payload: parsed as LegacyIssueEvidencePayload };
    }
  } catch {
    return { ok: false };
  }
  return { ok: false };
}

function rowId(row: LegacyIssueEvidenceRow, index: number): string {
  return row.id ?? row.evidence_id ?? `E${index + 1}`;
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string')
    : [];
}

function summaryFromChunks(row: LegacyIssueEvidenceRow): string {
  const chunks = row.matched_chunks ?? [];
  return chunks
    .map((chunk) => chunk.excerpt?.trim())
    .filter((value): value is string => Boolean(value))
    .slice(0, 2)
    .join(' / ');
}

function summaryFromValues(values: Record<string, string> | undefined): string {
  if (!values) return '-';
  const keys = [
    'vehicle_model',
    'problem',
    'symptom',
    'cause',
    'countermeasure',
    'action',
    'notes',
  ];
  const parts = keys
    .map((key) => values[key]?.trim())
    .filter((value): value is string => Boolean(value));
  return parts.slice(0, 3).join(' / ') || '-';
}

function formatScore(score: number | undefined): string {
  if (typeof score !== 'number' || !Number.isFinite(score)) {
    return '-';
  }
  return score.toFixed(score >= 10 ? 1 : 3);
}
