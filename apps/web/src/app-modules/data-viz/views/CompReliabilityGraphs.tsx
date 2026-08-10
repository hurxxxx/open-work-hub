import { useState } from 'react';
import type { Data, Layout } from 'plotly.js';
import { useTranslation } from 'react-i18next';
import { EmptyState } from '@ai-do/ui';

import { cn } from '@/src/lib/utils';
import type { DurabilityGraphResponse } from '../api/dataviz-api';
import {
  CHART_GROUPS_VAR,
  SIMPLE_COLORS,
  SIMPLE_LABELS,
  electricReliabilityColor,
  varReliabilityColor,
  type ElectricGraphConfig,
  type ElectricGraphZoomResult,
  type SimpleField,
} from './comp-reliability-graph-config';
import { DATA_VIZ_PLOT_COLORS } from './data-viz-colors';
import {
  FONT,
  FONT_SIZE_AXIS,
  LINE_WIDTH,
  autoYRange,
  calcXAxis,
  makeYAxis,
} from './comp-reliability-axis';
import { RelChart, type ReliabilityAxisControl } from './CompReliabilityChart';

export function VarReliabilityGraphs({
  resp,
}: {
  resp: DurabilityGraphResponse;
}) {
  const { t } = useTranslation('apps');
  const data = resp.data;
  const allCols = resp.columns || Object.keys(data);
  const firstCol = allCols.find((c) => data[c]);
  const maxHr = firstCol ? data[firstCol].x.slice(-1)[0] : 10;
  const xInfo = calcXAxis(maxHr);
  const [indiv, setIndiv] = useState<string | null>(null);

  return (
    <div className="flex flex-col gap-3">
      <div className="app-text-caption text-ui-success">
        {t('ai.dataViz.reliability.sampleSummaryWithColumns', {
          rows: resp.total_rows,
          points: resp.sampled_points,
          columns: allCols.length,
        })}
      </div>
      <div className="grid gap-3 xl:grid-cols-2">
        {CHART_GROUPS_VAR.map((g) => {
          const mC = g.main.filter((c) => data[c]);
          const sC = g.sub.filter((c) => data[c]);
          if (!mC.length && !sC.length) return null;
          const traces: Data[] = [];
          mC.forEach((c, ci) => {
            const xd =
              xInfo.factor === 1 ? data[c].x : data[c].x.map((v) => v * 60);
            traces.push({
              x: xd,
              y: data[c].y,
              type: 'scattergl',
              mode: 'lines',
              name: c,
              yaxis: 'y',
              line: { color: varReliabilityColor(c, ci), width: LINE_WIDTH },
            } as Data);
          });
          sC.forEach((c, ci) => {
            const xd =
              xInfo.factor === 1 ? data[c].x : data[c].x.map((v) => v * 60);
            traces.push({
              x: xd,
              y: data[c].y,
              type: 'scattergl',
              mode: 'lines',
              name: c,
              yaxis: 'y2',
              line: {
                color: varReliabilityColor(c, mC.length + ci),
                width: LINE_WIDTH,
              },
            } as Data);
          });
          const yr1 = autoYRange(data, mC);
          const yr2 = autoYRange(data, sC);
          const baseLayout: Partial<Layout> = {
            margin: { l: 60, r: 60, t: 10, b: 40 },
            xaxis: {
              title: {
                text: xInfo.label,
                font: { size: FONT_SIZE_AXIS, family: FONT },
              },
              dtick: xInfo.dtick,
              gridcolor: DATA_VIZ_PLOT_COLORS.grid,
              tickfont: { size: FONT_SIZE_AXIS, family: FONT },
            },
            yaxis: makeYAxis(g.yLabel, yr1, false),
            yaxis2: makeYAxis(g.y2Label, yr2, true),
            legend: {
              orientation: 'h',
              y: 1.15,
              x: 0.5,
              xanchor: 'center',
              font: { size: 12, family: FONT },
            },
            font: { family: FONT, size: 11 },
            paper_bgcolor: DATA_VIZ_PLOT_COLORS.paper,
            plot_bgcolor: DATA_VIZ_PLOT_COLORS.plot,
          };
          return (
            <div
              key={g.title}
              className="rounded-2xl border border-app-border bg-app-surface p-3"
            >
              <div className="app-text-body-sm mb-1 font-semibold text-app-ink">
                {g.title}
              </div>
              <RelChart
                traces={traces}
                baseLayout={baseLayout}
                axes={[
                  {
                    key: 'yaxis',
                    label: t('ai.dataViz.reliability.leftAxis'),
                    init: yr1,
                  },
                  {
                    key: 'yaxis2',
                    label: t('ai.dataViz.reliability.rightAxis'),
                    init: yr2,
                  },
                  {
                    key: 'xaxis',
                    label: 'X',
                    init: firstCol
                      ? [
                          data[firstCol].x[0] * (xInfo.factor === 1 ? 1 : 60),
                          maxHr * (xInfo.factor === 1 ? 1 : 60),
                        ]
                      : null,
                  },
                ]}
              />
            </div>
          );
        })}
      </div>
      <div className="rounded-2xl border border-app-border bg-app-surface p-3">
        <div className="app-text-body-sm mb-2 font-semibold text-app-ink">
          {t('ai.dataViz.reliability.selectIndividualItem')}
        </div>
        <div className="mb-2 flex flex-wrap gap-1">
          {allCols
            .filter((c) => data[c])
            .map((c, ci) => (
              <button
                key={c}
                type="button"
                onClick={() => setIndiv(c)}
                style={{
                  color: varReliabilityColor(c, ci),
                  borderColor: varReliabilityColor(c, ci),
                }}
                className={cn(
                  'app-text-caption rounded-md border bg-app-surface px-2 py-0.5',
                  indiv === c ? 'font-bold' : '',
                )}
              >
                {c}
              </button>
            ))}
        </div>
        {indiv && data[indiv] ? (
          <RelChart
            traces={[
              {
                x:
                  xInfo.factor === 1
                    ? data[indiv].x
                    : data[indiv].x.map((v) => v * 60),
                y: data[indiv].y,
                type: 'scattergl',
                mode: 'lines',
                name: indiv,
                line: {
                  color: varReliabilityColor(indiv, 0),
                  width: LINE_WIDTH,
                },
              } as Data,
            ]}
            baseLayout={{
              margin: { l: 60, r: 30, t: 24, b: 40 },
              xaxis: {
                title: {
                  text: xInfo.label,
                  font: { size: FONT_SIZE_AXIS, family: FONT },
                },
                dtick: xInfo.dtick,
                gridcolor: DATA_VIZ_PLOT_COLORS.grid,
              },
              yaxis: makeYAxis(indiv, autoYRange(data, [indiv]), false),
              title: { text: indiv, font: { size: 14, family: FONT } },
              font: { family: FONT, size: 11 },
              paper_bgcolor: DATA_VIZ_PLOT_COLORS.paper,
              plot_bgcolor: DATA_VIZ_PLOT_COLORS.plot,
            }}
            axes={[
              { key: 'yaxis', label: 'Y', init: autoYRange(data, [indiv]) },
            ]}
          />
        ) : (
          <EmptyState title={t('ai.dataViz.reliability.selectItemAbove')} />
        )}
      </div>
    </div>
  );
}

