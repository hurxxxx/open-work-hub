export type ByteSizeUnit = 'KB' | 'MB' | 'GB' | 'TB';

export type ByteSizeFractionDigits = number | 'compact';

export interface FormatByteSizeOptions {
  fractionDigits?: ByteSizeFractionDigits;
  locale?: string;
  trailingZeros?: 'preserve' | 'trim';
  units?: readonly ByteSizeUnit[];
}

const DEFAULT_BYTE_SIZE_UNITS: readonly ByteSizeUnit[] = ['KB', 'MB'];
const numberFormatters = new Map<string, Intl.NumberFormat>();

function fractionDigitsForValue(
  value: number,
  fractionDigits: ByteSizeFractionDigits | undefined,
): number {
  if (fractionDigits === 'compact') {
    return value >= 10 ? 0 : 1;
  }
  return fractionDigits ?? 1;
}

function formatByteSizeNumber(
  value: number,
  fractionDigits: number,
  options: FormatByteSizeOptions,
): string {
  const trailingZeros = options.trailingZeros ?? 'preserve';
  if (!options.locale) {
    const fixed = value.toFixed(fractionDigits);
    return trailingZeros === 'trim' ? String(Number(fixed)) : fixed;
  }

  const minimumFractionDigits =
    trailingZeros === 'preserve' ? fractionDigits : 0;
  const formatterKey = [
    options.locale,
    fractionDigits,
    minimumFractionDigits,
  ].join(':');
  let formatter = numberFormatters.get(formatterKey);
  if (!formatter) {
    formatter = new Intl.NumberFormat(options.locale, {
      maximumFractionDigits: fractionDigits,
      minimumFractionDigits,
    });
    numberFormatters.set(formatterKey, formatter);
  }
  return formatter.format(value);
}

export function formatByteSize(
  bytes: number,
  options: FormatByteSizeOptions = {},
): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }

  const units =
    options.units && options.units.length > 0
      ? options.units
      : DEFAULT_BYTE_SIZE_UNITS;
  let value = bytes / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }

  const fractionDigits = fractionDigitsForValue(value, options.fractionDigits);
  return `${formatByteSizeNumber(value, fractionDigits, options)} ${
    units[unitIndex]
  }`;
}
