import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type ReactNode,
} from 'react';
import { useTranslation } from 'react-i18next';
import {
  ChevronDown,
  Download,
  Loader2,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Trash2,
} from 'lucide-react';

import { useAuth } from '@/src/platform/auth/auth-provider';
import { useWorkspaceBootstrapContext } from '@/src/platform/workspaces/workspace-bootstrap-context';
import { resolveShellWorkspaceSlug } from '@/src/platform/workspaces/workspace-utils';
import { cn } from '@/src/lib/utils';
import {
  patentClaimsExplain,
  patentDescriptionMapping,
  patentFetch,
  patentInfringeCheck,
  patentRightsScope,
  patentTranslate,
  PatentApiError,
  type ClaimsExplainResult,
  type DescriptionMappingResult,
  type InfringeCheckResult,
  type PatentDetail,
  type RightsScopeResult,
} from '../api/patent-api';

type TabId = 'claims' | 'rights' | 'mapping' | 'infringe';

const TAB_EMOJI: Record<TabId, string> = {
  claims: '📋',
  rights: '⚖️',
  mapping: '🔗',
  infringe: '🛡️',
};
const TAB_ORDER: TabId[] = ['claims', 'rights', 'mapping', 'infringe'];

interface HistoryEntry {
  number: string;
  title: string;
}

function historyStorageKey(workspaceSlug: string | null): string | null {
  return workspaceSlug
    ? `open-alm.patent.analysis.history.${workspaceSlug}`
    : null;
}

function readHistory(workspaceSlug: string | null): HistoryEntry[] {
  const key = historyStorageKey(workspaceSlug);
  if (!key || typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as HistoryEntry[]) : [];
  } catch {
    return [];
  }
}

function writeHistory(
  workspaceSlug: string | null,
  entries: HistoryEntry[],
): void {
  const key = historyStorageKey(workspaceSlug);
  if (!key || typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(key, JSON.stringify(entries.slice(0, 30)));
  } catch {
    // Quota/disabled storage — history is best-effort only.
  }
}

function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof PatentApiError) return error.message;
  if (error instanceof Error) return error.message;
  return fallback;
}

/** Loosely-typed LLM rows — read fields defensively. */
function str(row: Record<string, unknown>, key: string): string {
  const value = row[key];
  return typeof value === 'string' ? value : value == null ? '' : String(value);
}
function strArray(row: Record<string, unknown>, key: string): string[] {
  const value = row[key];
  return Array.isArray(value) ? value.map((item) => String(item)) : [];
}
function rowArray(
  row: Record<string, unknown>,
  key: string,
): Array<Record<string, unknown>> {
  const value = row[key];
  return Array.isArray(value) ? (value as Array<Record<string, unknown>>) : [];
}

