export function formatUsageNumber(
  value: number | null | undefined,
  locale: string,
): string {
  return new Intl.NumberFormat(locale).format(value ?? 0);
}

export function formatUsagePercent(
  numerator: number | null | undefined,
  denominator: number | null | undefined,
  locale: string,
): string {
  const base = denominator ?? 0;
  if (base <= 0) {
    return '-';
  }
  const percent = ((numerator ?? 0) / base) * 100;
  return `${new Intl.NumberFormat(locale, {
    maximumFractionDigits: 1,
  }).format(percent)}%`;
}

export function formatUsageLatency(
  value: number | null | undefined,
  locale: string,
): string {
  if (!value) {
    return '-';
  }
  return `${formatUsageNumber(value, locale)}ms`;
}

export function formatUsageBytes(
  value: number | null | undefined,
  locale: string,
): string {
  const bytes = value ?? 0;
  if (bytes < 1024) {
    return `${formatUsageNumber(bytes, locale)} B`;
  }
  const units = ['KB', 'MB', 'GB', 'TB'];
  let size = bytes / 1024;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  return `${new Intl.NumberFormat(locale, {
    maximumFractionDigits: size >= 10 ? 0 : 1,
  }).format(size)} ${units[unitIndex]}`;
}

export function formatUsageTrendDate(value: string): string {
  return value.slice(5).replace('-', '/');
}