export function ElectricReliabilityGraphs({
  resp,
  cfg,
  zoomResps,
}: {
  resp: DurabilityGraphResponse;
  cfg: ElectricGraphConfig;
  zoomResps: ElectricGraphZoomResult[];
}) {
  const { t } = useTranslation('apps');
  const data = resp.data;
  const xF = cfg.xUnit === 'min' ? 60 : cfg.xUnit === 'sec' ? 3600 : 1;
  const xL =
    cfg.xUnit === 'min'
      ? 'Time (min)'
      : cfg.xUnit === 'sec'
        ? 'Time (sec)'
        : 'Time (hr)';
  const traces: Data[] = [];
  cfg.traces.forEach((t, ti) => {
    if (!data[t.col]) return;
    const xd = data[t.col].x.map((v) => v * xF);
    traces.push({
      x: xd,
      y: data[t.col].y,
      type: 'scattergl',
      mode: 'lines',
      name: t.col,
      yaxis: t.axis,
      line: { color: electricReliabilityColor(t.col, ti), width: LINE_WIDTH },
    } as Data);
  });
  const yCols = cfg.traces.filter((t) => t.axis === 'y').map((t) => t.col);
  const y2Cols = cfg.traces.filter((t) => t.axis === 'y2').map((t) => t.col);
  const yr1 = autoYRange(data, yCols);
  const yr2 = autoYRange(data, y2Cols);
  const fc = cfg.traces[0]?.col;
  const xV = fc && data[fc] ? data[fc].x.map((v) => v * xF) : [0, 10];
  const mX = xV[xV.length - 1] || 10;
  let xDt = mX / 10;
  if (cfg.xUnit !== 'sec') {
    xDt = xDt <= 5 ? 5 : Math.ceil(xDt / 10) * 10;
    if (mX <= 10) xDt = 1;
  } else if (mX <= 30) xDt = Math.ceil(mX / 10);

  const baseLayout: Partial<Layout> = {
    margin: { l: 60, r: 60, t: 10, b: 44 },
    xaxis: {
      title: { text: xL, font: { size: FONT_SIZE_AXIS, family: FONT } },
      dtick: xDt,
      gridcolor: DATA_VIZ_PLOT_COLORS.grid,
      tickfont: { size: FONT_SIZE_AXIS, family: FONT },
    },
    yaxis: makeYAxis(cfg.yLabel, yr1, false),
    yaxis2: makeYAxis(cfg.y2Label, yr2, true),
    legend: {
      orientation: 'h',
      y: 1.1,
      x: 0.5,
      xanchor: 'center',
      font: { size: 12, family: FONT },
    },
    font: { family: FONT, size: 11 },
    paper_bgcolor: DATA_VIZ_PLOT_COLORS.paper,
    plot_bgcolor: DATA_VIZ_PLOT_COLORS.plot,
  };
  const [indiv, setIndiv] = useState<string | null>(null);

  return (
    <div className="flex flex-col gap-3">
      <div className="app-text-caption text-ui-success">
        {t('ai.dataViz.reliability.electricSummary', {
          title: cfg.title,
          original: resp.original_rows,
          total: resp.total_rows,
        })}
      </div>
      <div className="rounded-2xl border border-app-border bg-app-surface p-3">
        <div className="app-text-body-sm mb-1 font-semibold text-app-ink">
          {cfg.title}
        </div>
        <RelChart
          traces={traces}
          baseLayout={baseLayout}
          height={460}
          axes={[
            {
              key: 'yaxis',
              label: t('ai.dataViz.reliability.leftAxis'),
              init: yr1,
            },
            {
              key: 'yaxis2',
              label: t('ai.dataViz.reliability.rightAxis'),
              init: yr2,
            },
            { key: 'xaxis', label: 'X', init: [xV[0], mX] },
          ]}
        />
      </div>
      {zoomResps.length > 0 ? (
        <div className="grid gap-3 lg:grid-cols-2">
          {zoomResps.map(({ z, resp: zr }) => {
            if (!zr || zr.error) return null;
            const zt: Data[] = [];
            cfg.traces.forEach((t, ti) => {
              if (!zr.data[t.col]) return;
              const zx = zr.data[t.col].x.map((v) => v * 3600);
              zt.push({
                x: zx,
                y: zr.data[t.col].y,
                type: 'scattergl',
                mode: 'lines',
                name: t.col,
                yaxis: t.axis,
                line: {
                  color: electricReliabilityColor(t.col, ti),
                  width: LINE_WIDTH,
                },
              } as Data);
            });
            return (
              <div
                key={z.title}
                className="rounded-2xl border border-app-border bg-app-surface p-3"
              >
                <div className="app-text-body-sm mb-1 font-semibold text-app-ink">
                  {z.title}
                </div>
                <RelChart
                  traces={zt}
                  height={320}
                  baseLayout={{
                    margin: { l: 50, r: 50, t: 10, b: 40 },
                    xaxis: {
                      title: {
                        text: 'Time (sec)',
                        font: { size: 12, family: FONT },
                      },
                      gridcolor: DATA_VIZ_PLOT_COLORS.grid,
                    },
                    yaxis: makeYAxis(cfg.yLabel, z.yRange, false),
                    yaxis2: makeYAxis(cfg.y2Label, z.y2Range, true),
                    legend: {
                      orientation: 'h',
                      y: 1.12,
                      x: 0.5,
                      xanchor: 'center',
                      font: { size: 10, family: FONT },
                    },
                    font: { family: FONT, size: 10 },
                    paper_bgcolor: DATA_VIZ_PLOT_COLORS.paper,
                    plot_bgcolor: DATA_VIZ_PLOT_COLORS.plot,
                  }}
                  axes={[
                    {
                      key: 'yaxis',
                      label: t('ai.dataViz.reliability.leftAxis'),
                      init: z.yRange,
                    },
                    {
                      key: 'yaxis2',
                      label: t('ai.dataViz.reliability.rightAxis'),
                      init: z.y2Range,
                    },
                  ]}
                />
              </div>
            );
          })}
        </div>
      ) : null}
      <div className="rounded-2xl border border-app-border bg-app-surface p-3">
        <div className="app-text-body-sm mb-2 font-semibold text-app-ink">
          {t('ai.dataViz.reliability.individualItems')}
        </div>
        <div className="mb-2 flex flex-wrap gap-1">
          {Object.keys(data).map((c, ci) => (
            <button
              key={c}
              type="button"
              onClick={() => setIndiv(c)}
              style={{
                color: electricReliabilityColor(c, ci),
                borderColor: electricReliabilityColor(c, ci),
              }}
              className={cn(
                'app-text-caption rounded-md border bg-app-surface px-2 py-0.5',
                indiv === c ? 'font-bold' : '',
              )}
            >
              {c}
            </button>
          ))}
        </div>
        {indiv && data[indiv] ? (
          <RelChart
            traces={[
              {
                x: data[indiv].x.map((v) => v * xF),
                y: data[indiv].y,
                type: 'scattergl',
                mode: 'lines',
                name: indiv,
                line: {
                  color: electricReliabilityColor(indiv, 0),
                  width: LINE_WIDTH,
                },
              } as Data,
            ]}
            baseLayout={{
              margin: { l: 60, r: 30, t: 24, b: 40 },
              xaxis: {
                title: {
                  text: xL,
                  font: { size: FONT_SIZE_AXIS, family: FONT },
                },
                gridcolor: DATA_VIZ_PLOT_COLORS.grid,
              },
              yaxis: makeYAxis(indiv, autoYRange(data, [indiv]), false),
              title: { text: indiv, font: { size: 14, family: FONT } },
              font: { family: FONT, size: 11 },
              paper_bgcolor: DATA_VIZ_PLOT_COLORS.paper,
              plot_bgcolor: DATA_VIZ_PLOT_COLORS.plot,
            }}
            axes={[
              { key: 'yaxis', label: 'Y', init: autoYRange(data, [indiv]) },
            ]}
          />
        ) : (
          <EmptyState title={t('ai.dataViz.reliability.selectItemAbove')} />
        )}
      </div>
    </div>
  );
}

