import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import {
  DEFAULT_LOCALE,
  LOCALE_SESSION_CONFIG,
  readStoredLocale,
  type AppLocale,
} from './locales';
import {
  syncLocale as syncLocaleSession,
  type LocaleI18n,
} from './locale-session';
import { resources } from './resources';

void i18n.use(initReactI18next).init({
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
  return syncLocaleSession<AppLocale>(locale, LOCALE_SESSION_CONFIG, {
    i18n: i18n as LocaleI18n<AppLocale>,
  });
}

export { i18n };
