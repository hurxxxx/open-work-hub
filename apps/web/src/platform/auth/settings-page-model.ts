import {
  normalizeDateFormatPreference,
  normalizeTimeZone,
} from '@/src/platform/time/time-utils';
import { normalizeLocale } from '@/src/platform/i18n';

import type {
  AuthSessionItem,
  AuthUser,
  ChangePasswordPayload,
  DateFormatPreference,
  LocalePreference,
  ThemePreference,
  UpdatePreferencesPayload,
} from './auth-api';

export type SettingsSection =
  | 'profile'
  | 'appearance'
  | 'security'
  | 'notifications'
  | 'releaseNotes'
  | 'openWorkHubDesktop';

export type SettingsTranslator = (
  key: string,
  options?: Record<string, unknown>,
) => string;

export interface ProfilePageState {
  activeSection: SettingsSection;
  displayName: string;
  fullName: string;
  themePreference: ThemePreference;
  timeZone: string;
  locale: LocalePreference;
  dateFormat: DateFormatPreference;
  defaultWorkspaceId: string;
  submitting: boolean;
  message: string | null;
  error: string | null;
  currentPassword: string;
  newPassword: string;
  sessions: AuthSessionItem[];
  loadingSessions: boolean;
}

export type ProfilePreferenceChange =
  | { type: 'theme'; value: ThemePreference }
  | { type: 'locale'; value: string }
  | { type: 'timeZone'; value: string }
  | { type: 'dateFormat'; value: string }
  | { type: 'defaultWorkspace'; value: string };

export type ProfilePreferenceSyncPlan = {
  kind: 'locale';
  next: LocalePreference;
  previous: LocalePreference;
};

export type ProfilePreferenceSavePlan = {
  optimisticPatch: Partial<ProfilePageState>;
  payload: UpdatePreferencesPayload;
  rollbackPatch: Partial<ProfilePageState>;
  sync?: ProfilePreferenceSyncPlan;
};

export type ProfileDetailsSavePlan = {
  startPatch: Partial<ProfilePageState>;
  payload: UpdatePreferencesPayload;
  successPatch: (message: string) => Partial<ProfilePageState>;
  failurePatch: (error: unknown, fallback: string) => Partial<ProfilePageState>;
  completePatch: Partial<ProfilePageState>;
};

export type PasswordChangePlan = {
  startPatch: Partial<ProfilePageState>;
  payload: ChangePasswordPayload;
  successPatch: (message: string) => Partial<ProfilePageState>;
  failurePatch: (error: unknown, fallback: string) => Partial<ProfilePageState>;
};

export interface VisibleAuthSessions {
  hiddenCount: number;
  shownSessions: AuthSessionItem[];
}

export type ProfilePageAction =
  | { type: 'patch'; patch: Partial<ProfilePageState> }
  | { type: 'resetProfile'; user: AuthUser };

export const fieldClassName =
  'app-text-body w-full rounded-md border border-app-border bg-app-bg px-3 py-2 text-app-ink transition-colors focus:border-app-accent focus:outline-none';

export function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }

  if (typeof error === 'string') {
    return error;
  }

  return fallback;
}

function resolveDefaultWorkspaceId(user: AuthUser | null | undefined): string {
  const defaultWorkspaceId = user?.default_workspace_id ?? '';
  if (!defaultWorkspaceId) {
    return '';
  }
  return user?.workspaces.some(
    (workspace) => workspace.id === defaultWorkspaceId,
  )
    ? defaultWorkspaceId
    : '';
}

export function createInitialProfilePageState(
  user: AuthUser,
  initialTab: SettingsSection,
): ProfilePageState {
  return {
    activeSection: initialTab,
    displayName: user.display_name,
    fullName: user.full_name,
    themePreference: user.theme_preference,
    timeZone: normalizeTimeZone(user.time_zone),
    locale: normalizeLocale(user.locale),
    dateFormat: normalizeDateFormatPreference(user.date_format),
    defaultWorkspaceId: resolveDefaultWorkspaceId(user),
    submitting: false,
    message: null,
    error: null,
    currentPassword: '',
    newPassword: '',
    sessions: [],
    loadingSessions: false,
  };
}