function escHtml(value: unknown): string {
  return (value == null ? '' : String(value))
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

type ReportHtmlText = (
  key: string,
  options?: Record<string, unknown>,
) => string;

/**
 * Build a self-contained HTML report (patent bibliography + whichever analyses
 * have been run) for download as reference material. Sections are emitted only
 * when their data exists.
 */
function buildPatentReportHtml(
  detail: PatentDetail,
  claims: ClaimsExplainResult | null,
  rights: RightsScopeResult | null,
  mapping: DescriptionMappingResult | null,
  stamp: string,
  tr: ReportHtmlText,
  translated?: { abstract: string; claims: string[] },
): string {
  const d = detail as unknown as Record<string, unknown>;
  const num = detail.app_no || detail.reg_no || detail.title || 'report';
  const sections: string[] = [];

  // 1) Bibliography
  const meta: string[] = [];
  const row = (k: string, v: string) => {
    if (v) meta.push(`<tr><th>${escHtml(k)}</th><td>${escHtml(v)}</td></tr>`);
  };
  row(tr('meta.title'), detail.title);
  row(tr('meta.titleEng'), detail.title_eng);
  row(tr('meta.appNo'), detail.app_no);
  row(tr('meta.regNo'), detail.reg_no);
  row(tr('meta.openNo'), detail.open_no);
  row(tr('meta.applicant'), detail.applicant);
  row(tr('meta.status'), detail.status);
  row(tr('meta.finalDisposal'), detail.final_disposal);
  row(tr('meta.applicationDate'), detail.date);
  row(tr('meta.openDate'), detail.open_date);
  row(tr('meta.registrationDate'), detail.reg_date);
  row('IPC', detail.ipc);
  const googleUrl = str(d, 'google_patents_url');
  if (googleUrl) {
    meta.push(
      `<tr><th>${escHtml(tr('meta.googlePatents'))}</th><td><a href="${escHtml(googleUrl)}">${escHtml(googleUrl)}</a></td></tr>`,
    );
  }
  if (meta.length) {
    sections.push(
      `<section><h2>${escHtml(tr('sections.basicInfo'))}</h2><table class="meta">${meta.join('')}</table></section>`,
    );
  }

  const absKo = translated?.abstract ?? '';
  const claimsKo = translated?.claims ?? [];

  if (detail.abstract) {
    const body = absKo
      ? `<p class="abs">${escHtml(absKo)}</p><div class="orig"><span class="origlbl">${escHtml(tr('common.original'))}</span>${escHtml(detail.abstract)}</div>`
      : `<p class="abs">${escHtml(detail.abstract)}</p>`;
    sections.push(
      `<section><h2>${escHtml(tr('sections.abstract'))}</h2>${body}</section>`,
    );
  }

  if (detail.claims.length) {
    const items = detail.claims
      .map((c, i) => {
        const ko = claimsKo[i];
        return ko
          ? `<li>${escHtml(ko)}<div class="orig"><span class="origlbl">${escHtml(tr('common.original'))}</span>${escHtml(c)}</div></li>`
          : `<li>${escHtml(c)}</li>`;
      })
      .join('');
    const labelKey =
      absKo || claimsKo.length
        ? 'sections.claimsTranslatedCount'
        : 'sections.claimsCount';
    sections.push(
      `<section><h2>${escHtml(tr(labelKey, { count: detail.claims.length }))}</h2><ol class="claims">${items}</ol></section>`,
    );
  }

  // Claims explanation
  if (claims) {
    let h = '';
    if (claims.summary)
      h += `<h3>${escHtml(tr('claims.summary'))}</h3><p>${escHtml(claims.summary)}</p>`;
    if (claims.key_features?.length) {
      h += `<h3>${escHtml(tr('claims.keyFeatures'))}</h3><ol>${claims.key_features.map((f) => `<li>${escHtml(f)}</li>`).join('')}</ol>`;
    }
    if (claims.technical_significance) {
      h += `<h3>${escHtml(tr('claims.significance'))}</h3><p>${escHtml(claims.technical_significance)}</p>`;
    }
    if (claims.per_claim?.length) {
      h += `<h3>${escHtml(tr('claims.perClaim'))}</h3>`;
      for (const c of claims.per_claim) {
        h += `<div class="card"><div class="cardt">${escHtml(tr('claimNumber', { num: str(c, 'claim_num') }))} <span class="tag">${escHtml(str(c, 'type'))}</span></div><p>${escHtml(str(c, 'explanation'))}</p></div>`;
      }
    }
    if (h)
      sections.push(
        `<section><h2>${escHtml(tr('sections.claimExplanation'))}</h2>${h}</section>`,
      );
  }

  // Rights scope
  if (rights) {
    let h = '';
    if (rights.overall_analysis) {
      const heading = rights.scope_breadth
        ? tr('rights.overallWithScope', { scope: rights.scope_breadth })
        : tr('rights.overall');
      h += `<h3>${escHtml(heading)}</h3><p>${escHtml(rights.overall_analysis)}</p>`;
    }
    if (rights.key_elements?.length) {
      h += `<h3>${escHtml(tr('rights.keyElements'))}</h3><p>${rights.key_elements.map((e) => `<span class="kw">${escHtml(e)}</span>`).join(' ')}</p>`;
    }
    if (rights.per_claim?.length) {
      h += `<h3>${escHtml(tr('rights.perClaimScope'))}</h3>`;
      for (const c of rights.per_claim) {
        const claimTitle = str(c, 'breadth')
          ? tr('rights.claimWithScope', {
              num: str(c, 'claim_num'),
              scope: str(c, 'breadth'),
            })
          : tr('claimNumber', { num: str(c, 'claim_num') });
        h += `<div class="card"><div class="cardt">${escHtml(claimTitle)} <span class="tag">${escHtml(str(c, 'type'))}</span></div><p>${escHtml(str(c, 'scope_summary'))}</p>`;
        const els = strArray(c, 'elements');
        if (els.length)
          h += `<p>${els.map((e) => `<span class="kw">${escHtml(e)}</span>`).join(' ')}</p>`;
        const notes = str(c, 'notes');
        if (notes) h += `<p class="note">${escHtml(notes)}</p>`;
        h += '</div>';
      }
    }
    if (rights.caution)
      h += `<p class="caution">⚠ ${escHtml(rights.caution)}</p>`;
    if (h)
      sections.push(
        `<section><h2>${escHtml(tr('sections.rightsScope'))}</h2>${h}</section>`,
      );
  }

  // Description mapping
  if (mapping?.mappings?.length) {
    let h = '';
    const sorted = [...mapping.mappings].sort(
      (a, b) => Number(a.claim_num ?? 0) - Number(b.claim_num ?? 0),
    );
    for (const m of sorted) {
      h += `<div class="card"><div class="cardt">${escHtml(tr('claimNumber', { num: str(m, 'claim_num') }))}</div>`;
      const summary = str(m, 'claim_summary');
      if (summary) h += `<p>${escHtml(summary)}</p>`;
      for (const el of rowArray(m, 'elements')) {
        h += `<div class="map"><div class="mapk">${escHtml(str(el, 'element'))}</div><div class="mapv">${escHtml(str(el, 'mapped_text'))}</div></div>`;
      }
      h += '</div>';
    }
    sections.push(
      `<section><h2>${escHtml(tr('sections.descriptionMapping'))}</h2>${h}</section>`,
    );
  }

  if (detail.warning) {
    sections.unshift(`<p class="caution">⚠ ${escHtml(detail.warning)}</p>`);
  }

  return `<!DOCTYPE html><html lang="${escHtml(tr('lang'))}"><head><meta charset="utf-8">
<title>${escHtml(tr('documentTitle', { num }))}</title>
<style>
  body{font-family:"Malgun Gothic",Arial,sans-serif;color:#1a1a1a;line-height:1.65;max-width:900px;margin:0 auto;padding:32px 24px;}
  h1{font-size:20px;border-bottom:2px solid #333;padding-bottom:10px;margin-bottom:4px;}
  .sub{color:#777;font-size:12px;margin-bottom:24px;}
  h2{font-size:15px;margin:28px 0 10px;padding:6px 10px;background:#f3f4f6;border-left:4px solid #2563eb;}
  h3{font-size:13px;margin:16px 0 6px;color:#2563eb;}
  table.meta{border-collapse:collapse;width:100%;font-size:12.5px;}
  table.meta th{text-align:left;width:120px;color:#555;background:#fafafa;border:1px solid #e5e7eb;padding:6px 10px;vertical-align:top;}
  table.meta td{border:1px solid #e5e7eb;padding:6px 10px;}
  .abs{font-size:12.5px;background:#fafafa;padding:12px;border-radius:6px;}
  ol.claims li{margin-bottom:10px;font-size:12.5px;}
  .orig{margin-top:5px;font-size:11px;color:#999;background:#fafafa;border-left:2px solid #ddd;padding:4px 8px;border-radius:3px;}
  .origlbl{display:inline-block;font-size:9px;color:#aaa;border:1px solid #ddd;border-radius:6px;padding:0 5px;margin-right:6px;}
  .card{border:1px solid #e5e7eb;border-radius:6px;padding:10px 12px;margin:8px 0;}
  .cardt{font-weight:600;font-size:12.5px;margin-bottom:4px;}
  .tag{font-size:10px;background:#eef2ff;color:#3730a3;border-radius:8px;padding:1px 7px;margin-left:4px;}
  .kw{display:inline-block;font-size:11px;background:#eef2ff;color:#1e3a8a;border-radius:10px;padding:2px 8px;margin:2px;}
  .note{font-size:11px;color:#777;}
  .caution{background:#fff7ed;border:1px solid #fdba74;color:#9a3412;border-radius:6px;padding:8px 12px;font-size:12px;}
  .map{display:flex;gap:8px;margin:4px 0;font-size:12px;}
  .mapk{flex:0 0 200px;font-weight:600;color:#1e3a8a;}
  .mapv{flex:1;background:#f8fafc;border-left:3px solid #2563eb;padding:4px 8px;border-radius:4px;}
  .qa{display:flex;gap:8px;margin:6px 0;font-size:12.5px;}
  .qa .role{flex:0 0 20px;font-weight:700;color:#2563eb;}
  .qa.user{background:#f8fafc;padding:6px 8px;border-radius:4px;}
  p{margin:6px 0;}
  a{color:#2563eb;word-break:break-all;}
  @media print{body{padding:0;}}
</style></head><body>
<h1>${escHtml(tr('heading', { num }))}</h1>
<div class="sub">${escHtml(tr('subtitle', { stamp }))}</div>
${sections.join('\n')}
</body></html>`;
}

export function PatentAnalysisView() {
  const { t } = useTranslation(['apps', 'common']);
  const { token, user } = useAuth();
  const workspaceBootstrap = useWorkspaceBootstrapContext();
  const workspaceSlug =
    workspaceBootstrap.data?.workspace.slug ??
    resolveShellWorkspaceSlug(user, null);

  const [tab, setTab] = useState<TabId>('claims');
  const [numberInput, setNumberInput] = useState('');
  const [fetching, setFetching] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [detail, setDetail] = useState<PatentDetail | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);

  // ── Analysis tabs ─────────────────────────────────────────────────────────
  const [historyOpen, setHistoryOpen] = useState(true);
  const [reportBusy, setReportBusy] = useState(false);
  const [claimsBusy, setClaimsBusy] = useState(false);
  const [claimsResult, setClaimsResult] = useState<ClaimsExplainResult | null>(
    null,
  );
  const [rightsBusy, setRightsBusy] = useState(false);
  const [rightsResult, setRightsResult] = useState<RightsScopeResult | null>(
    null,
  );
  const [mappingBusy, setMappingBusy] = useState(false);
  const [mappingResult, setMappingResult] =
    useState<DescriptionMappingResult | null>(null);
  const [techInput, setTechInput] = useState('');
  const [infringeBusy, setInfringeBusy] = useState(false);
  const [infringeResult, setInfringeResult] =
    useState<InfringeCheckResult | null>(null);
  const [tabError, setTabError] = useState<string | null>(null);

  const fetchRequestRef = useRef(0);

  useEffect(() => {
    setHistory(readHistory(workspaceSlug));
  }, [workspaceSlug]);

  const recordHistory = useCallback(
    (entry: HistoryEntry) => {
      setHistory((current) => {
        const next = [
          entry,
          ...current.filter((h) => h.number !== entry.number),
        ].slice(0, 30);
        writeHistory(workspaceSlug, next);
        return next;
      });
    },
    [workspaceSlug],
  );

  const resetAnalysis = useCallback(() => {
    setClaimsResult(null);
    setRightsResult(null);
    setMappingResult(null);
    setInfringeResult(null);
    setTabError(null);
  }, []);

  const fetchPatent = useCallback(
    async (patentNumber: string) => {
      const trimmed = patentNumber.trim();
      if (!trimmed || !token || fetching) return;
      const requestId = fetchRequestRef.current + 1;
      fetchRequestRef.current = requestId;
      setFetching(true);
      setFetchError(null);
      try {
        const result = await patentFetch({
          token,
          workspaceSlug,
          patentNumber: trimmed,
        });
        if (fetchRequestRef.current !== requestId) return;
        setDetail(result);
        resetAnalysis();
        recordHistory({ number: trimmed, title: result.title || trimmed });
      } catch (error) {
        if (fetchRequestRef.current !== requestId) return;
        setFetchError(
          errorMessage(error, t('apps:ai.patentAnalysis.fetchFailed')),
        );
      } finally {
        if (fetchRequestRef.current === requestId) setFetching(false);
      }
    },
    [fetching, recordHistory, resetAnalysis, t, token, workspaceSlug],
  );

  const clearAllHistory = useCallback(() => {
    setHistory([]);
    writeHistory(workspaceSlug, []);
  }, [workspaceSlug]);

  // Builds the LLM prompt context for Ask 아이두. The labels below are prompt
  // markers (not UI copy); the backend wraps this string in a Korean section.
  const runClaims = useCallback(async () => {
    if (!detail || !token || claimsBusy) return;
    setClaimsBusy(true);
    setTabError(null);
    try {
      const result = await patentClaimsExplain({
        token,
        workspaceSlug,
        claims: detail.claims,
        abstract: detail.abstract,
        title: detail.title,
      });
      setClaimsResult(result);
    } catch (error) {
      setTabError(
        errorMessage(error, t('apps:ai.patentAnalysis.errors.connect')),
      );
    } finally {
      setClaimsBusy(false);
    }
  }, [claimsBusy, detail, t, token, workspaceSlug]);

  const runRights = useCallback(async () => {
    if (!detail || !token || rightsBusy) return;
    setRightsBusy(true);
    setTabError(null);
    try {
      const result = await patentRightsScope({
        token,
        workspaceSlug,
        claims: detail.claims,
        title: detail.title,
      });
      setRightsResult(result);
    } catch (error) {
      setTabError(
        errorMessage(error, t('apps:ai.patentAnalysis.errors.connect')),
      );
    } finally {
      setRightsBusy(false);
    }
  }, [detail, rightsBusy, t, token, workspaceSlug]);

  const runMapping = useCallback(async () => {
    if (!detail || !token || mappingBusy) return;
    setMappingBusy(true);
    setTabError(null);
    try {
      const result = await patentDescriptionMapping({
        token,
        workspaceSlug,
        claims: detail.claims,
        description: detail.description,
        abstract: detail.abstract,
      });
      setMappingResult(result);
    } catch (error) {
      setTabError(
        errorMessage(error, t('apps:ai.patentAnalysis.errors.connect')),
      );
    } finally {
      setMappingBusy(false);
    }
  }, [detail, mappingBusy, t, token, workspaceSlug]);

  const runInfringe = useCallback(async () => {
    const tech = techInput.trim();
    if (!detail || !tech || !token || infringeBusy) return;
    setInfringeBusy(true);
    setTabError(null);
    try {
      const result = await patentInfringeCheck({
        token,
        workspaceSlug,
        claims: detail.claims,
        title: detail.title,
        techDescription: tech,
      });
      setInfringeResult(result);
    } catch (error) {
      setTabError(
        errorMessage(error, t('apps:ai.patentAnalysis.errors.connect')),
      );
    } finally {
      setInfringeBusy(false);
    }
  }, [detail, infringeBusy, t, techInput, token, workspaceSlug]);

  const hasPatent = detail !== null && detail.claims.length > 0;

  const downloadReport = useCallback(async () => {
    if (!detail || reportBusy) return;
    setReportBusy(true);
    try {
      // Foreign patents have English abstract/claims — translate to Korean for
      // the report (the analyses are already Korean). Originals are kept too.
      let translated: { abstract: string; claims: string[] } | undefined;
      if (detail.foreign && token) {
        try {
          const texts = [detail.abstract || '', ...detail.claims];
          const { translations } = await patentTranslate({
            token,
            workspaceSlug,
            texts,
          });
          if (translations.length) {
            translated = {
              abstract: translations[0] || '',
              claims: translations.slice(1),
            };
          }
        } catch {
          // Translation is best-effort — fall back to the English original.
        }
      }
      const now = new Date();
      const stamp = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
      const html = buildPatentReportHtml(
        detail,
        claimsResult,
        rightsResult,
        mappingResult,
        stamp,
        (key, options) =>
          t(`apps:ai.patentAnalysis.reportHtml.${key}`, options),
        translated,
      );
      const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      const safeNum = (
        detail.app_no ||
        detail.reg_no ||
        detail.title ||
        'report'
      ).replace(/[\\/:*?"<>|]/g, '_');
      link.href = url;
      link.download = `${t('apps:ai.patentAnalysis.reportHtml.filePrefix')}_${safeNum}_${stamp}.html`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } finally {
      setReportBusy(false);
    }
  }, [
    detail,
    reportBusy,
    claimsResult,
    rightsResult,
    mappingResult,
    t,
    token,
    workspaceSlug,
  ]);

  return (
    <div className="flex h-full w-full flex-col overflow-hidden">
      {/* Top: patent number lookup */}
      <div className="flex items-center gap-2.5 border-b border-app-border px-4 py-3">
        <button
          type="button"
          onClick={() => setHistoryOpen((open) => !open)}
          title={t('ai.patentAnalysis.toggleHistory')}
          aria-pressed={historyOpen}
          className="hidden shrink-0 items-center justify-center rounded-md border border-app-border p-2 text-app-ink transition-colors hover:bg-app-surface-hover md:inline-flex"
        >
          {historyOpen ? (
            <PanelLeftClose size={16} />
          ) : (
            <PanelLeftOpen size={16} />
          )}
        </button>
        <div className="relative">
          <Search
            size={14}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-app-ink/55"
          />
          <input
            value={numberInput}
            onChange={(event) => setNumberInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') void fetchPatent(numberInput);
            }}
            placeholder={t('ai.patentAnalysis.numberPlaceholder')}
            className="w-80 rounded-lg border border-app-border bg-app-surface-sidebar py-2 pl-9 pr-3 app-text-body-sm text-app-ink outline-none focus:border-app-accent"
          />
        </div>
        <button
          type="button"
          onClick={() => void fetchPatent(numberInput)}
          disabled={fetching}
          className="app-text-control inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-app-accent px-4 py-2 font-semibold text-app-accent-fg transition-colors hover:bg-app-accent-hover disabled:opacity-60"
        >
          {fetching ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <Search size={14} />
          )}
          {fetching
            ? t('ai.patentAnalysis.fetching')
            : t('ai.patentAnalysis.fetch')}
        </button>
        {fetchError ? (
          <span
            role="alert"
            className="app-text-body-sm text-[var(--ui-color-danger)]"
          >
            {fetchError}
          </span>
        ) : null}
      </div>

      {/* Patent info bar */}
      {detail ? (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-app-border bg-app-surface-sidebar px-4 py-2 app-text-micro text-app-ink/80">
          <span className="app-text-body-sm font-semibold text-app-ink">
            {detail.title || detail.app_no}
          </span>
          {detail.applicant ? (
            <span>
              {t('ai.patentAnalysis.info.applicant')}: {detail.applicant}
            </span>
          ) : null}
          {detail.status ? (
            <span>
              {t('ai.patentAnalysis.info.status')}: {detail.status}
            </span>
          ) : null}
          {detail.app_no ? (
            <span>
              {t('ai.patentAnalysis.info.appNo')}: {detail.app_no}
            </span>
          ) : null}
          {detail.ipc ? <span>IPC: {detail.ipc}</span> : null}
          {detail.warning ? (
            <span className="text-app-warning-text dark:text-app-warning-text">
              {detail.warning}
            </span>
          ) : null}
          {hasPatent ? (
            <button
              type="button"
              onClick={() => void downloadReport()}
              disabled={reportBusy}
              title={t('ai.patentAnalysis.downloadReportHint')}
              className="app-text-micro ml-auto inline-flex shrink-0 items-center gap-1 rounded-md border border-app-border px-2.5 py-1 text-app-ink transition-colors hover:bg-app-surface-hover disabled:opacity-60"
            >
              {reportBusy ? (
                <Loader2 size={12} className="animate-spin" />
              ) : (
                <Download size={12} />
              )}
              {reportBusy
                ? t('ai.patentAnalysis.downloadReportBusy')
                : t('ai.patentAnalysis.downloadReport')}
            </button>
          ) : null}
        </div>
      ) : null}

      {/* Tab bar */}
      <div className="flex shrink-0 gap-1 overflow-x-auto border-b border-app-border px-4 py-2">
        {TAB_ORDER.map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => setTab(item)}
            className={cn(
              'app-text-control whitespace-nowrap rounded-md px-3 py-1.5 transition-colors',
              tab === item
                ? 'bg-app-accent text-app-accent-fg'
                : 'text-app-ink hover:bg-app-surface-hover',
            )}
          >
            <span aria-hidden="true">{TAB_EMOJI[item]}</span>{' '}
            {t(`ai.patentAnalysis.tabs.${item}`)}
          </button>
        ))}
      </div>

      {/* Main: history sidebar + tab content */}
      <div className="flex min-h-0 flex-1 overflow-hidden">
        <aside
          className={cn(
            'w-44 shrink-0 flex-col overflow-hidden border-r border-app-border bg-app-surface-sidebar',
            historyOpen ? 'hidden md:flex' : 'hidden',
          )}
        >
          <div className="flex items-center justify-between border-b border-app-border px-3 py-2">
            <span className="sidebar-section-label text-app-ink/55">
              <span aria-hidden="true">🕐</span>{' '}
              {t('ai.patentAnalysis.historyTitle')}
            </span>
            {history.length > 0 ? (
              <button
                type="button"
                onClick={clearAllHistory}
                title={t('ai.patentAnalysis.historyClear')}
                className="text-app-ink/55 transition-colors hover:text-app-accent"
              >
                <Trash2 size={12} />
              </button>
            ) : null}
          </div>
          <div className="min-h-0 flex-1 space-y-0.5 overflow-y-auto px-2 py-2">
            {history.length === 0 ? (
              <p className="px-1 py-2 text-center app-text-micro text-app-ink/55">
                {t('ai.patentAnalysis.historyEmpty')}
              </p>
            ) : (
              history.map((entry) => (
                <button
                  key={entry.number}
                  type="button"
                  onClick={() => {
                    setNumberInput(entry.number);
                    void fetchPatent(entry.number);
                  }}
                  className="flex w-full flex-col items-start rounded-md px-2 py-1.5 text-left transition-colors hover:bg-app-surface-hover"
                >
                  <span className="app-text-micro truncate text-app-ink">
                    {entry.title}
                  </span>
                  <span className="app-text-micro text-app-ink/55">
                    {entry.number}
                  </span>
                </button>
              ))
            )}
          </div>
        </aside>

        <section className="flex min-w-0 flex-1 flex-col overflow-hidden">
          {tab === 'claims' ? (
            <ClaimsTab
              detail={detail}
              hasPatent={hasPatent}
              busy={claimsBusy}
              result={claimsResult}
              error={tabError}
              onRun={() => void runClaims()}
            />
          ) : null}
          {tab === 'rights' ? (
            <RightsTab
              detail={detail}
              hasPatent={hasPatent}
              busy={rightsBusy}
              result={rightsResult}
              error={tabError}
              onRun={() => void runRights()}
            />
          ) : null}
          {tab === 'mapping' ? (
            <MappingTab
              detail={detail}
              hasPatent={hasPatent}
              busy={mappingBusy}
              result={mappingResult}
              error={tabError}
              onRun={() => void runMapping()}
            />
          ) : null}
          {tab === 'infringe' ? (
            <InfringeTab
              detail={detail}
              hasPatent={hasPatent}
              busy={infringeBusy}
              result={infringeResult}
              techInput={techInput}
              error={tabError}
              onTechInput={setTechInput}
              onRun={() => void runInfringe()}
            />
          ) : null}
        </section>
      </div>
    </div>
  );
}

