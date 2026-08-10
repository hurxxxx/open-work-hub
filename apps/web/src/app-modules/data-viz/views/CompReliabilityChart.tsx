import { useRef, useState } from 'react';
import type { Data, Layout } from 'plotly.js';
import Plot from 'react-plotly.js';
import { useTranslation } from 'react-i18next';

import {
  type AxisKey,
  buildAxisPatch,
  niceRange,
} from './comp-reliability-axis';

const PCFG = {
  responsive: true,
  displayModeBar: false,
  scrollZoom: false,
  doubleClick: false as const,
};

export interface ReliabilityAxisControl {
  key: AxisKey;
  label: string;
  init: [number, number] | null;
}

export function RelChart({
  traces,
  baseLayout,
  axes,
  height = 420,
}: {
  traces: Data[];
  baseLayout: Partial<Layout>;
  axes: ReliabilityAxisControl[];
  height?: number;
}) {
  const { t } = useTranslation('apps');
  const [override, setOverride] = useState<Partial<Layout>>({});
  const inputs = useRef<
    Record<string, { min: number | ''; max: number | ''; div: number }>
  >({});

  axes.forEach((axis) => {
    if (!inputs.current[axis.key]) {
      const range = axis.init ? niceRange(axis.init[0], axis.init[1]) : null;
      inputs.current[axis.key] = {
        min: range ? range.min : '',
        max: range ? range.max : '',
        div: 10,
      };
    }
  });

  const [, force] = useState(0);
  const layout = { ...baseLayout, ...override } as Partial<Layout>;

  const apply = () => {
    const patch: Record<string, unknown> = {};
    axes.forEach((axis) => {
      const value = inputs.current[axis.key];
      if (
        value.min === '' ||
        value.max === '' ||
        Number.isNaN(Number(value.min)) ||
        Number.isNaN(Number(value.max))
      ) {
        return;
      }
      const axisPatch = buildAxisPatch(
        Number(value.min),
        Number(value.max),
        value.div || 10,
      );
      patch[axis.key] = {
        ...((baseLayout as Record<string, unknown>)[axis.key] || {}),
        ...axisPatch,
      };
    });
    setOverride(patch);
  };

  const reset = () => setOverride({});

  return (
    <div className="flex flex-col gap-2">
      <Plot
        data={traces}
        layout={{ ...layout, autosize: true }}
        config={PCFG}
        useResizeHandler
        style={{ width: '100%', height: `${height}px` }}
      />
      <div className="flex flex-wrap items-center gap-2 app-text-caption text-app-ink/65">
        {axes.map((axis) => (
          <span key={axis.key} className="inline-flex items-center gap-1">
            <b className="text-app-ink/75">{axis.label}</b>
            <input
              type="number"
              defaultValue={
                inputs.current[axis.key].min === ''
                  ? ''
                  : String(inputs.current[axis.key].min)
              }
              onChange={(event) => {
                inputs.current[axis.key].min =
                  event.target.value === '' ? '' : Number(event.target.value);
              }}
              className="w-16 rounded border border-app-border bg-app-surface px-1 py-0.5 text-right tabular-nums outline-none focus:border-app-accent"
            />
            <span>~</span>
            <input
              type="number"
              defaultValue={
                inputs.current[axis.key].max === ''
                  ? ''
                  : String(inputs.current[axis.key].max)
              }
              onChange={(event) => {
                inputs.current[axis.key].max =
                  event.target.value === '' ? '' : Number(event.target.value);
              }}
              className="w-16 rounded border border-app-border bg-app-surface px-1 py-0.5 text-right tabular-nums outline-none focus:border-app-accent"
            />
            <span>/</span>
            <input
              type="number"
              defaultValue={String(inputs.current[axis.key].div)}
              onChange={(event) => {
                inputs.current[axis.key].div = Number(event.target.value) || 10;
              }}
              className="w-12 rounded border border-app-border bg-app-surface px-1 py-0.5 text-right tabular-nums outline-none focus:border-app-accent"
            />
          </span>
        ))}
        <button
          type="button"
          onClick={() => {
            apply();
            force((value) => value + 1);
          }}
          className="rounded-md bg-app-accent px-2.5 py-0.5 font-medium text-app-accent-fg transition-colors hover:bg-app-accent-hover"
        >
          {t('ai.dataViz.reliability.axisApply')}
        </button>
        <button
          type="button"
          onClick={() => {
            reset();
            force((value) => value + 1);
          }}
          className="rounded-md border border-app-border bg-app-surface px-2.5 py-0.5 text-app-ink/75 transition-colors hover:bg-app-surface-hover"
        >
          {t('ai.dataViz.reliability.axisAuto')}
        </button>
      </div>
    </div>
  );
}
