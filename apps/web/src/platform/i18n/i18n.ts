import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import {
  DEFAULT_LOCALE,
  normalizeLocale,
  persistLocale,
  readStoredLocale,
  type AppLocale,
} from './locales';
import { resources } from './resources';

void i18n
  .use(initReactI18next)
  .init({
    defaultNS: 'common',
    fallbackLng: DEFAULT_LOCALE,
    interpolation: {
      escapeValue: false,
    },
    lng: readStoredLocale(),
    ns: Object.keys(resources[DEFAULT_LOCALE]),
    react: {
      useSuspense: false,
    },
    resources,
    supportedLngs: Object.keys(resources),
  });

export function syncLocale(locale: string | null | undefined): AppLocale {
  const normalized = normalizeLocale(locale);
  if (i18n.language !== normalized) {
    void i18n.changeLanguage(normalized);
  }
  persistLocale(normalized);
  if (typeof document !== 'undefined') {
    document.documentElement.lang = normalized;
  }
  return normalized;
}

export { i18n };