// ── Shared pieces ─────────────────────────────────────────────────────────────
// Draggable left/right split width — shared across all analysis tabs and
// persisted so it survives tab switches and revisits.
const LEFT_WIDTH_KEY = 'open-alm.patent.analysis.leftWidth';
const LEFT_WIDTH_MIN = 220;
const RIGHT_WIDTH_MIN = 280;

function readStoredLeftWidth(): number | null {
  if (typeof window === 'undefined') return null;
  const value = Number(window.localStorage.getItem(LEFT_WIDTH_KEY));
  return Number.isFinite(value) && value >= LEFT_WIDTH_MIN ? value : null;
}

/**
 * Left "claims original" column + a draggable divider. Returned as a fragment so
 * the column and the handle sit as flex siblings of the tab's right panel. Width
 * is shared (localStorage) across the claims/rights/mapping/infringe tabs.
 */
function ClaimsColumn({ detail }: { detail: PatentDetail | null }) {
  const { t } = useTranslation('apps');
  const [width, setWidth] = useState<number | null>(readStoredLeftWidth);
  const colRef = useRef<HTMLDivElement | null>(null);

  const onResizeStart = useCallback(
    (event: ReactMouseEvent<HTMLDivElement>) => {
      event.preventDefault();
      const parent = colRef.current?.parentElement;
      if (!parent) return;
      const parentRect = parent.getBoundingClientRect();
      const maxWidth = Math.max(
        parentRect.width - RIGHT_WIDTH_MIN,
        LEFT_WIDTH_MIN,
      );

      const onMove = (moveEvent: MouseEvent) => {
        const next = Math.min(
          Math.max(moveEvent.clientX - parentRect.left, LEFT_WIDTH_MIN),
          maxWidth,
        );
        setWidth(next);
      };
      const onUp = () => {
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
        setWidth((current) => {
          if (current != null) {
            window.localStorage.setItem(
              LEFT_WIDTH_KEY,
              String(Math.round(current)),
            );
          }
          return current;
        });
      };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
    },
    [],
  );

  return (
    <>
      <div
        ref={colRef}
        style={{ width: width == null ? '50%' : width }}
        className="flex min-w-[200px] shrink-0 flex-col overflow-hidden border-r border-app-border"
      >
        <div className="flex h-11 shrink-0 items-center border-b border-app-border px-3 app-text-caption font-semibold text-app-ink">
          {t('ai.patentAnalysis.claimsOriginal')}
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          {detail && detail.claims.length > 0 ? (
            <ol className="space-y-2">
              {detail.claims.map((claim, index) => (
                <li
                  key={index}
                  className="whitespace-pre-wrap app-text-body-sm leading-relaxed text-app-ink/85"
                >
                  {claim}
                </li>
              ))}
            </ol>
          ) : (
            <p className="px-2 py-10 text-center app-text-body-sm text-app-ink/55">
              {t('ai.patentAnalysis.noPatent')}
            </p>
          )}
        </div>
      </div>
      <div
        role="separator"
        aria-orientation="vertical"
        onMouseDown={onResizeStart}
        title={t('ai.patentAnalysis.resizeHint')}
        className="w-1.5 shrink-0 cursor-col-resize bg-transparent transition-colors hover:bg-app-accent/40"
      />
    </>
  );
}

