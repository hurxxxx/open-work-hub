export const DEFAULT_LOCALE = 'ko-KR';
export const SUPPORTED_LOCALES = ['ko-KR', 'en-US'] as const;
export const LOCALE_STORAGE_KEY = 'aidoo:locale';

export type AppLocale = (typeof SUPPORTED_LOCALES)[number];

export const LOCALE_OPTIONS: Array<{ value: AppLocale; label: string }> = [
  { value: 'ko-KR', label: '한국어' },
  { value: 'en-US', label: 'English' },
];

export function isAppLocale(value: string | null | undefined): value is AppLocale {
  return (SUPPORTED_LOCALES as readonly string[]).includes(value ?? '');
}

export function normalizeLocale(value: string | null | undefined): AppLocale {
  return isAppLocale(value) ? value : DEFAULT_LOCALE;
}

export function readStoredLocale(): AppLocale {
  if (typeof window === 'undefined') {
    return DEFAULT_LOCALE;
  }
  try {
    return normalizeLocale(window.localStorage.getItem(LOCALE_STORAGE_KEY));
  } catch {
    return DEFAULT_LOCALE;
  }
}

export function persistLocale(locale: AppLocale): void {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  } catch {
    return;
  }
}