export function SimpleReliabilityGraph({
  resp,
  colMap,
}: {
  resp: DurabilityGraphResponse;
  colMap: Record<SimpleField, string>;
}) {
  const { t } = useTranslation('apps');
  const data = resp.data;
  const allCols = resp.columns || Object.keys(data);
  const letterToIdx = (l: string): number => {
    let r = 0;
    const u = l.toUpperCase();
    for (let i = 0; i < u.length; i++) r = r * 26 + (u.charCodeAt(i) - 64);
    return r - 1;
  };
  const findCol = (letter: string): string | null => {
    const idx = letterToIdx(letter);
    return idx >= 0 && idx < allCols.length ? allCols[idx] : null;
  };
  const traces: Data[] = [];
  const yMainCols: string[] = [];
  const y2Cols: string[] = [];
  const y3Cols: string[] = [];
  const addTraces = (fields: SimpleField[], axis: string, bucket: string[]) => {
    fields.forEach((f) => {
      const letter = colMap[f];
      if (!letter) return;
      const col = findCol(letter);
      if (!col || !data[col]) return;
      bucket.push(col);
      traces.push({
        x: data[col].x,
        y: data[col].y,
        type: 'scattergl',
        mode: 'lines',
        name: SIMPLE_LABELS[f],
        yaxis: axis,
        line: { color: SIMPLE_COLORS[f], width: LINE_WIDTH },
      } as Data);
    });
  };
  addTraces(['pd', 'ps', 'crank'], 'y', yMainCols);
  addTraces(['td', 'ts', 'surface'], 'y2', y2Cols);
  addTraces(['rpm'], 'y3', y3Cols);
  const [indiv, setIndiv] = useState<string | null>(null);

  if (!traces.length) {
    return <EmptyState title={t('ai.dataViz.reliability.noMappedData')} />;
  }

  const yr1 = autoYRange(data, yMainCols);
  const yr2 = autoYRange(data, y2Cols);
  const yr3 = autoYRange(data, y3Cols);
  const firstCol = allCols.find((c) => data[c]);
  const maxHr = firstCol ? data[firstCol].x.slice(-1)[0] : 10;
  const xInfo = calcXAxis(maxHr);
  const hasY3 = y3Cols.length > 0;
  const domR = hasY3 ? 0.92 : 1.0;

  const baseLayout: Record<string, unknown> = {
    margin: { l: 60, r: hasY3 ? 40 : 60, t: 10, b: 44 },
    xaxis: {
      title: {
        text: xInfo.label,
        font: { size: FONT_SIZE_AXIS, family: FONT },
      },
      dtick: xInfo.dtick,
      gridcolor: DATA_VIZ_PLOT_COLORS.grid,
      tickfont: { size: FONT_SIZE_AXIS, family: FONT },
      domain: [0, domR],
    },
    yaxis: makeYAxis(t('ai.dataViz.reliability.pressureAxis'), yr1, false),
    yaxis2: makeYAxis(t('ai.dataViz.reliability.temperatureAxis'), yr2, true),
    legend: {
      orientation: 'h',
      y: 1.1,
      x: 0.5,
      xanchor: 'center',
      font: { size: 12, family: FONT },
    },
    font: { family: FONT, size: 11 },
    paper_bgcolor: DATA_VIZ_PLOT_COLORS.paper,
    plot_bgcolor: DATA_VIZ_PLOT_COLORS.plot,
  };
  if (hasY3) {
    baseLayout.yaxis3 = {
      ...makeYAxis('RPM', yr3, true),
      anchor: 'free',
      position: 1.0,
      tickfont: {
        size: FONT_SIZE_AXIS,
        family: FONT,
        color: SIMPLE_COLORS.rpm,
      },
    };
  }
  const axes: ReliabilityAxisControl[] = [
    {
      key: 'yaxis',
      label: t('ai.dataViz.reliability.leftPressureAxis'),
      init: yr1,
    },
    {
      key: 'yaxis2',
      label: t('ai.dataViz.reliability.rightTemperatureAxis'),
      init: yr2,
    },
    ...(hasY3
      ? [
          {
            key: 'yaxis3',
            label: t('ai.dataViz.reliability.rightRpmAxis'),
            init: yr3,
          } satisfies ReliabilityAxisControl,
        ]
      : []),
    {
      key: 'xaxis',
      label: 'X',
      init: firstCol ? [data[firstCol].x[0], maxHr] : null,
    },
  ];

  return (
    <div className="flex flex-col gap-3">
      <div className="app-text-caption text-ui-success">
        {t('ai.dataViz.reliability.sampleSummary', {
          rows: resp.total_rows,
          points: resp.sampled_points,
        })}
      </div>
      <div className="rounded-2xl border border-app-border bg-app-surface p-3">
        <RelChart
          traces={traces}
          baseLayout={baseLayout as Partial<Layout>}
          axes={axes}
          height={460}
        />
      </div>
      <div className="rounded-2xl border border-app-border bg-app-surface p-3">
        <div className="app-text-body-sm mb-2 font-semibold text-app-ink">
          {t('ai.dataViz.reliability.individualItems')}
        </div>
        <div className="mb-2 flex flex-wrap gap-1">
          {allCols
            .filter((c) => data[c])
            .map((c) => (
              <button
                key={c}
                type="button"
                onClick={() => setIndiv(c)}
                className={cn(
                  'app-text-caption rounded-md border border-app-border bg-app-surface px-2 py-0.5 text-app-ink',
                  indiv === c ? 'border-app-accent font-bold' : '',
                )}
              >
                {c}
              </button>
            ))}
        </div>
        {indiv && data[indiv] ? (
          <RelChart
            traces={[
              {
                x: data[indiv].x,
                y: data[indiv].y,
                type: 'scattergl',
                mode: 'lines',
                name: indiv,
                line: { width: LINE_WIDTH },
              } as Data,
            ]}
            baseLayout={{
              margin: { l: 60, r: 30, t: 24, b: 40 },
              xaxis: {
                title: {
                  text: xInfo.label,
                  font: { size: FONT_SIZE_AXIS, family: FONT },
                },
                dtick: xInfo.dtick,
                gridcolor: DATA_VIZ_PLOT_COLORS.grid,
              },
              yaxis: makeYAxis(indiv, autoYRange(data, [indiv]), false),
              title: { text: indiv, font: { size: 14, family: FONT } },
              font: { family: FONT, size: 11 },
              paper_bgcolor: DATA_VIZ_PLOT_COLORS.paper,
              plot_bgcolor: DATA_VIZ_PLOT_COLORS.plot,
            }}
            axes={[
              { key: 'yaxis', label: 'Y', init: autoYRange(data, [indiv]) },
            ]}
          />
        ) : (
          <EmptyState title={t('ai.dataViz.reliability.selectItemAbove')} />
        )}
      </div>
    </div>
  );
}
