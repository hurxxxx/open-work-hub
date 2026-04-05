import type { ReactNode } from 'react';
import {
  Bar,
  BarChart,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import type { ChartSeries } from '../types';
import { EmptyState } from './empty-state';

type ChartStatus = 'ready' | 'loading' | 'empty' | 'error';

export interface ChartFrameProps {
  title: ReactNode;
  description?: ReactNode;
  status?: ChartStatus;
  emptyState?: ReactNode;
  children?: ReactNode;
}

function toCartesianData(categories: string[], series: ChartSeries[]) {
  return categories.map((category, index) => {
    return series.reduce<Record<string, string | number>>(
      (row, item) => {
        row[item.key] = item.data[index] ?? 0;
        return row;
      },
      { category },
    );
  });
}

export function ChartFrame({
  title,
  description,
  status = 'ready',
  emptyState,
  children,
}: ChartFrameProps) {
  const body =
    status === 'empty' || status === 'error' ? (
      emptyState ?? (
        <EmptyState
          title="No chart data"
          description="이 영역은 실제 메트릭 연결 후 시각화를 표시합니다."
        />
      )
    ) : (
      children
    );

  return (
    <section className="rounded-[var(--ui-radius-lg)] border border-[var(--ui-color-border)] bg-[var(--ui-color-surface)] p-5 shadow-[var(--ui-shadow-sm)]">
      <div className="mb-4 grid gap-1">
        <h3 className="m-0 text-base font-semibold text-[var(--ui-color-ink)]">{title}</h3>
        {description ? (
          <p className="m-0 text-sm text-[var(--ui-color-ink-muted)]">{description}</p>
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
      <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={192}>
        <LineChart data={data}>
          <XAxis dataKey="category" tickLine={false} axisLine={false} />
          <YAxis tickLine={false} axisLine={false} width={32} />
          <Tooltip />
          {series.map((item) => (
            <Line
              key={item.key}
              type="monotone"
              dataKey={item.key}
              stroke={item.color}
              strokeWidth={2}
              dot={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
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
      <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={192}>
        <BarChart data={data}>
          <XAxis dataKey="category" tickLine={false} axisLine={false} />
          <YAxis tickLine={false} axisLine={false} width={32} />
          <Tooltip />
          {series.map((item) => (
            <Bar key={item.key} dataKey={item.key} fill={item.color} radius={[4, 4, 0, 0]} />
          ))}
        </BarChart>
      </ResponsiveContainer>
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
  const data = categories.map((category, index) => ({
    name: category,
    value: series[0]?.data[index] ?? 0,
    color: series[index]?.color ?? series[0]?.color ?? '#1f2d38',
  }));

  return (
    <ChartFrame title={title} status={status} emptyState={emptyState}>
      <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={192}>
        <PieChart>
          <Tooltip />
          <Pie data={data} dataKey="value" nameKey="name" innerRadius={52} outerRadius={74}>
            {data.map((item) => (
              <Cell key={item.name} fill={item.color} />
            ))}
          </Pie>
        </PieChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