function AnalysisHeader({
  title,
  busy,
  disabled,
  onRun,
  label,
}: {
  title: string;
  busy: boolean;
  disabled: boolean;
  onRun: () => void;
  label: string;
}) {
  return (
    <div className="flex h-11 shrink-0 items-center justify-between border-b border-app-border px-3">
      <span className="app-text-caption font-semibold text-app-ink">
        {title}
      </span>
      <button
        type="button"
        onClick={onRun}
        disabled={busy || disabled}
        className="app-text-control inline-flex items-center gap-1 rounded-md bg-app-accent px-3 py-1 text-app-accent-fg transition-colors hover:bg-app-accent-hover disabled:opacity-60"
      >
        {busy ? <Loader2 size={12} className="animate-spin" /> : null}▶ {label}
      </button>
    </div>
  );
}

function AnalysisPlaceholder({
  busy,
  hasPatent,
}: {
  busy: boolean;
  hasPatent: boolean;
}) {
  const { t } = useTranslation('apps');
  if (busy) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-2 text-app-ink/55">
        <Loader2 size={20} className="animate-spin text-app-accent" />
        <p className="app-text-body-sm">
          {t('ai.patentAnalysis.generic.analyzing')}
        </p>
      </div>
    );
  }
  return (
    <p className="px-3 py-10 text-center app-text-body-sm text-app-ink/55">
      {hasPatent
        ? t('ai.patentAnalysis.analyzePrompt')
        : t('ai.patentAnalysis.generic.empty')}
    </p>
  );
}