export function profilePageReducer(
  state: ProfilePageState,
  action: ProfilePageAction,
): ProfilePageState {
  switch (action.type) {
    case 'patch':
      return { ...state, ...action.patch };
    case 'resetProfile':
      return {
        ...state,
        displayName: action.user.display_name,
        fullName: action.user.full_name,
        timeZone: normalizeTimeZone(action.user.time_zone),
        locale: normalizeLocale(action.user.locale),
        dateFormat: normalizeDateFormatPreference(action.user.date_format),
        defaultWorkspaceId: resolveDefaultWorkspaceId(action.user),
        message: null,
        error: null,
      };
  }
}

export function getUserInitials(name: string) {
  return (
    name
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase() ?? '')
      .join('') || 'ID'
  );
}

export function prepareProfilePreferenceSave(
  state: ProfilePageState,
  change: ProfilePreferenceChange,
): ProfilePreferenceSavePlan | null {
  if (change.type === 'theme') {
    if (change.value === state.themePreference) return null;
    return {
      optimisticPatch: {
        error: null,
        message: null,
        themePreference: change.value,
      },
      payload: { theme_preference: change.value },
      rollbackPatch: { themePreference: state.themePreference },
    };
  }

  if (change.type === 'locale') {
    const nextLocale = normalizeLocale(change.value);
    if (nextLocale === state.locale) return null;
    return {
      optimisticPatch: { error: null, locale: nextLocale, message: null },
      payload: { locale: nextLocale },
      rollbackPatch: { locale: state.locale },
      sync: { kind: 'locale', next: nextLocale, previous: state.locale },
    };
  }

  if (change.type === 'timeZone') {
    const nextTimeZone = normalizeTimeZone(change.value);
    if (nextTimeZone === state.timeZone) return null;
    return {
      optimisticPatch: {
        error: null,
        message: null,
        timeZone: nextTimeZone,
      },
      payload: { time_zone: nextTimeZone },
      rollbackPatch: { timeZone: state.timeZone },
    };
  }

  if (change.type === 'dateFormat') {
    const nextDateFormat = normalizeDateFormatPreference(change.value);
    if (nextDateFormat === state.dateFormat) return null;
    return {
      optimisticPatch: {
        dateFormat: nextDateFormat,
        error: null,
        message: null,
      },
      payload: { date_format: nextDateFormat },
      rollbackPatch: { dateFormat: state.dateFormat },
    };
  }

  const nextDefaultWorkspaceId = change.value.trim();
  if (nextDefaultWorkspaceId === state.defaultWorkspaceId) return null;
  return {
    optimisticPatch: {
      defaultWorkspaceId: nextDefaultWorkspaceId,
      error: null,
      message: null,
    },
    payload: { default_workspace_id: nextDefaultWorkspaceId || null },
    rollbackPatch: { defaultWorkspaceId: state.defaultWorkspaceId },
  };
}

export function prepareProfileDetailsSave(
  state: ProfilePageState,
): ProfileDetailsSavePlan {
  return {
    startPatch: { error: null, message: null, submitting: true },
    payload: {
      date_format: state.dateFormat,
      display_name: state.displayName.trim(),
      full_name: state.fullName.trim(),
      locale: state.locale,
      theme_preference: state.themePreference,
      time_zone: state.timeZone,
    },
    successPatch: (message) => ({ message }),
    failurePatch: (caughtError, fallback) => ({
      error: getErrorMessage(caughtError, fallback),
    }),
    completePatch: { submitting: false },
  };
}

export function preparePasswordChange(
  state: ProfilePageState,
): PasswordChangePlan {
  return {
    startPatch: { error: null, message: null },
    payload: {
      current_password: state.currentPassword,
      new_password: state.newPassword,
    },
    successPatch: (message) => ({
      currentPassword: '',
      message,
      newPassword: '',
    }),
    failurePatch: (caughtError, fallback) => ({
      error: getErrorMessage(caughtError, fallback),
    }),
  };
}

export function selectVisibleAuthSessions(
  sessions: AuthSessionItem[],
  visibleOtherSessionLimit = 3,
): VisibleAuthSessions {
  const activeSessions = sessions.filter((session) => !session.revoked_at);
  const currentSessions = activeSessions.filter(
    (session) => session.is_current,
  );
  const otherSessions = activeSessions
    .filter((session) => !session.is_current)
    .slice(0, visibleOtherSessionLimit);
  const shownSessions = [...currentSessions, ...otherSessions];

  return {
    hiddenCount: activeSessions.length - shownSessions.length,
    shownSessions,
  };
}
