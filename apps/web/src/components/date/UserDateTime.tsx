import { useMemo, type ComponentPropsWithoutRef } from 'react';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  DATE_DISPLAY_LOCALE,
  formatDateTime,
  formatRelativeTime,
  normalizeDateFormatPreference,
  normalizeTimeZone,
  parseApiDateTime,
  type DateFormatPreference,
  type RelativeTimeOptions,
  type TemporalInput,
  type ZonedFormatOptions,
} from '@/src/platform/time/time-utils';

export type UserDateTimeDisplay = 'date' | 'datetime' | 'relative' | 'time';

export interface UserDateTimeFormatterOptions {
  dateFormat?: DateFormatPreference | string | null;
  locale?: string | null;
  timeZone?: string | null;
}

export interface UserDateTimeFormatOptions
  extends ZonedFormatOptions,
    RelativeTimeOptions {}

export interface UserDateTimeFormatter {
  dateFormat: DateFormatPreference;
  locale: string;
  timeZone: string;
  format: (
    value: TemporalInput,
    display?: UserDateTimeDisplay,
    options?: UserDateTimeFormatOptions,
  ) => string;
  formatDate: (value: TemporalInput, options?: ZonedFormatOptions) => string;
  formatDateTime: (
    value: TemporalInput,
    options?: ZonedFormatOptions,
  ) => string;
  formatRelativeTime: (
    value: TemporalInput,
    options?: RelativeTimeOptions,
  ) => string;
  formatTime: (value: TemporalInput, options?: ZonedFormatOptions) => string;
}

export interface UserDateTimeProps
  extends Omit<ComponentPropsWithoutRef<'time'>, 'children' | 'dateTime'> {
  display?: UserDateTimeDisplay;
  fallback?: string;
  options?: UserDateTimeFormatOptions;
  value: TemporalInput;
}

const DEFAULT_DATE_OPTIONS = {
  dateStyle: 'short',
} satisfies Intl.DateTimeFormatOptions;

const DEFAULT_DATE_TIME_OPTIONS = {
  dateStyle: 'short',
  timeStyle: 'short',
} satisfies Intl.DateTimeFormatOptions;

const DEFAULT_TIME_OPTIONS = {
  hour: '2-digit',
  minute: '2-digit',
} satisfies Intl.DateTimeFormatOptions;

const DEFAULT_LOCALE_DATE_COMPONENT_OPTIONS = {
  day: 'numeric',
  month: 'numeric',
  year: 'numeric',
} satisfies Intl.DateTimeFormatOptions;

const TIME_COMPONENT_OPTION_KEYS = [
  'dayPeriod',
  'fractionalSecondDigits',
  'hour',
  'minute',
  'second',
  'timeZoneName',
] as const satisfies readonly (keyof Intl.DateTimeFormatOptions)[];

const DATE_ONLY_RE = /^\d{4}-\d{2}-\d{2}$/;

function resolveLocale(locale: string | null | undefined): string {
  return locale?.trim() || DATE_DISPLAY_LOCALE;
}

function withUserZonedOptions(
  base: UserDateTimeFormatterOptions,
  options: ZonedFormatOptions = {},
): ZonedFormatOptions {
  return {
    ...options,
    dateFormat: options.dateFormat ?? base.dateFormat,
    locale: options.locale ?? base.locale ?? undefined,
    timeZone: normalizeTimeZone(options.timeZone ?? base.timeZone),
  };
}

function withUserRelativeOptions(
  base: UserDateTimeFormatterOptions,
  options: RelativeTimeOptions = {},
): RelativeTimeOptions {
  return {
    ...options,
    dateFormat: options.dateFormat ?? base.dateFormat,
    locale: options.locale ?? base.locale ?? undefined,
    timeZone: normalizeTimeZone(options.timeZone ?? base.timeZone),
  };
}

function hasFormatOption(
  options: Intl.DateTimeFormatOptions,
  keys: readonly (keyof Intl.DateTimeFormatOptions)[],
): boolean {
  return keys.some(
    (key) =>
      Object.prototype.hasOwnProperty.call(options, key) &&
      options[key] !== undefined,
  );
}