function ClaimChip({ num, type }: { num: unknown; type?: string }) {
  const { t } = useTranslation('apps');
  return (
    <span className="inline-flex items-center gap-1">
      <span className="rounded-md bg-app-accent/10 px-1.5 py-0.5 app-text-micro font-semibold text-app-accent">
        {t('ai.patentAnalysis.claims.claimNum', { num: String(num ?? '') })}
      </span>
      {type ? (
        <span className="app-text-micro text-app-ink/55">{type}</span>
      ) : null}
    </span>
  );
}

// ── 청구항 설명 ──────────────────────────────────────────────────────────────
function ClaimsTab(props: {
  detail: PatentDetail | null;
  hasPatent: boolean;
  busy: boolean;
  result: ClaimsExplainResult | null;
  error: string | null;
  onRun: () => void;
}) {
  const { t } = useTranslation('apps');
  return (
    <div className="flex h-full overflow-hidden">
      <ClaimsColumn detail={props.detail} />
      <div className="flex min-w-[200px] flex-1 flex-col overflow-hidden">
        <AnalysisHeader
          title={t('ai.patentAnalysis.tabs.claims')}
          busy={props.busy}
          disabled={!props.hasPatent}
          onRun={props.onRun}
          label={t('ai.patentAnalysis.analyze')}
        />
        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          {props.error ? (
            <p
              role="alert"
              className="mb-3 app-text-body-sm text-[var(--ui-color-danger)]"
            >
              {props.error}
            </p>
          ) : null}
          {props.result ? (
            <div className="space-y-4">
              {props.result.summary ? (
                <Section title={t('ai.patentAnalysis.claims.summary')}>
                  <p className="app-text-body-sm text-app-ink/85">
                    {props.result.summary}
                  </p>
                </Section>
              ) : null}
              {props.result.key_features.length > 0 ? (
                <Section title={t('ai.patentAnalysis.claims.keyFeatures')}>
                  <ul className="list-disc space-y-1 pl-4 app-text-body-sm text-app-ink/85">
                    {props.result.key_features.map((feature, index) => (
                      <li key={index}>{feature}</li>
                    ))}
                  </ul>
                </Section>
              ) : null}
              {props.result.technical_significance ? (
                <Section title={t('ai.patentAnalysis.claims.significance')}>
                  <p className="app-text-body-sm text-app-ink/85">
                    {props.result.technical_significance}
                  </p>
                </Section>
              ) : null}
              {props.result.per_claim.length > 0 ? (
                <Section title={t('ai.patentAnalysis.claims.perClaim')}>
                  <div className="space-y-2">
                    {props.result.per_claim.map((claim, index) => (
                      <div
                        key={index}
                        className="rounded-md border border-app-border bg-app-surface p-2.5"
                      >
                        <ClaimChip
                          num={claim.claim_num}
                          type={str(claim, 'type')}
                        />
                        <p className="mt-1.5 app-text-body-sm text-app-ink/85">
                          {str(claim, 'explanation')}
                        </p>
                      </div>
                    ))}
                  </div>
                </Section>
              ) : null}
            </div>
          ) : (
            <AnalysisPlaceholder
              busy={props.busy}
              hasPatent={props.hasPatent}
            />
          )}
        </div>
      </div>
    </div>
  );
}

