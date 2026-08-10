import type { ChartSeries } from '../types';

export type CartesianChartData = Array<Record<string, string | number>>;
export type DonutChartData = Array<{
  name: string;
  value: number;
  color: string;
}>;

export function toCartesianData(
  categories: readonly string[],
  series: readonly ChartSeries[],
): CartesianChartData {
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

export function toDonutChartData(
  categories: readonly string[],
  series: readonly ChartSeries[],
): DonutChartData {
  return categories.map((category, index) => ({
    name: category,
    value: series[0]?.data[index] ?? 0,
    color: series[index]?.color ?? series[0]?.color ?? 'var(--ui-color-accent)',
  }));
}
