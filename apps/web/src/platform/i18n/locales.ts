import {
  isSupportedLocale,
  normalizeLocale as normalizeLocaleSession,
  persistLocale as persistLocaleSession,
  readStoredLocale as readStoredLocaleSession,
  type LocaleSessionConfig,
  type LocaleStoreDependencies,
} from './locale-session';

export const DEFAULT_LOCALE = 'ko-KR';
export const SUPPORTED_LOCALES = ['ko-KR', 'en-US'] as const;
export const LOCALE_STORAGE_KEY = 'ai-do:locale';

export type AppLocale = (typeof SUPPORTED_LOCALES)[number];

export const LOCALE_OPTIONS: Array<{ value: AppLocale; label: string }> = [
  { value: 'ko-KR', label: '한국어' },
  { value: 'en-US', label: 'English' },
];

export const LOCALE_SESSION_CONFIG = {
  defaultLocale: DEFAULT_LOCALE,
  supportedLocales: SUPPORTED_LOCALES,
  storageKey: LOCALE_STORAGE_KEY,
} satisfies LocaleSessionConfig<AppLocale>;

export function isAppLocale(
  value: string | null | undefined,
): value is AppLocale {
  return isSupportedLocale(value, LOCALE_SESSION_CONFIG);
}

export function normalizeLocale(value: string | null | undefined): AppLocale {
  return normalizeLocaleSession(value, LOCALE_SESSION_CONFIG);
}

export function readStoredLocale(
  dependencies?: LocaleStoreDependencies,
): AppLocale {
  return readStoredLocaleSession(LOCALE_SESSION_CONFIG, dependencies);
}

export function persistLocale(
  locale: AppLocale,
  dependencies?: LocaleStoreDependencies,
): void {
  persistLocaleSession(locale, LOCALE_SESSION_CONFIG, dependencies);
}