// ── 권리범위 분석 ────────────────────────────────────────────────────────────
function RightsTab(props: {
  detail: PatentDetail | null;
  hasPatent: boolean;
  busy: boolean;
  result: RightsScopeResult | null;
  error: string | null;
  onRun: () => void;
}) {
  const { t } = useTranslation('apps');
  return (
    <div className="flex h-full overflow-hidden">
      <ClaimsColumn detail={props.detail} />
      <div className="flex min-w-[200px] flex-1 flex-col overflow-hidden">
        <AnalysisHeader
          title={t('ai.patentAnalysis.tabs.rights')}
          busy={props.busy}
          disabled={!props.hasPatent}
          onRun={props.onRun}
          label={t('ai.patentAnalysis.analyze')}
        />
        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          {props.error ? (
            <p
              role="alert"
              className="mb-3 app-text-body-sm text-[var(--ui-color-danger)]"
            >
              {props.error}
            </p>
          ) : null}
          {props.result ? (
            <div className="space-y-4">
              {props.result.overall_analysis ? (
                <Section title={t('ai.patentAnalysis.rights.overall')}>
                  <p className="app-text-body-sm text-app-ink/85">
                    {props.result.overall_analysis}
                  </p>
                  {props.result.scope_breadth ? (
                    <p className="mt-1.5 app-text-caption text-app-ink/55">
                      {t('ai.patentAnalysis.rights.breadth')}:{' '}
                      {props.result.scope_breadth}
                    </p>
                  ) : null}
                </Section>
              ) : null}
              {props.result.key_elements.length > 0 ? (
                <Section title={t('ai.patentAnalysis.rights.keyElements')}>
                  <div className="flex flex-wrap gap-1.5">
                    {props.result.key_elements.map((element, index) => (
                      <span
                        key={index}
                        className="app-text-micro rounded-full border border-app-border px-2 py-0.5 text-app-ink/80"
                      >
                        {element}
                      </span>
                    ))}
                  </div>
                </Section>
              ) : null}
              {props.result.per_claim.length > 0 ? (
                <Section title={t('ai.patentAnalysis.rights.perClaim')}>
                  <div className="space-y-2">
                    {props.result.per_claim.map((claim, index) => (
                      <div
                        key={index}
                        className="rounded-md border border-app-border bg-app-surface p-2.5"
                      >
                        <div className="flex items-center justify-between">
                          <ClaimChip
                            num={claim.claim_num}
                            type={str(claim, 'type')}
                          />
                          {str(claim, 'breadth') ? (
                            <span className="app-text-micro text-app-ink/55">
                              {t('ai.patentAnalysis.rights.breadth')}:{' '}
                              {str(claim, 'breadth')}
                            </span>
                          ) : null}
                        </div>
                        {str(claim, 'scope_summary') ? (
                          <p className="mt-1.5 app-text-body-sm text-app-ink/85">
                            {str(claim, 'scope_summary')}
                          </p>
                        ) : null}
                        {strArray(claim, 'elements').length > 0 ? (
                          <div className="mt-1.5 flex flex-wrap gap-1">
                            {strArray(claim, 'elements').map(
                              (element, elementIndex) => (
                                <span
                                  key={elementIndex}
                                  className="app-text-micro text-app-ink/70"
                                >
                                  #{element}
                                </span>
                              ),
                            )}
                          </div>
                        ) : null}
                        {str(claim, 'notes') ? (
                          <p className="mt-1.5 app-text-micro text-app-ink/55">
                            {t('ai.patentAnalysis.rights.notes')}:{' '}
                            {str(claim, 'notes')}
                          </p>
                        ) : null}
                      </div>
                    ))}
                  </div>
                </Section>
              ) : null}
              {props.result.caution ? (
                <p className="app-text-micro text-app-warning-text dark:text-app-warning-text">
                  ※ {props.result.caution}
                </p>
              ) : null}
            </div>
          ) : (
            <AnalysisPlaceholder
              busy={props.busy}
              hasPatent={props.hasPatent}
            />
          )}
        </div>
      </div>
    </div>
  );
}

