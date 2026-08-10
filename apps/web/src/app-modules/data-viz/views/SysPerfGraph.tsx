import { useCallback, useEffect, useMemo, useState } from 'react';
import Plot from 'react-plotly.js';
import { Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { EmptyState, InlineNotice, Select } from '@open-alm/ui';

import { cn } from '@/src/lib/utils';
import { type SysPerfUploadedFile } from '../api/dataviz-api';
import {
  buildSysPerfCompareGraphModel,
  buildSysPerfGraphPlotModel,
  createSysPerfGraphDefaultAxisSetting,
  type SysPerfGraphAxisSetting,
  type SysPerfGraphDataCache,
} from './sysperf-graph';
import {
  buildSysPerfGraphCheckedFiles,
  createSysPerfGraphAxisState,
  groupSysPerfGraphMissingItems,
  selectSysPerfGraphCheckedFiles,
  summarizeSysPerfGraphErrors,
  toggleSysPerfGraphFileChecked,
  toggleSysPerfGraphItemSelection,
  updateSysPerfGraphAxisField,
  updateSysPerfGraphAxisMapField,
} from './sysperf-graph-state';
import {
  loadMissingSysPerfGraphFiles,
  mergeSysPerfGraphLoadResults,
} from './sysperf-graph-loader';
import { MEASURE_ITEMS } from './sysperf-items';
import { isUsableSysPerfUploadedFile } from './sysperf-files';
import { useSysPerfWorkspace } from './sysperf-workspace';

// 원본 sys_perf.js ⑤ loadGraphTab / _drawSelectedGraphs / _drawCompareGraph 이식.
// 항목 클릭 → 항목별 독립 Y축 다축 그래프 + 축범위 컨트롤 + 파일별 비교.
// graph-data 키는 column_mapping.standard_name = `${n}_${nm}`.

const PCFG = { responsive: true, displayModeBar: false } as const;

export function SysPerfGraph({ files }: { files: SysPerfUploadedFile[] }) {
  const { t } = useTranslation('apps');
  const { token, workspaceSlug } = useSysPerfWorkspace();
  const validFiles = useMemo(
    () => files.filter(isUsableSysPerfUploadedFile),
    [files],
  );

  const [selected, setSelected] = useState<number[]>([]);
  const [checked, setChecked] = useState<Record<number, boolean>>({});
  const [cache, setCache] = useState<Record<number, SysPerfGraphDataCache>>({});
  // draft = 입력값, applied = 그래프 반영값 (원본: 적용 버튼 클릭 시 반영)
  const [axisX, setAxisX] = useState<SysPerfGraphAxisSetting>(
    createSysPerfGraphDefaultAxisSetting,
  );
  const [axisY, setAxisY] = useState<Record<number, SysPerfGraphAxisSetting>>(
    {},
  );
  const [appliedX, setAppliedX] = useState<SysPerfGraphAxisSetting>(
    createSysPerfGraphDefaultAxisSetting,
  );
  const [appliedY, setAppliedY] = useState<
    Record<number, SysPerfGraphAxisSetting>
  >({});
  const [cmpItem, setCmpItem] = useState<string>('');
  const [cmpDrawn, setCmpDrawn] = useState<number | null>(null);
  const [cmpBusy, setCmpBusy] = useState(false);

  // 파일 체크 초기화 (전부 체크)
  useEffect(() => {
    setChecked(buildSysPerfGraphCheckedFiles(validFiles));
  }, [validFiles]);

  const checkedKey = validFiles
    .filter((f) => checked[f.file_id])
    .map((f) => f.file_id)
    .join(',');

  // 체크된 파일의 graph-data 로드 (캐시)
  useEffect(() => {
    if (!token || !workspaceSlug) return;
    let cancel = false;
    void loadMissingSysPerfGraphFiles({
      token,
      workspaceSlug,
      files: validFiles,
      cache,
      checked,
      fallbackError: t('ai.dataViz.sysPerf.graph.loadFailed'),
    }).then((results) => {
      if (cancel || !results.length) return;
      setCache((prev) => mergeSysPerfGraphLoadResults(prev, results));
    });
    return () => {
      cancel = true;
    };
  }, [token, workspaceSlug, checkedKey, checked, cache, validFiles, t]);

  const toggleItem = (n: number) =>
    setSelected((s) => toggleSysPerfGraphItemSelection(s, n));
  const toggleFile = (fid: number) =>
    setChecked((c) => toggleSysPerfGraphFileChecked(c, fid));

  const selFilesList = useMemo(
    () => selectSysPerfGraphCheckedFiles(validFiles, checked),
    [validFiles, checked],
  );

  // 에러 (모든 체크 파일이 매칭 없음)
  const { allError: allErr, firstError: firstErr } = useMemo(
    () => summarizeSysPerfGraphErrors(selFilesList, cache),
    [selFilesList, cache],
  );

  const graphLabels = useMemo(
    () => ({
      axisTitle: ({
        index,
        name,
        unit,
      }: {
        index: number;
        name: string;
        unit: string;
      }) => t('ai.dataViz.sysPerf.graph.axisTitle', { index, name, unit }),
      traceFileSuffix: ({ index }: { index: number }) =>
        t('ai.dataViz.sysPerf.graph.traceFileSuffix', { index }),
      fileLabel: ({ index }: { index: number }) =>
        t('ai.dataViz.sysPerf.graph.fileLabel', { index }),
      comparePlotTitle: ({ name }: { name: string }) =>
        t('ai.dataViz.sysPerf.graph.comparePlotTitle', { name }),
      timeAxisTitle: t('ai.dataViz.sysPerf.graph.timeAxisLabel'),
    }),
    [t],
  );

  // ── traces + layout + missing 계산 ──
  const { traces, layout, axisInfo, missing } = useMemo(
    () =>
      buildSysPerfGraphPlotModel({
        selected,
        files: selFilesList,
        cache,
        appliedX,
        appliedY,
        labels: graphLabels,
        fallbackUnit: t('ai.dataViz.sysPerf.graph.otherUnit'),
      }),
    [selected, selFilesList, cache, appliedX, appliedY, graphLabels, t],
  );

  // 누락 항목 그룹화 메시지
  const missingMsg = useMemo(() => {
    if (!missing.length) return '';
    return groupSysPerfGraphMissingItems(missing)
      .map((group) =>
        t('ai.dataViz.sysPerf.graph.fileItems', {
          index: group.fileIndex,
          items: group.items.join(', '),
        }),
      )
      .join(' / ');
  }, [missing, t]);

  // 축 컨트롤 핸들러
  const setYField = (
    itemN: number,
    field: keyof SysPerfGraphAxisSetting,
    v: string,
  ) => setAxisY((p) => updateSysPerfGraphAxisMapField(p, itemN, field, v));
  const onApply = () => {
    setAppliedX(axisX);
    setAppliedY(axisY);
  };
  const onAutoRange = () => {
    const reset = createSysPerfGraphAxisState();
    setAxisX(reset.axisX);
    setAxisY(reset.axisY);
    setAppliedX(reset.appliedX);
    setAppliedY(reset.appliedY);
  };

  // 파일별 비교 traces
  const cmpData = useMemo(
    () =>
      buildSysPerfCompareGraphModel({
        itemNumber: cmpDrawn,
        files: validFiles,
        cache,
        labels: graphLabels,
      }),
    [cmpDrawn, cache, validFiles, graphLabels],
  );

  // 비교 그래프용 데이터 로드 (모든 valid 파일)
  const ensureAllLoaded = useCallback(async () => {
    if (!token || !workspaceSlug) return;
    const results = await loadMissingSysPerfGraphFiles({
      token,
      workspaceSlug,
      files: validFiles,
      cache,
      fallbackError: t('ai.dataViz.sysPerf.graph.loadFailed'),
      cacheErrors: false,
    });
    if (!results.length) return;
    setCache((prev) => mergeSysPerfGraphLoadResults(prev, results));
  }, [token, workspaceSlug, validFiles, cache, t]);

  const onDrawCompare = () => {
    if (!cmpItem) return;
    setCmpBusy(true);
    void ensureAllLoaded()
      .then(() => {
        setCmpDrawn(Number(cmpItem));
      })
      .finally(() => {
        setCmpBusy(false);
      });
  };

  if (!validFiles.length)
    return <EmptyState title={t('ai.dataViz.sysPerf.graph.emptyUpload')} />;

  const numInput =
    'w-16 rounded border border-app-border bg-app-bg px-1 py-0.5 text-center tabular-nums outline-none focus:border-app-accent app-text-caption';

  return (
    <div className="flex flex-col gap-3">
      {/* 파일 체크박스 */}
      {validFiles.length > 1 ? (
        <div className="flex flex-wrap gap-2">
          {validFiles.map((f, i) => (
            <label
              key={f.file_id}
              className={cn(
                'app-text-control-sm inline-flex cursor-pointer items-center gap-1.5 rounded-md border px-3 py-1.5 font-medium',
                checked[f.file_id]
                  ? 'border-app-accent bg-app-accent/10 text-app-accent'
                  : 'border-app-border text-app-ink/65',
              )}
            >
              <input
                type="checkbox"
                checked={!!checked[f.file_id]}
                onChange={() => toggleFile(f.file_id)}
              />
              {t('ai.dataViz.sysPerf.graph.fileLabel', { index: i + 1 })}
            </label>
          ))}
        </div>
      ) : null}

      <div className="flex gap-3">
        {/* 좌: 항목 선택 */}
        <div className="custom-scrollbar max-h-[600px] w-52 shrink-0 overflow-y-auto rounded-lg border border-app-border bg-app-surface">
          <div className="app-text-caption sticky top-0 bg-app-accent px-2 py-2 text-center font-bold text-app-accent-fg">
            {t('ai.dataViz.sysPerf.graph.itemSelectTitle')}
          </div>
          {MEASURE_ITEMS.map((item) => {
            if (item.n === 1) return null;
            const sel = selected.includes(item.n);
            return (
              <div key={item.n}>
                {item.cs ? (
                  <div className="app-text-caption border-b border-app-border bg-app-surface-raised px-2 py-1 font-bold text-app-ink/55">
                    {(item.c || '').replace(/\n/g, ' ')}
                  </div>
                ) : null}
                <button
                  type="button"
                  onClick={() => toggleItem(item.n)}
                  className={cn(
                    'app-text-caption block w-full border-b border-app-border px-2.5 py-1 text-left leading-tight transition-colors',
                    sel
                      ? 'bg-app-accent/15 font-semibold text-app-accent'
                      : 'text-app-ink hover:bg-app-surface-hover',
                  )}
                >
                  {item.nm}
                </button>
              </div>
            );
          })}
        </div>

        {/* 우: 그래프 + 축 컨트롤 */}
        <div className="min-w-0 flex-1">
          {allErr ? (
            <InlineNotice tone="warning">
              {t('ai.dataViz.sysPerf.graph.allError', { error: firstErr })}
            </InlineNotice>
          ) : !selected.length ? (
            <div className="grid min-h-[300px] place-items-center rounded-lg border border-app-border bg-app-surface">
              <p className="app-text-body-sm text-app-ink/55">
                {t('ai.dataViz.sysPerf.graph.emptySelectionHint')}
              </p>
            </div>
          ) : (
            <>
              {missingMsg ? (
                <div className="mb-2">
                  <InlineNotice tone="warning">
                    {t('ai.dataViz.sysPerf.graph.missingNotice', {
                      items: missingMsg,
                    })}
                  </InlineNotice>
                </div>
              ) : null}
              <div className="rounded-lg border border-app-border bg-app-surface p-2">
                <Plot
                  data={traces}
                  layout={layout}
                  config={PCFG}
                  useResizeHandler
                  style={{ width: '100%', height: '500px' }}
                />
              </div>

              {/* 축 범위 컨트롤 */}
              <div className="mt-2 rounded-lg border border-app-border bg-app-surface p-3">
                <div className="app-text-caption mb-1.5 font-bold text-app-ink/75">
                  {t('ai.dataViz.sysPerf.graph.xAxisRangeTitle')}
                </div>
                <div className="mb-2 flex flex-wrap items-center gap-2 border-b border-app-border pb-2 [border-bottom-style:dashed]">
                  <span className="app-text-body-sm w-24 font-semibold text-app-ink">
                    {t('ai.dataViz.sysPerf.graph.timeAxisLabel')}
                  </span>
                  <span className="app-text-caption text-app-ink/55">
                    {t('ai.dataViz.sysPerf.graph.axisControlLabels.min')}
                  </span>
                  <input
                    type="number"
                    className={numInput}
                    value={axisX.mn}
                    onChange={(e) =>
                      setAxisX((p) =>
                        updateSysPerfGraphAxisField(p, 'mn', e.target.value),
                      )
                    }
                  />
                  <span className="app-text-caption text-app-ink/55">
                    {t('ai.dataViz.sysPerf.graph.axisControlLabels.max')}
                  </span>
                  <input
                    type="number"
                    className={numInput}
                    value={axisX.mx}
                    onChange={(e) =>
                      setAxisX((p) =>
                        updateSysPerfGraphAxisField(p, 'mx', e.target.value),
                      )
                    }
                  />
                  <span className="app-text-caption text-app-ink/55">
                    {t('ai.dataViz.sysPerf.graph.divide')}
                  </span>
                  <input
                    type="number"
                    className={numInput}
                    value={axisX.dv}
                    onChange={(e) =>
                      setAxisX((p) =>
                        updateSysPerfGraphAxisField(p, 'dv', e.target.value),
                      )
                    }
                  />
                </div>
                <div className="app-text-caption mb-1.5 font-bold text-app-ink/75">
                  {t('ai.dataViz.sysPerf.graph.yAxisRangeTitle')}
                </div>
                {axisInfo.map((info) => {
                  const s =
                    axisY[info.item.n] ||
                    createSysPerfGraphDefaultAxisSetting();
                  return (
                    <div
                      key={info.item.n}
                      className="mb-1.5 flex flex-wrap items-center gap-2"
                    >
                      <span className="app-text-body-sm inline-flex w-56 items-center gap-1.5 font-semibold text-app-ink">
                        <span
                          className="inline-block h-2.5 w-2.5 rounded-full"
                          style={{ background: info.color }}
                        />
                        {t('ai.dataViz.sysPerf.graph.axisItemLabel', {
                          index: info.idx + 1,
                          name: info.item.nm,
                        })}{' '}
                        <span style={{ color: info.color }}>({info.unit})</span>
                      </span>
                      <span className="app-text-caption text-app-ink/55">
                        {t('ai.dataViz.sysPerf.graph.axisControlLabels.min')}
                      </span>
                      <input
                        type="number"
                        className={numInput}
                        value={s.mn}
                        onChange={(e) =>
                          setYField(info.item.n, 'mn', e.target.value)
                        }
                      />
                      <span className="app-text-caption text-app-ink/55">
                        {t('ai.dataViz.sysPerf.graph.axisControlLabels.max')}
                      </span>
                      <input
                        type="number"
                        className={numInput}
                        value={s.mx}
                        onChange={(e) =>
                          setYField(info.item.n, 'mx', e.target.value)
                        }
                      />
                      <span className="app-text-caption text-app-ink/55">
                        {t('ai.dataViz.sysPerf.graph.divide')}
                      </span>
                      <input
                        type="number"
                        className={numInput}
                        value={s.dv}
                        onChange={(e) =>
                          setYField(info.item.n, 'dv', e.target.value)
                        }
                      />
                    </div>
                  );
                })}
                <div className="mt-2 flex gap-2">
                  <button
                    type="button"
                    onClick={onApply}
                    className="app-text-control-sm rounded-md bg-app-accent px-4 py-1.5 font-medium text-app-accent-fg transition-colors hover:bg-app-accent-hover"
                  >
                    {t('ai.dataViz.sysPerf.graph.apply')}
                  </button>
                  <button
                    type="button"
                    onClick={onAutoRange}
                    className="app-text-control-sm rounded-md border border-app-border bg-app-surface px-3 py-1.5 text-app-ink/80 transition-colors hover:bg-app-surface-hover"
                  >
                    {t('ai.dataViz.sysPerf.graph.autoRange')}
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {/* 파일별 비교 */}
      <div className="rounded-lg border border-app-border bg-app-surface p-3">
        <div className="app-text-body-sm mb-2 font-semibold text-app-ink">
          {t('ai.dataViz.sysPerf.graph.compareTitle')}
        </div>
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <Select
            value={cmpItem}
            onValueChange={setCmpItem}
            placeholder={t('ai.dataViz.sysPerf.graph.comparePlaceholder')}
            options={MEASURE_ITEMS.filter((m) => m.n > 1).map((m) => ({
              value: String(m.n),
              label: m.nm,
            }))}
            className="min-w-[220px]"
          />
          <button
            type="button"
            disabled={!cmpItem || cmpBusy}
            onClick={onDrawCompare}
            className="app-text-control-sm inline-flex items-center gap-1.5 rounded-md bg-app-accent px-3 py-1.5 font-medium text-app-accent-fg transition-colors hover:bg-app-accent-hover disabled:opacity-60"
          >
            {cmpBusy ? <Loader2 size={14} className="animate-spin" /> : null}
            {t('ai.dataViz.sysPerf.graph.drawCompare')}
          </button>
        </div>
        {cmpData.item ? (
          <Plot
            data={cmpData.traces}
            layout={cmpData.layout}
            config={PCFG}
            useResizeHandler
            style={{ width: '100%', height: '400px' }}
          />
        ) : null}
      </div>
    </div>
  );
}
