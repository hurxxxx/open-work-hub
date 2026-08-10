import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ChevronDown,
  Download,
  FileSpreadsheet,
  FileText,
  Loader2,
  RefreshCw,
} from 'lucide-react';
import { InlineNotice } from '@ai-do/ui';

import { useAuth } from '@/src/platform/auth/auth-provider';
import { useWorkspaceBootstrapContext } from '@/src/platform/workspaces/workspace-bootstrap-context';
import { resolveShellWorkspaceSlug } from '@/src/platform/workspaces/workspace-utils';
import { cn } from '@/src/lib/utils';
import {
  analyzeImds,
  generateImds,
  matchImdsMetadata,
  type ImdsAnalyzeResult,
  type ImdsGenerateMeta,
} from '../api/imds-minerals-api';

const TYPE_KEYS: Record<string, string> = {
  component: 'ai.imdsMinerals.types.component',
  product: 'ai.imdsMinerals.types.product',
  material: 'ai.imdsMinerals.types.material',
  chemical: 'ai.imdsMinerals.types.chemical',
};

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

function extractOemFromFilename(filename: string): string {
  const base = filename.replace(/\.[^.]+$/, '');
  return (base.split('_')[0] ?? '').trim();
}

export function ImdsMineralsView() {
  const { t } = useTranslation('apps');
  const { token, user } = useAuth();
  const workspaceBootstrap = useWorkspaceBootstrapContext();
  const workspaceSlug =
    workspaceBootstrap.data?.workspace.slug ??
    resolveShellWorkspaceSlug(user, null);

  const [pdf, setPdf] = useState<File | null>(null);
  const [analysis, setAnalysis] = useState<ImdsAnalyzeResult | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);

  const [template, setTemplate] = useState<File | null>(null);
  const [meta, setMeta] = useState<ImdsGenerateMeta>({
    sheet: '',
    car: '',
    endName: '',
    oem: '',
    dcc: '',
  });
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [generatedBlob, setGeneratedBlob] = useState<Blob | null>(null);

  const [listFile, setListFile] = useState<File | null>(null);
  const [matching, setMatching] = useState(false);
  const [matchMsg, setMatchMsg] = useState<{
    found: boolean;
    text: string;
  } | null>(null);
  const defaultSheet = t('ai.imdsMinerals.defaultSheet');

  const typeLabel = useCallback(
    (type: string) => (TYPE_KEYS[type] ? t(TYPE_KEYS[type]) : type),
    [t],
  );

  const runMatch = useCallback(
    async (pdfFile: File, list: File) => {
      if (!token) return;
      const oem = extractOemFromFilename(pdfFile.name);
      if (!oem) {
        setMatchMsg({ found: false, text: t('ai.imdsMinerals.match.noOem') });
        return;
      }
      setMatching(true);
      setMatchMsg(null);
      try {
        const result = await matchImdsMetadata({
          token,
          workspaceSlug,
          listFile: list,
          oem,
        });
        if (result.found) {
          setMeta((prev) => ({
            ...prev,
            car: result.car,
            endName: result.end_name,
            oem: result.oem,
            dcc: result.dcc,
            sheet: prev.sheet.trim() || defaultSheet,
          }));
          setMatchMsg({
            found: true,
            text: t('ai.imdsMinerals.match.matched', { oem }),
          });
        } else {
          setMeta((prev) => ({
            ...prev,
            oem,
            sheet: prev.sheet.trim() || defaultSheet,
          }));
          setMatchMsg({
            found: false,
            text: t('ai.imdsMinerals.match.notMatched', { oem }),
          });
        }
      } catch (err) {
        setMatchMsg({
          found: false,
          text: errorMessage(err, t('ai.imdsMinerals.errors.matchFailed')),
        });
      } finally {
        setMatching(false);
      }
    },
    [defaultSheet, t, token, workspaceSlug],
  );

  const handlePdf = useCallback(
    async (file: File | undefined | null) => {
      if (!file || !token) return;
      setPdf(file);
      setAnalysis(null);
      setAnalyzeError(null);
      setGeneratedBlob(null);
      setAnalyzing(true);
      if (listFile) void runMatch(file, listFile);
      try {
        const data = await analyzeImds({ token, workspaceSlug, file });
        setAnalysis(data);
      } catch (err) {
        setAnalyzeError(
          errorMessage(err, t('ai.imdsMinerals.errors.analyzeFailed')),
        );
      } finally {
        setAnalyzing(false);
      }
    },
    [listFile, runMatch, t, token, workspaceSlug],
  );

  const handleList = useCallback(
    (file: File | undefined | null) => {
      if (!file) return;
      setListFile(file);
      setGeneratedBlob(null);
      if (pdf) void runMatch(pdf, file);
    },
    [pdf, runMatch],
  );

  const formReady = useMemo(
    () =>
      Boolean(
        pdf &&
          template &&
          meta.sheet.trim() &&
          meta.car.trim() &&
          meta.endName.trim() &&
          meta.oem.trim() &&
          meta.dcc.trim(),
      ),
    [pdf, template, meta],
  );

  const handleGenerate = useCallback(async () => {
    if (!token || !pdf) {
      setGenerateError(t('ai.imdsMinerals.errors.needPdf'));
      return;
    }
    if (!template) {
      setGenerateError(t('ai.imdsMinerals.errors.needTemplate'));
      return;
    }
    if (!formReady) {
      setGenerateError(t('ai.imdsMinerals.errors.needFields'));
      return;
    }
    setGenerateError(null);
    setGenerating(true);
    setGeneratedBlob(null);
    try {
      const blob = await generateImds({
        token,
        workspaceSlug,
        pdf,
        template,
        meta,
      });
      setGeneratedBlob(blob);
    } catch (err) {
      setGenerateError(
        errorMessage(err, t('ai.imdsMinerals.errors.generateFailed')),
      );
    } finally {
      setGenerating(false);
    }
  }, [formReady, meta, pdf, t, template, token, workspaceSlug]);

  const handleDownload = useCallback(() => {
    if (!generatedBlob) return;
    const url = URL.createObjectURL(generatedBlob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'IMDS_responsible_minerals.xlsx';
    link.click();
    URL.revokeObjectURL(url);
  }, [generatedBlob]);

  const updateMeta = useCallback((patch: Partial<ImdsGenerateMeta>) => {
    setMeta((prev) => ({ ...prev, ...patch }));
    setGeneratedBlob(null);
  }, []);

  const handleTemplate = useCallback((file: File | undefined | null) => {
    setTemplate(file ?? null);
    setGeneratedBlob(null);
  }, []);

  const reset = useCallback(() => {
    setPdf(null);
    setAnalysis(null);
    setAnalyzeError(null);
    setTemplate(null);
    setGenerateError(null);
    setMeta({ sheet: '', car: '', endName: '', oem: '', dcc: '' });
    setListFile(null);
    setMatching(false);
    setMatchMsg(null);
    setGeneratedBlob(null);
  }, []);

  return (
    <div className="flex min-h-screen flex-col gap-6 bg-app-bg p-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="app-text-title-md font-semibold text-app-ink">
            {t('ai.imdsMinerals.title')}
          </h1>
          <p className="mt-1 app-text-body text-app-ink/60">
            {t('ai.imdsMinerals.subtitle')}
          </p>
        </div>
        <button
          type="button"
          onClick={reset}
          className="inline-flex items-center gap-2 rounded-md border border-app-border px-3 py-2 app-text-body text-app-ink/70 transition hover:bg-app-surface-hover"
        >
          <RefreshCw className="size-4" />
          {t('ai.imdsMinerals.reset')}
        </button>
      </header>

      <section className="flex flex-col gap-4 rounded-lg border border-app-border bg-app-surface p-5">
        <h2 className="app-text-title-sm font-semibold text-app-ink">
          {t('ai.imdsMinerals.analyze.uploadTitle')}
        </h2>
        <label
          htmlFor="imds-pdf-file"
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault();
            void handlePdf(event.dataTransfer.files?.[0]);
          }}
          className="flex w-full cursor-pointer flex-col items-center rounded-lg border border-dashed border-app-border bg-app-bg p-8 text-center transition hover:border-app-ink/40"
        >
          <FileText className="size-9 text-app-ink/50" />
          <p className="mt-3 app-text-body text-app-ink/70">
            {pdf ? pdf.name : t('ai.imdsMinerals.analyze.uploadHint')}
          </p>
          <span className="mt-4 inline-flex items-center gap-2 rounded-md bg-app-accent px-4 py-2 app-text-body font-semibold text-app-accent-fg">
            {t('ai.imdsMinerals.analyze.choose')}
          </span>
          <input
            id="imds-pdf-file"
            type="file"
            accept=".pdf"
            className="sr-only"
            onChange={(event) => void handlePdf(event.target.files?.[0])}
          />
        </label>

        {analyzing ? (
          <div className="flex items-center gap-2 app-text-body text-app-ink/60">
            <Loader2 className="size-4 animate-spin" />
            {t('ai.imdsMinerals.analyze.loading')}
          </div>
        ) : null}

        {analyzeError ? (
          <InlineNotice tone="danger">{analyzeError}</InlineNotice>
        ) : null}

        {analysis ? (
          <AnalysisSummary analysis={analysis} typeLabel={typeLabel} />
        ) : null}
      </section>

      <section className="flex flex-col gap-4 rounded-lg border border-app-border bg-app-surface p-5">
        <h2 className="app-text-title-sm font-semibold text-app-ink">
          {t('ai.imdsMinerals.generate.title')}
        </h2>
        <p className="app-text-body text-app-ink/60">
          {t('ai.imdsMinerals.generate.hint')}
        </p>

        <label
          htmlFor="imds-list-file"
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault();
            handleList(event.dataTransfer.files?.[0]);
          }}
          className="flex cursor-pointer items-center gap-3 rounded-md border border-dashed border-app-border bg-app-bg px-4 py-3 transition hover:border-app-ink/40"
        >
          <FileSpreadsheet className="size-5 text-app-ink/50" />
          <span className="app-text-body text-app-ink/70">
            {listFile ? listFile.name : t('ai.imdsMinerals.form.listChoose')}
          </span>
        </label>
        <input
          id="imds-list-file"
          type="file"
          accept=".xlsx,.xlsm"
          className="sr-only"
          onChange={(event) => handleList(event.target.files?.[0])}
        />

        {matching ? (
          <div className="flex items-center gap-2 app-text-caption text-app-ink/60">
            <Loader2 className="size-4 animate-spin" />
            {t('ai.imdsMinerals.match.matching')}
          </div>
        ) : null}
        {matchMsg ? (
          <InlineNotice tone={matchMsg.found ? 'success' : 'warning'}>
            {matchMsg.text}
          </InlineNotice>
        ) : null}

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <MetaField
            label={t('ai.imdsMinerals.form.car')}
            value={meta.car}
            onChange={(value) => updateMeta({ car: value })}
          />
          <MetaField
            label={t('ai.imdsMinerals.form.endName')}
            value={meta.endName}
            onChange={(value) => updateMeta({ endName: value })}
          />
          <MetaField
            label={t('ai.imdsMinerals.form.oem')}
            value={meta.oem}
            onChange={(value) => updateMeta({ oem: value })}
          />
          <MetaField
            label={t('ai.imdsMinerals.form.dcc')}
            value={meta.dcc}
            onChange={(value) => updateMeta({ dcc: value })}
          />
          <MetaField
            label={t('ai.imdsMinerals.form.sheet')}
            value={meta.sheet}
            onChange={(value) => updateMeta({ sheet: value })}
          />
        </div>

        <label
          htmlFor="imds-template-file"
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault();
            handleTemplate(event.dataTransfer.files?.[0]);
          }}
          className="flex cursor-pointer items-center gap-3 rounded-md border border-dashed border-app-border bg-app-bg px-4 py-3 transition hover:border-app-ink/40"
        >
          <FileSpreadsheet className="size-5 text-app-ink/50" />
          <span className="app-text-body text-app-ink/70">
            {template
              ? template.name
              : t('ai.imdsMinerals.form.templateChoose')}
          </span>
          <input
            id="imds-template-file"
            type="file"
            accept=".xlsx,.xlsm"
            className="sr-only"
            onChange={(event) => handleTemplate(event.target.files?.[0])}
          />
        </label>

        {generateError ? (
          <InlineNotice tone="danger">{generateError}</InlineNotice>
        ) : null}

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => void handleGenerate()}
            disabled={generating || !formReady}
            className={cn(
              'inline-flex w-fit items-center gap-2 rounded-md bg-app-accent px-5 py-2.5 app-text-body font-semibold text-app-accent-fg transition',
              (generating || !formReady) && 'cursor-not-allowed opacity-50',
            )}
          >
            {generating ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <FileSpreadsheet className="size-4" />
            )}
            {generating
              ? t('ai.imdsMinerals.form.generating')
              : t('ai.imdsMinerals.form.submit')}
          </button>

          {generatedBlob && !generating ? (
            <button
              type="button"
              onClick={handleDownload}
              className="inline-flex w-fit items-center gap-2 rounded-md bg-app-accent px-5 py-2.5 app-text-body font-semibold text-app-accent-fg transition"
            >
              <Download className="size-4" />
              {t('ai.imdsMinerals.form.download')}
            </button>
          ) : null}
        </div>

        {generatedBlob && !generating ? (
          <InlineNotice tone="success">
            {t('ai.imdsMinerals.form.generated')}
          </InlineNotice>
        ) : null}
      </section>
    </div>
  );
}

