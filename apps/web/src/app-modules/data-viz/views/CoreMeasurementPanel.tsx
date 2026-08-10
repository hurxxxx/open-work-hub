import { useEffect, useMemo, useState } from 'react';
import Plot from 'react-plotly.js';
import type { Data, Layout, Shape, Annotations } from 'plotly.js';
import { useTranslation } from 'react-i18next';
import { Loader2 } from 'lucide-react';
import { EmptyState, InlineNotice, Select } from '@open-alm/ui';

import { useAuth } from '@/src/platform/auth/auth-provider';
import { useWorkspaceBootstrapContext } from '@/src/platform/workspaces/workspace-bootstrap-context';
import { resolveShellWorkspaceSlug } from '@/src/platform/workspaces/workspace-utils';
import {
  getCoreMeasurementSeries,
  listCoreMeasurementGroups,
  type DataVizGroup,
  type DataVizSeries,
} from '../api/dataviz-api';
import { CORE_MEASUREMENT_COLORS } from './data-viz-colors';

function isOutOfSpec(
  value: number,
  lsl: number | null,
  usl: number | null,
): boolean {
  if (lsl != null && value < lsl) return true;
  if (usl != null && value > usl) return true;
  return false;
}

export function CoreMeasurementPanel() {
  const { t } = useTranslation('apps');
  const { token, user } = useAuth();
  const workspaceBootstrap = useWorkspaceBootstrapContext();
  const workspaceSlug =
    workspaceBootstrap.data?.workspace.slug ??
    resolveShellWorkspaceSlug(user, null);

  const [groups, setGroups] = useState<DataVizGroup[]>([]);
  const [groupId, setGroupId] = useState('');
  const [item, setItem] = useState('');
  const [series, setSeries] = useState<DataVizSeries | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token || !workspaceSlug) return;
    let cancelled = false;
    listCoreMeasurementGroups(token, workspaceSlug)
      .then((data) => {
        if (cancelled) return;
        setGroups(data);
        if (data.length > 0) {
          setGroupId(data[0].id);
          setItem(data[0].items[0]?.item ?? '');
        }
      })
      .catch((e) => !cancelled && setError(String(e?.message ?? e)));
    return () => {
      cancelled = true;
    };
  }, [token, workspaceSlug]);

  const currentGroup = useMemo(
    () => groups.find((g) => g.id === groupId) ?? null,
    [groups, groupId],
  );

  useEffect(() => {
    if (!currentGroup) return;
    if (!currentGroup.items.some((it) => it.item === item)) {
      setItem(currentGroup.items[0]?.item ?? '');
    }
  }, [currentGroup, item]);

  useEffect(() => {
    if (!token || !workspaceSlug || !groupId || !item) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    getCoreMeasurementSeries(token, workspaceSlug, groupId, item)
      .then((data) => !cancelled && setSeries(data))
      .catch((e) => !cancelled && setError(String(e?.message ?? e)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [token, workspaceSlug, groupId, item]);

  const figure = useMemo(() => {
    if (!series) return null;
    const xs = series.points.map((p) => p.index);
    const ys = series.points.map((p) => p.value);
    const { lsl, usl, nominal } = series.spec;
    const colors = ys.map((v) =>
      isOutOfSpec(v, lsl, usl)
        ? CORE_MEASUREMENT_COLORS.outOfSpec
        : CORE_MEASUREMENT_COLORS.inSpec,
    );
    const outCount = ys.filter((v) => isOutOfSpec(v, lsl, usl)).length;

    const data: Data[] = [
      {
        type: 'scattergl',
        mode: 'lines+markers',
        x: xs,
        y: ys,
        name: t('ai.dataViz.core.measuredValue'),
        line: { color: CORE_MEASUREMENT_COLORS.measuredLine, width: 1 },
        marker: { color: colors, size: 6 },
        hovertemplate: '#%{x}: %{y}<extra></extra>',
      } as Data,
    ];

    const shapes: Partial<Shape>[] = [];
    const annotations: Partial<Annotations>[] = [];
    const hline = (y: number, color: string, dash: string, label: string) => {
      shapes.push({
        type: 'line',
        xref: 'paper',
        x0: 0,
        x1: 1,
        yref: 'y',
        y0: y,
        y1: y,
        line: { color, width: 1, dash },
      } as Partial<Shape>);
      annotations.push({
        xref: 'paper',
        x: 1,
        y,
        xanchor: 'right',
        yanchor: 'bottom',
        text: label,
        showarrow: false,
        font: { size: 10, color },
      } as Partial<Annotations>);
    };
    if (nominal != null)
      hline(
        nominal,
        CORE_MEASUREMENT_COLORS.nominal,
        'dot',
        `${t('ai.dataViz.core.nominal')} ${nominal}`,
      );
    if (usl != null)
      hline(usl, CORE_MEASUREMENT_COLORS.outOfSpec, 'dash', `USL ${usl}`);
    if (lsl != null)
      hline(lsl, CORE_MEASUREMENT_COLORS.outOfSpec, 'dash', `LSL ${lsl}`);

    const layout: Partial<Layout> = {
      title: { text: `${series.model} · ${series.item}` },
      height: 460,
      margin: { t: 48, r: 96, b: 48, l: 64 },
      xaxis: { title: { text: t('ai.dataViz.core.indexAxis') } },
      yaxis: {
        title: { text: series.spec.raw || t('ai.dataViz.core.measuredValue') },
      },
      shapes,
      annotations,
      showlegend: false,
    };

    return { data, layout, outCount, total: ys.length };
  }, [series, t]);

  const groupOptions = useMemo(
    () =>
      groups.map((g) => ({ value: g.id, label: `[${g.sheet}] ${g.model}` })),
    [groups],
  );
  const itemOptions = useMemo(
    () =>
      currentGroup?.items.map((it) => ({ value: it.item, label: it.item })) ??
      [],
    [currentGroup],
  );

  return (
    <section className="flex flex-col gap-4 rounded-2xl border border-app-border bg-app-surface p-4 lg:p-5">
      <div className="flex flex-wrap items-center gap-3 border-b border-app-border pb-3">
        <label className="flex items-center gap-2">
          <span className="app-text-caption text-app-ink/65">
            {t('ai.dataViz.core.model')}
          </span>
          <Select
            value={groupId}
            onValueChange={setGroupId}
            options={groupOptions}
            placeholder={t('ai.dataViz.core.model')}
          />
        </label>
        <label className="flex items-center gap-2">
          <span className="app-text-caption text-app-ink/65">
            {t('ai.dataViz.core.item')}
          </span>
          <Select
            value={item}
            onValueChange={setItem}
            options={itemOptions}
            placeholder={t('ai.dataViz.core.item')}
            disabled={itemOptions.length === 0}
          />
        </label>
        {figure ? (
          <span className="app-text-body-sm ml-auto text-app-ink/65">
            n={figure.total}
            {figure.outCount > 0 ? (
              <span className="ml-2 font-semibold text-ui-danger">
                {t('ai.dataViz.core.outOfSpec', { count: figure.outCount })}
              </span>
            ) : null}
          </span>
        ) : null}
      </div>

      {error ? (
        <InlineNotice tone="danger">
          {t('ai.dataViz.core.loadError', { message: error })}
        </InlineNotice>
      ) : null}

      {loading ? (
        <div className="flex h-64 items-center justify-center">
          <Loader2 size={24} className="animate-spin text-app-accent" />
        </div>
      ) : null}

      {figure && !loading ? (
        <Plot
          data={figure.data}
          layout={figure.layout}
          useResizeHandler
          style={{ width: '100%', height: '460px' }}
          config={{ displaylogo: false, responsive: true }}
        />
      ) : null}

      {!loading && !error && groups.length === 0 ? (
        <EmptyState title={t('ai.dataViz.core.empty')} />
      ) : null}
    </section>
  );
}