// ── 발명의설명 매핑 ──────────────────────────────────────────────────────────
function MappingTab(props: {
  detail: PatentDetail | null;
  hasPatent: boolean;
  busy: boolean;
  result: DescriptionMappingResult | null;
  error: string | null;
  onRun: () => void;
}) {
  const { t } = useTranslation('apps');
  return (
    <div className="flex h-full overflow-hidden">
      <ClaimsColumn detail={props.detail} />
      <div className="flex min-w-[200px] flex-1 flex-col overflow-hidden">
        <AnalysisHeader
          title={t('ai.patentAnalysis.tabs.mapping')}
          busy={props.busy}
          disabled={!props.hasPatent}
          onRun={props.onRun}
          label={t('ai.patentAnalysis.analyze')}
        />
        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          <p className="mb-3 app-text-caption text-app-ink/55">
            {t('ai.patentAnalysis.mapping.intro')}
          </p>
          {props.error ? (
            <p
              role="alert"
              className="mb-3 app-text-body-sm text-[var(--ui-color-danger)]"
            >
              {props.error}
            </p>
          ) : null}
          {props.result && props.result.mappings.length > 0 ? (
            <div className="space-y-3">
              {props.result.mappings.map((mapping, index) => (
                <div
                  key={index}
                  className="rounded-md border border-app-border bg-app-surface p-2.5"
                >
                  <ClaimChip num={mapping.claim_num} />
                  {str(mapping, 'claim_summary') ? (
                    <p className="mt-1.5 app-text-body-sm font-medium text-app-ink">
                      {str(mapping, 'claim_summary')}
                    </p>
                  ) : null}
                  <div className="mt-2 space-y-2">
                    {rowArray(mapping, 'elements').map(
                      (element, elementIndex) => (
                        <div
                          key={elementIndex}
                          className="rounded border border-app-border/60 bg-app-surface-sidebar p-2"
                        >
                          <p className="app-text-caption font-semibold text-app-ink">
                            {str(element, 'element')}
                          </p>
                          <p className="mt-1 whitespace-pre-wrap app-text-micro text-app-ink/75">
                            {str(element, 'mapped_text')}
                          </p>
                        </div>
                      ),
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <AnalysisPlaceholder
              busy={props.busy}
              hasPatent={props.hasPatent}
            />
          )}
        </div>
      </div>
    </div>
  );
}

// ── 침해 검토 ────────────────────────────────────────────────────────────────
const MATCH_STYLE: Record<string, string> = {
  yes: 'bg-[var(--ui-color-danger)]/10 text-[var(--ui-color-danger)]',
  partial: 'bg-app-warning/10 text-app-warning-text dark:text-app-warning-text',
  no: 'bg-app-success/10 text-app-success-text dark:text-app-success-text',
};

// verdict 문자열(침해 가능성 높음/중간/낮음/비침해)에 따른 색·아이콘.
// C:\server main.js 의 verdictMeta 와 동일한 색 체계를 따른다.
// 아래 토큰은 서버가 생성한 verdict 문자열을 파싱하기 위한 식별자이며 UI 카피가 아니다.
const VERDICT_TOKEN_HIGH = '높음';
const VERDICT_TOKEN_MID = '중간';
const VERDICT_TOKEN_LOW = '낮음';
const VERDICT_TOKEN_NONE = '비침해';
type VerdictMeta = { icon: string; text: string; box: string };
function infringeVerdictMeta(verdict: string): VerdictMeta {
  const s = verdict || '';
  if (s.includes(VERDICT_TOKEN_HIGH))
    return {
      icon: '🔴',
      text: 'text-[var(--ui-color-danger)]',
      box: 'border-[var(--ui-color-danger)] bg-[var(--ui-color-danger)]/10',
    };
  if (s.includes(VERDICT_TOKEN_MID))
    return {
      icon: '🟠',
      text: 'text-orange-600 dark:text-orange-400',
      box: 'border-orange-500 bg-orange-500/10',
    };
  if (s.includes(VERDICT_TOKEN_LOW))
    return {
      icon: '🟡',
      text: 'text-app-warning-text dark:text-app-warning-text',
      box: 'border-amber-500 bg-app-warning/10',
    };
  if (s.includes(VERDICT_TOKEN_NONE))
    return {
      icon: '🟢',
      text: 'text-app-success-text dark:text-app-success-text',
      box: 'border-emerald-500 bg-app-success/10',
    };
  return {
    icon: '⚪',
    text: 'text-app-ink/70',
    box: 'border-app-border bg-app-surface-sidebar',
  };
}

function InfringeTab(props: {
  detail: PatentDetail | null;
  hasPatent: boolean;
  busy: boolean;
  result: InfringeCheckResult | null;
  techInput: string;
  error: string | null;
  onTechInput: (value: string) => void;
  onRun: () => void;
}) {
  const { t } = useTranslation('apps');
  // 사내기술 설명 입력 접기/펼치기. 검토 결과가 나오면 자동으로 접어
  // 결과 시인성을 높이고, 토글로 다시 펼쳐 수정·재검토할 수 있게 한다.
  const [techCollapsed, setTechCollapsed] = useState(false);
  useEffect(() => {
    if (props.result) setTechCollapsed(true);
  }, [props.result]);
  return (
    <div className="flex h-full overflow-hidden">
      <ClaimsColumn detail={props.detail} />
      <div className="flex min-w-[240px] flex-1 flex-col overflow-hidden">
        <AnalysisHeader
          title={t('ai.patentAnalysis.infringe.title')}
          busy={props.busy}
          disabled={!props.hasPatent || !props.techInput.trim()}
          onRun={props.onRun}
          label={t('ai.patentAnalysis.infringe.run')}
        />
        <div className="flex shrink-0 flex-col gap-1.5 border-b border-app-border p-3">
          <div className="flex items-center justify-between gap-2">
            <span className="app-text-caption font-semibold text-app-ink">
              {t('ai.patentAnalysis.infringe.techLabel')}
            </span>
            <button
              type="button"
              onClick={() => setTechCollapsed((v) => !v)}
              className="app-text-micro inline-flex items-center gap-1 rounded border border-app-border px-1.5 py-0.5 text-app-ink/55 transition-colors hover:border-app-accent hover:text-app-accent"
            >
              <ChevronDown
                size={12}
                className={cn(
                  'transition-transform',
                  techCollapsed && '-rotate-90',
                )}
              />
              {techCollapsed
                ? t('ai.patentAnalysis.infringe.toggleExpand')
                : t('ai.patentAnalysis.infringe.toggleCollapse')}
            </button>
          </div>
          {!techCollapsed ? (
            <>
              <textarea
                value={props.techInput}
                onChange={(event) => props.onTechInput(event.target.value)}
                rows={10}
                placeholder={t('ai.patentAnalysis.infringe.techPlaceholder')}
                className="min-h-[64px] resize-y rounded-lg border border-app-border bg-app-surface-sidebar px-3 py-2 app-text-body-sm leading-relaxed text-app-ink outline-none focus:border-app-accent"
              />
              <span className="app-text-micro text-app-ink/55">
                {t('ai.patentAnalysis.infringe.disclaimer')}
              </span>
            </>
          ) : null}
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          {props.error ? (
            <p
              role="alert"
              className="mb-3 app-text-body-sm text-[var(--ui-color-danger)]"
            >
              {props.error}
            </p>
          ) : null}
          {props.result ? (
            <div className="space-y-4">
              {(() => {
                const meta = infringeVerdictMeta(props.result.overall_verdict);
                let total = 0;
                let yes = 0;
                let partial = 0;
                let no = 0;
                props.result.per_claim.forEach((claim) => {
                  rowArray(claim, 'elements').forEach((element) => {
                    total += 1;
                    const m = str(element, 'tech_match').toLowerCase();
                    if (m === 'yes') yes += 1;
                    else if (m === 'partial') partial += 1;
                    else if (m === 'no') no += 1;
                  });
                });
                return (
                  <div
                    className={cn('rounded-lg border-b-[3px] p-4', meta.box)}
                  >
                    <div className="flex items-center gap-3">
                      <span className="text-2xl leading-none">{meta.icon}</span>
                      <div>
                        <div className="app-text-micro font-semibold uppercase tracking-wide text-app-ink/55">
                          {t('ai.patentAnalysis.infringe.verdict')}
                        </div>
                        <div
                          className={cn(
                            'text-lg font-extrabold leading-tight',
                            meta.text,
                          )}
                        >
                          {props.result.overall_verdict}
                        </div>
                      </div>
                    </div>
                    {total > 0 ? (
                      <div className="mt-2.5 flex flex-wrap gap-1.5 app-text-micro font-bold">
                        <span className="rounded bg-[var(--ui-color-danger)] px-2 py-0.5 text-white">
                          {t('ai.patentAnalysis.infringe.countYes')} {yes}
                        </span>
                        <span className="rounded bg-orange-500 px-2 py-0.5 text-white">
                          {t('ai.patentAnalysis.infringe.countPartial')}{' '}
                          {partial}
                        </span>
                        <span className="rounded bg-app-success px-2 py-0.5 text-white">
                          {t('ai.patentAnalysis.infringe.countNo')} {no}
                        </span>
                        <span className="rounded border border-app-border bg-app-surface px-2 py-0.5 font-semibold text-app-ink/70">
                          {t('ai.patentAnalysis.infringe.countTotal')} {total}
                        </span>
                      </div>
                    ) : null}
                    {props.result.overall_summary ? (
                      <p className="mt-2.5 app-text-body-sm leading-relaxed text-app-ink/85">
                        {props.result.overall_summary}
                      </p>
                    ) : null}
                  </div>
                );
              })()}
              {props.result.per_claim.map((claim, index) => (
                <div
                  key={index}
                  className="rounded-md border border-app-border bg-app-surface p-2.5"
                >
                  <div className="flex items-center justify-between">
                    <ClaimChip
                      num={claim.claim_num}
                      type={str(claim, 'type')}
                    />
                    {str(claim, 'verdict') ? (
                      <span className="app-text-micro font-semibold text-app-ink">
                        {str(claim, 'verdict')}
                      </span>
                    ) : null}
                  </div>
                  {str(claim, 'summary') ? (
                    <p className="mt-1.5 app-text-body-sm text-app-ink/85">
                      {str(claim, 'summary')}
                    </p>
                  ) : null}
                  {rowArray(claim, 'elements').length > 0 ? (
                    <div className="mt-2 space-y-1.5">
                      {rowArray(claim, 'elements').map(
                        (element, elementIndex) => {
                          const match = str(
                            element,
                            'tech_match',
                          ).toLowerCase();
                          return (
                            <div
                              key={elementIndex}
                              className="rounded border border-app-border/60 bg-app-surface-sidebar p-2"
                            >
                              <div className="flex items-start justify-between gap-2">
                                <span className="app-text-caption font-medium text-app-ink">
                                  {str(element, 'element')}
                                </span>
                                <span
                                  className={cn(
                                    'app-text-micro shrink-0 rounded px-1.5 py-0.5 font-semibold',
                                    MATCH_STYLE[match] ??
                                      'bg-app-surface-hover text-app-ink/70',
                                  )}
                                >
                                  {t(
                                    `ai.patentAnalysis.infringe.match_${match}`,
                                    {
                                      defaultValue: str(element, 'tech_match'),
                                    },
                                  )}
                                </span>
                              </div>
                              {str(element, 'rationale') ? (
                                <p className="mt-1 app-text-micro text-app-ink/75">
                                  {str(element, 'rationale')}
                                </p>
                              ) : null}
                            </div>
                          );
                        },
                      )}
                    </div>
                  ) : null}
                </div>
              ))}
              {props.result.caution ? (
                <p className="app-text-micro text-app-warning-text dark:text-app-warning-text">
                  ※ {props.result.caution}
                </p>
              ) : null}
            </div>
          ) : (
            <p className="px-3 py-10 text-center app-text-body-sm text-app-ink/55">
              {props.busy
                ? t('ai.patentAnalysis.generic.analyzing')
                : t('ai.patentAnalysis.infringe.needTech')}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <p className="mb-1.5 app-text-caption font-semibold text-app-ink">
        {title}
      </p>
      {children}
    </div>
  );
}