function withDefaultDateTimeOptions(
  dateFormat: DateFormatPreference,
  options: ZonedFormatOptions,
): ZonedFormatOptions {
  if (hasFormatOption(options, TIME_COMPONENT_OPTION_KEYS)) {
    return {
      ...(dateFormat === 'locale'
        ? DEFAULT_LOCALE_DATE_COMPONENT_OPTIONS
        : DEFAULT_DATE_OPTIONS),
      ...options,
    };
  }
  return {
    ...DEFAULT_DATE_TIME_OPTIONS,
    ...options,
  };
}

function withDefaultTimeOptions(
  options: ZonedFormatOptions,
): ZonedFormatOptions {
  if (
    options.timeStyle ||
    hasFormatOption(options, TIME_COMPONENT_OPTION_KEYS)
  ) {
    return options;
  }
  return {
    ...DEFAULT_TIME_OPTIONS,
    ...options,
  };
}

function machineDateTime(value: TemporalInput): string | undefined {
  if (typeof value === 'string' && DATE_ONLY_RE.test(value)) {
    return value;
  }
  return parseApiDateTime(value)?.toISOString();
}

export function createUserDateTimeFormatter(
  options: UserDateTimeFormatterOptions = {},
): UserDateTimeFormatter {
  const locale = resolveLocale(options.locale);
  const timeZone = normalizeTimeZone(options.timeZone);
  const dateFormat = normalizeDateFormatPreference(options.dateFormat);
  const base = { dateFormat, locale, timeZone };

  const formatter: UserDateTimeFormatter = {
    dateFormat,
    locale,
    timeZone,
    format(value, display = 'datetime', formatOptions = {}) {
      if (display === 'date') {
        return formatter.formatDate(value, formatOptions);
      }
      if (display === 'time') {
        return formatter.formatTime(value, formatOptions);
      }
      if (display === 'relative') {
        return formatter.formatRelativeTime(value, formatOptions);
      }
      return formatter.formatDateTime(value, formatOptions);
    },
    formatDate(value, formatOptions = {}) {
      return formatDateTime(
        value,
        withUserZonedOptions(base, {
          ...DEFAULT_DATE_OPTIONS,
          ...formatOptions,
        }),
      );
    },
    formatDateTime(value, formatOptions = {}) {
      return formatDateTime(
        value,
        withUserZonedOptions(
          base,
          withDefaultDateTimeOptions(dateFormat, formatOptions),
        ),
      );
    },
    formatRelativeTime(value, formatOptions = {}) {
      return formatRelativeTime(
        value,
        withUserRelativeOptions(base, formatOptions),
      );
    },
    formatTime(value, formatOptions = {}) {
      return formatDateTime(
        value,
        withUserZonedOptions(base, withDefaultTimeOptions(formatOptions)),
      );
    },
  };

  return formatter;
}

export function useUserDateTimeFormatter(): UserDateTimeFormatter {
  const { user } = useAuth();
  const { i18n } = useTranslation();

  return useMemo(
    () =>
      createUserDateTimeFormatter({
        dateFormat: user?.date_format,
        locale: user?.locale ?? i18n.language,
        timeZone: user?.time_zone,
      }),
    [i18n.language, user?.date_format, user?.locale, user?.time_zone],
  );
}

export function UserDateTime({
  display = 'datetime',
  fallback = '',
  options,
  title,
  value,
  ...timeProps
}: UserDateTimeProps) {
  const formatter = useUserDateTimeFormatter();
  const label = formatter.format(value, display, {
    fallback,
    ...options,
  });
  const dateTime = machineDateTime(value);
  const relativeTitle =
    title ??
    (display === 'relative'
      ? formatter.formatDateTime(value, { fallback })
      : undefined);

  return (
    <time dateTime={dateTime} title={relativeTitle} {...timeProps}>
      {label || fallback}
    </time>
  );
}
