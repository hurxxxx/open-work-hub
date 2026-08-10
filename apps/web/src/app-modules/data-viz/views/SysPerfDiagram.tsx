import { useCallback, useEffect, useMemo, useState } from 'react';
import Plot from 'react-plotly.js';
import { Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { EmptyState, InlineNotice, Select } from '@open-alm/ui';

import { cn } from '@/src/lib/utils';
import {
  type SysPerfUploadedFile,
  type SysPerfPhDiagram,
  type SysPerfTsDiagram,
  type SysPerfRefrigerantPropRow,
} from '../api/dataviz-api';
import {
  SYS_PERF_TS_AXIS_DEFAULTS,
  buildDiagramTableRows,
  buildMatchWarnings,
  buildPhPlotModel,
  buildTsPlotModel,
  type SysPerfDiagramCycleCacheEntry,
  type SysPerfTsAxis,
} from './sysperf-diagram';
import {
  SYS_PERF_DIAGRAM_DEFAULT_TIME,
  buildSysPerfDiagramBulkTimes,
  canApplySysPerfDiagramTsAxis,
  getSysPerfDiagramBrowserStorage,
  loadSysPerfDiagramBulkTime,
  loadSysPerfDiagramTimes,
  loadSysPerfDiagramTsAxis,
  saveSysPerfDiagramTime,
  saveSysPerfDiagramTsAxis,
  updateSysPerfDiagramTsAxisDraft,
} from './sysperf-diagram-session';
import {
  loadSysPerfDiagramRefrigerants,
  loadSysPerfDiagramRun,
} from './sysperf-diagram-loader';
import { SYSPERF_DIAGRAM_TABLE_COLORS } from './data-viz-colors';
import { isUsableSysPerfUploadedFile } from './sysperf-files';
import { useSysPerfWorkspace } from './sysperf-workspace';

// 원본 sys_perf.js ⑥ — drawPHDiagram + _renderPHBackgroundPlot + interpolateEnthalpy 이식.
// 클라이언트 Plotly 렌더: kgf/cm² log축, 등건도/등온/등엔트로피/등비체적 isoline, 사이클 1~8 폐곡선.

const PCFG = { responsive: true, displayModeBar: false } as const;
const DEFAULT_REFRIGERANTS = [
  { id: 0, name: 'R-134a' },
  { id: 0, name: 'R-1234yf' },
  { id: 0, name: 'R-744' },
  { id: 0, name: 'R-410A' },
  { id: 0, name: 'R-32' },
];
type CacheEntry = SysPerfDiagramCycleCacheEntry;

export function SysPerfDiagram({ files }: { files: SysPerfUploadedFile[] }) {
  const { t } = useTranslation('apps');
  const { token, workspaceSlug } = useSysPerfWorkspace();
  const validFiles = useMemo(
    () => files.filter(isUsableSysPerfUploadedFile),
    [files],
  );

  const [refrigerants, setRefrigerants] =
    useState<{ id: number; name: string }[]>(DEFAULT_REFRIGERANTS);
  const [refrigerant, setRefrigerant] = useState<string>('R-134a');
  const [mode, setMode] = useState<'ph' | 'ts'>('ph');
  const [activeFidx, setActiveFidx] = useState(0);
  const [times, setTimes] = useState<Record<number, string>>({});
  const [bulkTime, setBulkTime] = useState<string>(
    SYS_PERF_DIAGRAM_DEFAULT_TIME,
  );
  const [cache, setCache] = useState<Record<number, CacheEntry>>({});
  const [props, setProps] = useState<SysPerfRefrigerantPropRow[]>([]);
  const [ph, setPh] = useState<SysPerfPhDiagram | null>(null);
  const [ts, setTs] = useState<SysPerfTsDiagram | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [tsAx, setTsAx] = useState<SysPerfTsAxis>(SYS_PERF_TS_AXIS_DEFAULTS); // 입력값(draft)
  const [tsAxApplied, setTsAxApplied] = useState<SysPerfTsAxis>(
    SYS_PERF_TS_AXIS_DEFAULTS,
  ); // 차트 반영값

  useEffect(() => {
    const a = loadSysPerfDiagramTsAxis(getSysPerfDiagramBrowserStorage());
    setTsAx(a);
    setTsAxApplied(a);
  }, []);

  useEffect(() => {
    if (!token || !workspaceSlug) return;
    void loadSysPerfDiagramRefrigerants({ token, workspaceSlug })
      .then((list) => {
        if (list.length) {
          setRefrigerants(list);
          setRefrigerant((cur) =>
            list.some((r) => r.name === cur) ? cur : list[0].name,
          );
        }
      })
      .catch(() => undefined);
  }, [token, workspaceSlug]);

  useEffect(() => {
    const storage = getSysPerfDiagramBrowserStorage();
    setTimes(
      loadSysPerfDiagramTimes({
        storage,
        fileCount: validFiles.length,
      }),
    );
    setActiveFidx(0);
    setBulkTime(loadSysPerfDiagramBulkTime(storage));
  }, [validFiles]);

  const setTime = (fidx: number, v: string) => {
    setTimes((p) => ({ ...p, [fidx]: v }));
    saveSysPerfDiagramTime(getSysPerfDiagramBrowserStorage(), fidx, v);
  };
  const applyBulk = () => {
    const nextTimes = buildSysPerfDiagramBulkTimes({
      storage: getSysPerfDiagramBrowserStorage(),
      fileCount: validFiles.length,
      value: bulkTime,
    });
    if (!nextTimes) return;
    setTimes(nextTimes);
  };

  // 선도 그리기 — 모든 파일 cycle-data + props + 배경(ph/ts)
  const draw = useCallback(async () => {
    if (!token || !workspaceSlug || !validFiles.length) return;
    setBusy(true);
    setErr(null);
    try {
      const result = await loadSysPerfDiagramRun({
        token,
        workspaceSlug,
        files: validFiles,
        times,
        refrigerant,
        refrigerants,
      });
      setProps(result.props);
      setCache(result.cache);
      setPh(result.ph);
      setTs(result.ts);
      if (result.cycleError !== undefined) {
        setErr(
          result.cycleError || t('ai.dataViz.sysPerf.diagram.cycleFailed'),
        );
      }
    } catch (e) {
      setErr(
        e instanceof Error
          ? e.message
          : t('ai.dataViz.sysPerf.diagram.loadFailed'),
      );
    } finally {
      setBusy(false);
    }
  }, [token, workspaceSlug, validFiles, times, refrigerant, refrigerants, t]);

  const cached = cache[activeFidx];

  const applyTsAx = () => {
    if (!canApplySysPerfDiagramTsAxis(tsAx)) return;
    setTsAxApplied(tsAx);
    saveSysPerfDiagramTsAxis(getSysPerfDiagramBrowserStorage(), tsAx);
  };
  const resetTsAx = () => {
    setTsAx(SYS_PERF_TS_AXIS_DEFAULTS);
    setTsAxApplied(SYS_PERF_TS_AXIS_DEFAULTS);
    saveSysPerfDiagramTsAxis(
      getSysPerfDiagramBrowserStorage(),
      SYS_PERF_TS_AXIS_DEFAULTS,
    );
  };

  // 8행 표
  const tableRows = useMemo(
    () =>
      buildDiagramTableRows({
        cached,
        props,
        fallbackNote: ({ expected, actual }) =>
          t('ai.dataViz.sysPerf.diagram.fallbackNote', { expected, actual }),
        txvIsenthalpic: t('ai.dataViz.sysPerf.diagram.txvIsenthalpic'),
        hvacInherits: t('ai.dataViz.sysPerf.diagram.hvacInherits'),
      }),
    [cached, props, t],
  );

  // 매칭 오류 감지 (Comp In P >= Comp Out P × 0.9)
  const matchWarnings = useMemo(
    () =>
      buildMatchWarnings({
        fileCount: validFiles.length,
        cache,
        formatWarning: ({ index, inPressure, outPressure }) =>
          t('ai.dataViz.sysPerf.diagram.compPressureWarning', {
            index,
            inPressure,
            outPressure,
          }),
      }),
    [cache, validFiles.length, t],
  );

  const plotLabels = useMemo(
    () => ({
      saturationCurve: t('ai.dataViz.sysPerf.diagram.saturationCurve'),
      criticalPoint: t('ai.dataViz.sysPerf.diagram.criticalPoint'),
      cycleFileName: ({ index, time }: { index: number; time: number }) =>
        t('ai.dataViz.sysPerf.diagram.cycleFileName', {
          index,
          time: time.toFixed(1),
        }),
      axes: {
        enthalpy: t('ai.dataViz.sysPerf.diagram.axes.enthalpy'),
        pressure: t('ai.dataViz.sysPerf.diagram.axes.pressure'),
        entropy: t('ai.dataViz.sysPerf.diagram.axes.entropy'),
        temperature: t('ai.dataViz.sysPerf.diagram.axes.temperature'),
      },
      phTitle: ({ refrigerant: titleRefrigerant }: { refrigerant: string }) =>
        t('ai.dataViz.sysPerf.diagram.phTitle', {
          refrigerant: titleRefrigerant,
        }),
      tsTitle: ({ refrigerant: titleRefrigerant }: { refrigerant: string }) =>
        t('ai.dataViz.sysPerf.diagram.tsTitle', {
          refrigerant: titleRefrigerant,
        }),
    }),
    [t],
  );

  // ── P-H 플롯 (원본 _renderPHBackgroundPlot z-순서·색·축) ──
  const phPlot = useMemo(
    () =>
      buildPhPlotModel({
        ph,
        cache,
        fileCount: validFiles.length,
        props,
        refrigerant,
        labels: plotLabels,
      }),
    [ph, cache, validFiles.length, props, refrigerant, plotLabels],
  );

  // ── T-S 플롯 (원본 drawTSDiagram z-순서·색·축) ──
  const tsPlot = useMemo(
    () =>
      buildTsPlotModel({
        ts,
        cache,
        fileCount: validFiles.length,
        props,
        refrigerant,
        axis: tsAxApplied,
        labels: plotLabels,
      }),
    [ts, cache, validFiles.length, props, refrigerant, tsAxApplied, plotLabels],
  );

  if (!validFiles.length)
    return <EmptyState title={t('ai.dataViz.sysPerf.diagram.emptyUpload')} />;

  const active = mode === 'ph' ? phPlot : tsPlot;

  return (
    <div className="flex flex-col gap-3">
      {/* 컨트롤 바 */}
      <div className="flex flex-wrap items-end gap-3 rounded-2xl border border-app-border bg-app-surface p-4">
        <label className="flex flex-col gap-1">
          <span className="app-text-caption text-app-ink/65">
            {t('ai.dataViz.sysPerf.diagram.refrigerant')}
          </span>
          <Select
            value={refrigerant}
            onValueChange={setRefrigerant}
            options={refrigerants.map((r) => ({
              value: r.name,
              label: r.name,
            }))}
            className="min-w-[140px]"
          />
        </label>
        <div className="flex gap-1.5">
          {(['ph', 'ts'] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMode(m)}
              className={cn(
                'app-text-control-sm rounded-md border px-3 py-1.5 transition-colors',
                mode === m
                  ? 'border-app-accent bg-app-accent/10 text-app-accent'
                  : 'border-app-border text-app-ink/65 hover:bg-app-surface-hover',
              )}
            >
              {m === 'ph'
                ? t('ai.dataViz.sysPerf.diagram.mode.ph')
                : t('ai.dataViz.sysPerf.diagram.mode.ts')}
            </button>
          ))}
        </div>
        <button
          type="button"
          disabled={busy}
          onClick={() => void draw()}
          className="app-text-control-sm inline-flex items-center gap-1.5 rounded-md bg-app-accent px-4 py-2 font-semibold text-app-accent-fg transition-colors hover:bg-app-accent-hover disabled:opacity-60"
        >
          {busy ? <Loader2 size={14} className="animate-spin" /> : null}
          {t('ai.dataViz.sysPerf.diagram.drawAction')}
        </button>
        {ph && !ph.has_coolprop ? (
          <InlineNotice tone="info">
            {t('ai.dataViz.sysPerf.diagram.coolPropFallback')}
          </InlineNotice>
        ) : null}
      </div>

      {/* 상단 바: 파일 탭 + 시각 + 일괄 */}
      <div className="rounded-2xl border border-app-border bg-app-surface-raised p-3">
        {validFiles.length > 1 ? (
          <div className="mb-2.5 flex flex-wrap gap-1.5">
            {validFiles.map((f, i) => (
              <button
                key={f.file_id}
                type="button"
                title={f.filename}
                onClick={() => setActiveFidx(i)}
                className={cn(
                  'app-text-control-sm rounded-md border px-3 py-1.5 font-semibold transition-colors',
                  activeFidx === i
                    ? 'border-app-accent bg-app-accent/10 text-app-accent'
                    : 'border-app-border text-app-ink/65 hover:bg-app-surface-hover',
                )}
              >
                {t('ai.dataViz.sysPerf.diagram.fileLabel', { index: i + 1 })}
              </button>
            ))}
          </div>
        ) : null}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="app-text-caption font-bold text-app-ink/75">
              {t('ai.dataViz.sysPerf.diagram.timeInput')}
            </span>
            <input
              type="number"
              step="0.1"
              min="0"
              value={times[activeFidx] ?? SYS_PERF_DIAGRAM_DEFAULT_TIME}
              onChange={(e) => setTime(activeFidx, e.target.value)}
              className="w-24 rounded border border-app-border bg-app-bg px-2 py-1 text-center tabular-nums outline-none focus:border-app-accent app-text-body-sm"
            />
            <span className="app-text-caption text-app-ink/45">
              (
              {(validFiles[activeFidx] || validFiles[0]).filename.substring(
                0,
                24,
              )}
              )
            </span>
          </div>
          {validFiles.length >= 2 ? (
            <div className="flex items-center gap-2 border-l border-app-border pl-3">
              <span className="app-text-caption font-bold text-app-ink/75">
                {t('ai.dataViz.sysPerf.diagram.bulkTimeInput')}
              </span>
              <input
                type="number"
                step="0.1"
                min="0"
                value={bulkTime}
                onChange={(e) => setBulkTime(e.target.value)}
                className="w-24 rounded border border-app-accent bg-app-bg px-2 py-1 text-center font-semibold tabular-nums outline-none app-text-body-sm"
              />
              <button
                type="button"
                onClick={applyBulk}
                title={t('ai.dataViz.sysPerf.diagram.applyBulkTitle')}
                className="app-text-control-sm rounded-md bg-app-accent px-3 py-1.5 font-bold text-app-accent-fg transition-colors hover:bg-app-accent-hover"
              >
                {t('ai.dataViz.sysPerf.diagram.applyBulkAction')}
              </button>
            </div>
          ) : null}
        </div>
      </div>

      {err ? (
        <InlineNotice tone="warning">
          {t('ai.dataViz.sysPerf.diagram.errorWithMatchHint', { error: err })}
        </InlineNotice>
      ) : null}
      {matchWarnings.length ? (
        <InlineNotice tone="danger">
          {t('ai.dataViz.sysPerf.diagram.matchWarningNotice', {
            warnings: matchWarnings.join(' / '),
          })}
        </InlineNotice>
      ) : null}

      {/* 8행 데이터 정리 표 */}
      <div className="rounded-2xl border border-app-border bg-app-surface p-4">
        <div className="app-text-body font-bold text-app-ink">
          {t('ai.dataViz.sysPerf.diagram.tableTitle')}
          {cached?.time != null ? (
            <span className="app-text-caption ml-2 font-normal text-app-ink/55">
              {t('ai.dataViz.sysPerf.diagram.tableSubtitle', {
                index: activeFidx + 1,
                time: cached.time.toFixed(1),
              })}
            </span>
          ) : null}
        </div>
        <div className="custom-scrollbar mt-2 overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr
                style={{
                  background: SYSPERF_DIAGRAM_TABLE_COLORS.headerBg,
                  color: SYSPERF_DIAGRAM_TABLE_COLORS.white,
                }}
              >
                {[
                  'no',
                  'item',
                  'pressure',
                  'temperature',
                  'enthalpy',
                  'note',
                ].map((th) => (
                  <th
                    key={th}
                    className="app-text-caption whitespace-nowrap px-3 py-2 font-bold"
                    style={{
                      border: SYSPERF_DIAGRAM_TABLE_COLORS.headerBorder,
                    }}
                  >
                    {t(`ai.dataViz.sysPerf.diagram.tableHeaders.${th}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {tableRows.map((r) => (
                <tr key={r.no}>
                  <td
                    className="app-text-body-sm px-3 py-1.5 text-center font-bold"
                    style={{
                      border: SYSPERF_DIAGRAM_TABLE_COLORS.cellBorder,
                    }}
                  >
                    {r.no}
                  </td>
                  <td
                    className="app-text-body-sm px-3 py-1.5 text-center font-bold"
                    style={{
                      border: SYSPERF_DIAGRAM_TABLE_COLORS.cellBorder,
                    }}
                  >
                    {r.label}
                  </td>
                  <td
                    className="app-text-body-sm px-3 py-1.5 text-right font-semibold tabular-nums"
                    style={{
                      border: SYSPERF_DIAGRAM_TABLE_COLORS.cellBorder,
                      color: SYSPERF_DIAGRAM_TABLE_COLORS.pressure,
                    }}
                  >
                    {r.p}
                  </td>
                  <td
                    className="app-text-body-sm px-3 py-1.5 text-right font-semibold tabular-nums"
                    style={{
                      border: SYSPERF_DIAGRAM_TABLE_COLORS.cellBorder,
                      color: SYSPERF_DIAGRAM_TABLE_COLORS.temperature,
                    }}
                  >
                    {r.t}
                  </td>
                  <td
                    className="app-text-body-sm px-3 py-1.5 text-right font-semibold tabular-nums"
                    style={{
                      border: SYSPERF_DIAGRAM_TABLE_COLORS.cellBorder,
                      color: SYSPERF_DIAGRAM_TABLE_COLORS.enthalpy,
                    }}
                  >
                    {r.h}
                    {r.sh ? (
                      <div
                        className="app-text-caption font-semibold"
                        style={{
                          color: SYSPERF_DIAGRAM_TABLE_COLORS.superheat,
                        }}
                      >
                        {t('ai.dataViz.sysPerf.diagram.superheatValue', {
                          value: r.sh,
                        })}
                      </div>
                    ) : null}
                    {r.sc ? (
                      <div
                        className="app-text-caption font-semibold"
                        style={{
                          color: SYSPERF_DIAGRAM_TABLE_COLORS.pressure,
                        }}
                      >
                        {t('ai.dataViz.sysPerf.diagram.subcoolValue', {
                          value: r.sc,
                        })}
                      </div>
                    ) : null}
                  </td>
                  <td
                    className="app-text-caption px-3 py-1.5"
                    style={{
                      border: SYSPERF_DIAGRAM_TABLE_COLORS.cellBorder,
                      background: r.notes.length
                        ? SYSPERF_DIAGRAM_TABLE_COLORS.noteBg
                        : '',
                      color: r.notes.length
                        ? SYSPERF_DIAGRAM_TABLE_COLORS.noteText
                        : '',
                      lineHeight: 1.5,
                    }}
                  >
                    {r.notes.map((n, i) => (
                      <div key={i}>{n}</div>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* 선도 플롯 */}
      <div className="rounded-2xl border border-app-border bg-app-surface p-4">
        {busy ? (
          <div className="grid place-items-center py-16">
            <Loader2 size={20} className="animate-spin text-app-accent" />
          </div>
        ) : ph || ts ? (
          <Plot
            data={active.traces}
            layout={active.layout}
            config={PCFG}
            useResizeHandler
            style={{ width: '100%', height: '760px' }}
          />
        ) : (
          <div className="grid place-items-center py-16">
            <p className="app-text-body-sm text-app-ink/55">
              {t('ai.dataViz.sysPerf.diagram.emptyChartHint')}
            </p>
          </div>
        )}
      </div>

      {/* T-S 축 설정 패널 (원본 _renderTSAxisControls) */}
      {mode === 'ts' ? (
        <div className="flex flex-wrap items-center gap-4 rounded-2xl border border-app-border bg-app-surface-raised p-3">
          <span className="app-text-caption font-bold text-app-ink">
            {t('ai.dataViz.sysPerf.diagram.axisSettings')}
          </span>
          <div className="flex items-center gap-1.5">
            <span className="app-text-caption w-16 font-semibold text-app-ink/75">
              {t('ai.dataViz.sysPerf.diagram.axisLabels.entropy')}
            </span>
            {(['xMin', 'xMax', 'xTick'] as const).map((k, i) => (
              <span key={k} className="flex items-center gap-1">
                <span className="app-text-caption text-app-ink/55">
                  {t(
                    `ai.dataViz.sysPerf.diagram.axisControls.${['min', 'max', 'tick'][i]}`,
                  )}
                </span>
                <input
                  type="number"
                  step={k === 'xTick' ? '0.01' : '0.05'}
                  value={tsAx[k]}
                  onChange={(e) =>
                    setTsAx((axis) =>
                      updateSysPerfDiagramTsAxisDraft({
                        axis,
                        key: k,
                        value: e.target.value,
                      }),
                    )
                  }
                  className="w-16 rounded border border-app-border bg-app-bg px-1.5 py-1 text-center tabular-nums outline-none focus:border-app-accent app-text-caption"
                />
              </span>
            ))}
          </div>
          <div className="flex items-center gap-1.5">
            <span className="app-text-caption w-16 font-semibold text-app-ink/75">
              {t('ai.dataViz.sysPerf.diagram.axisLabels.temperature')}
            </span>
            {(['yMin', 'yMax', 'yTick'] as const).map((k, i) => (
              <span key={k} className="flex items-center gap-1">
                <span className="app-text-caption text-app-ink/55">
                  {t(
                    `ai.dataViz.sysPerf.diagram.axisControls.${['min', 'max', 'tick'][i]}`,
                  )}
                </span>
                <input
                  type="number"
                  step={k === 'yTick' ? '1' : '5'}
                  value={tsAx[k]}
                  onChange={(e) =>
                    setTsAx((axis) =>
                      updateSysPerfDiagramTsAxisDraft({
                        axis,
                        key: k,
                        value: e.target.value,
                      }),
                    )
                  }
                  className="w-16 rounded border border-app-border bg-app-bg px-1.5 py-1 text-center tabular-nums outline-none focus:border-app-accent app-text-caption"
                />
              </span>
            ))}
          </div>
          <button
            type="button"
            onClick={applyTsAx}
            className="app-text-control-sm rounded-md bg-app-accent px-4 py-1.5 font-bold text-app-accent-fg transition-colors hover:bg-app-accent-hover"
          >
            {t('ai.dataViz.sysPerf.diagram.applyAction')}
          </button>
          <button
            type="button"
            onClick={resetTsAx}
            title={t('ai.dataViz.sysPerf.diagram.resetAxisTitle')}
            className="app-text-control-sm rounded-md border border-app-border bg-app-surface px-3 py-1.5 text-app-ink/75 transition-colors hover:bg-app-surface-hover"
          >
            {t('ai.dataViz.sysPerf.diagram.resetAction')}
          </button>
        </div>
      ) : null}
    </div>
  );
}
