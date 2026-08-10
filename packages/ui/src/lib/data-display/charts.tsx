import { lazy, Suspense, type CSSProperties, type ReactNode } from 'react';

import type { ChartSeries } from '../types';
import {
  toCartesianData,
  toDonutChartData,
  type CartesianChartData,
  type DonutChartData,
} from './chart-data';

type ChartStatus = 'ready' | 'loading' | 'empty' | 'error';

const chartAxisTick = {
  fill: 'var(--ui-color-ink-muted)',
  fontSize: 12,
};

const chartTooltipContentStyle: CSSProperties = {
  backgroundColor: 'var(--ui-color-surface-raised)',
  border: '1px solid var(--ui-color-border)',
  borderRadius: 'var(--ui-radius-sm)',
  boxShadow: 'var(--ui-shadow-lg)',
  color: 'var(--ui-color-ink)',
};

const chartTooltipLabelStyle: CSSProperties = {
  color: 'var(--ui-color-ink)',
};

const chartTooltipItemStyle: CSSProperties = {
  color: 'var(--ui-color-ink-muted)',
};

export interface ChartFrameProps {
  title: ReactNode;
  description?: ReactNode;
  status?: ChartStatus;
  emptyState?: ReactNode;
  children?: ReactNode;
}

const LineChartRenderer = lazy(async () => {
  const { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } =
    await import('recharts');

  return {
    default: function LineChartRenderer({
      data,
      series,
    }: {
      data: CartesianChartData;
      series: ChartSeries[];
    }) {
      return (
        <ResponsiveContainer
          width="100%"
          height="100%"
          initialDimension={{ width: 640, height: 192 }}
          minWidth={0}
          minHeight={192}
        >
          <LineChart data={data}>
            <XAxis
              axisLine={false}
              dataKey="category"
              tick={chartAxisTick}
              tickLine={false}
              tickMargin={8}
            />
            <YAxis
              axisLine={false}
              tick={chartAxisTick}
              tickLine={false}
              tickMargin={8}
              width={32}
            />
            <Tooltip
              contentStyle={chartTooltipContentStyle}
              itemStyle={chartTooltipItemStyle}
              labelStyle={chartTooltipLabelStyle}
            />
            {series.map((item) => (
              <Line
                key={item.key}
                type="monotone"
                dataKey={item.key}
                name={item.label}
                stroke={item.color}
                strokeWidth={2}
                dot={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      );
    },
  };
});

const BarChartRenderer = lazy(async () => {
  const { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } =
    await import('recharts');

  return {
    default: function BarChartRenderer({
      data,
      series,
    }: {
      data: CartesianChartData;
      series: ChartSeries[];
    }) {
      return (
        <ResponsiveContainer
          width="100%"
          height="100%"
          initialDimension={{ width: 640, height: 192 }}
          minWidth={0}
          minHeight={192}
        >
          <BarChart data={data}>
            <XAxis
              axisLine={false}
              dataKey="category"
              tick={chartAxisTick}
              tickLine={false}
              tickMargin={8}
            />
            <YAxis
              axisLine={false}
              tick={chartAxisTick}
              tickLine={false}
              tickMargin={8}
              width={32}
            />
            <Tooltip
              contentStyle={chartTooltipContentStyle}
              itemStyle={chartTooltipItemStyle}
              labelStyle={chartTooltipLabelStyle}
            />
            {series.map((item) => (
              <Bar
                key={item.key}
                dataKey={item.key}
                name={item.label}
                fill={item.color}
                radius={[4, 4, 0, 0]}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      );
    },
  };
});

const DonutChartRenderer = lazy(async () => {
  const { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } = await import(
    'recharts'
  );

  return {
    default: function DonutChartRenderer({ data }: { data: DonutChartData }) {
      return (
        <ResponsiveContainer
          width="100%"
          height="100%"
          initialDimension={{ width: 320, height: 192 }}
          minWidth={0}
          minHeight={192}
        >
          <PieChart>
            <Tooltip
              contentStyle={chartTooltipContentStyle}
              itemStyle={chartTooltipItemStyle}
              labelStyle={chartTooltipLabelStyle}
            />
            <Pie
              data={data}
              dataKey="value"
              nameKey="name"
              innerRadius={52}
              outerRadius={74}
            >
              {data.map((item) => (
                <Cell key={item.name} fill={item.color} />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
      );
    },
  };
});

export function ChartFrame({
  title,
  description,
  status = 'ready',
  emptyState,
  children,
}: ChartFrameProps) {
  const body =
    status === 'empty' || status === 'error' ? (emptyState ?? null) : children;

  return (
    <section className="rounded-[var(--ui-radius-lg)] border border-[var(--ui-color-border)] bg-ui-surface p-5 shadow-[var(--ui-shadow-sm)]">
      <div className="mb-4 grid gap-1">
        <h3 className="m-0 text-[length:var(--ui-text-h3)] font-semibold text-[var(--ui-color-ink)]">
          {title}
        </h3>
        {description ? (
          <p className="m-0 text-[length:var(--ui-text-body)] text-[var(--ui-color-ink-muted)]">
            {description}
          </p>
        ) : null}
      </div>
      <div className="h-48">{body}</div>
    </section>
  );
}

export interface LineChartCardProps {
  title: ReactNode;
  categories: string[];
  series: ChartSeries[];
  status?: ChartStatus;
  emptyState?: ReactNode;
}

export function LineChartCard({
  title,
  categories,
  series,
  status = 'ready',
  emptyState,
}: LineChartCardProps) {
  const data = toCartesianData(categories, series);

  return (
    <ChartFrame title={title} status={status} emptyState={emptyState}>
      <Suspense fallback={null}>
        <LineChartRenderer data={data} series={series} />
      </Suspense>
    </ChartFrame>
  );
}

export type BarChartCardProps = LineChartCardProps;

export function BarChartCard({
  title,
  categories,
  series,
  status = 'ready',
  emptyState,
}: BarChartCardProps) {
  const data = toCartesianData(categories, series);

  return (
    <ChartFrame title={title} status={status} emptyState={emptyState}>
      <Suspense fallback={null}>
        <BarChartRenderer data={data} series={series} />
      </Suspense>
    </ChartFrame>
  );
}

export interface DonutChartCardProps {
  title: ReactNode;
  categories: string[];
  series: ChartSeries[];
  status?: ChartStatus;
  emptyState?: ReactNode;
}

export function DonutChartCard({
  title,
  categories,
  series,
  status = 'ready',
  emptyState,
}: DonutChartCardProps) {
  const data = toDonutChartData(categories, series);

  return (
    <ChartFrame title={title} status={status} emptyState={emptyState}>
      <Suspense fallback={null}>
        <DonutChartRenderer data={data} />
      </Suspense>
    </ChartFrame>
  );
}