function AnalysisSummary({
  analysis,
  typeLabel,
}: {
  analysis: ImdsAnalyzeResult;
  typeLabel: (type: string) => string;
}) {
  const { t } = useTranslation('apps');
  const [previewOpen, setPreviewOpen] = useState(true);
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-3">
        <StatChip
          label={t('ai.imdsMinerals.stats.totalRows')}
          value={analysis.total_rows}
        />
        <StatChip
          label={t('ai.imdsMinerals.stats.relevant')}
          value={analysis.relevant_count}
        />
        {Object.entries(analysis.classification).map(([type, count]) => (
          <StatChip key={type} label={typeLabel(type)} value={count} />
        ))}
      </div>
      <p className="app-text-caption text-app-ink/50">
        {t('ai.imdsMinerals.stats.help')}
      </p>

      <div>
        <h3 className="app-text-label font-semibold text-app-ink/80">
          {t('ai.imdsMinerals.minerals.title')}
        </h3>
        {analysis.mineral_counts.length === 0 ? (
          <p className="mt-1 app-text-body text-app-ink/50">
            {t('ai.imdsMinerals.minerals.empty')}
          </p>
        ) : (
          <div className="mt-2 flex flex-wrap gap-2">
            {analysis.mineral_counts.map((item) => (
              <span
                key={item.mineral}
                className="inline-flex items-center gap-1 rounded-full bg-app-bg px-3 py-1 app-text-caption text-app-ink/70"
              >
                {item.mineral}
                <span className="font-semibold text-app-ink">{item.count}</span>
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="overflow-x-auto">
        <button
          type="button"
          onClick={() => setPreviewOpen((open) => !open)}
          aria-expanded={previewOpen}
          className="flex items-center gap-1.5 app-text-label font-semibold text-app-ink/80 transition-colors hover:text-app-ink"
        >
          <ChevronDown
            className={cn(
              'size-4 transition-transform',
              !previewOpen && '-rotate-90',
            )}
          />
          {t('ai.imdsMinerals.preview.title')}
        </button>
        {previewOpen && analysis.rows.length < analysis.relevant_count ? (
          <p className="mt-1 app-text-caption text-app-ink/50">
            {t('ai.imdsMinerals.preview.truncated', {
              shown: analysis.rows.length,
              total: analysis.relevant_count,
            })}
          </p>
        ) : null}
        {previewOpen ? (
          analysis.rows.length === 0 ? (
            <p className="mt-1 app-text-body text-app-ink/50">
              {t('ai.imdsMinerals.preview.empty')}
            </p>
          ) : (
            <table className="mt-2 min-w-full app-text-caption">
              <thead>
                <tr className="text-left text-app-ink/50">
                  <th className="px-2 py-1">
                    {t('ai.imdsMinerals.preview.level')}
                  </th>
                  <th className="px-2 py-1">
                    {t('ai.imdsMinerals.preview.name')}
                  </th>
                  <th className="px-2 py-1">
                    {t('ai.imdsMinerals.preview.code')}
                  </th>
                  <th className="px-2 py-1">
                    {t('ai.imdsMinerals.preview.type')}
                  </th>
                  <th className="px-2 py-1">
                    {t('ai.imdsMinerals.preview.mineral')}
                  </th>
                </tr>
              </thead>
              <tbody>
                {analysis.rows.map((row, index) => (
                  <tr
                    key={`${row.level}-${row.name}-${index}`}
                    className="border-t border-app-border"
                  >
                    <td className="px-2 py-1 text-app-ink/70">{row.level}</td>
                    <td className="px-2 py-1 text-app-ink">{row.name}</td>
                    <td className="px-2 py-1 text-app-ink/70">{row.code}</td>
                    <td className="px-2 py-1 text-app-ink/70">
                      {typeLabel(row.type)}
                    </td>
                    <td className="px-2 py-1 font-medium text-app-ink">
                      {row.mineral}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        ) : null}
      </div>
    </div>
  );
}

function StatChip({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg bg-app-bg px-4 py-2">
      <div className="app-text-caption text-app-ink/50">{label}</div>
      <div className="app-text-title-sm font-semibold text-app-ink">
        {value}
      </div>
    </div>
  );
}

function MetaField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="app-text-caption text-app-ink/60">{label}</span>
      <input
        type="text"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="rounded-md border border-app-border bg-app-bg px-3 py-2 app-text-body text-app-ink outline-none focus:border-app-accent"
      />
    </label>
  );
}
