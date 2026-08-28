import { useEffect, useReducer } from 'react';
import type { FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { syncLocale } from '@/src/platform/i18n';
import type { AuthUser, ThemePreference } from './auth-api';
import type { AuthContextValue } from './auth-context';
import {
  createInitialProfilePageState,
  getErrorMessage,
  preparePasswordChange,
  prepareProfileDetailsSave,
  prepareProfilePreferenceSave,
  profilePageReducer,
  type ProfilePreferenceChange,
  type SettingsSection,
} from './settings-page-model';

export function useProfilePageController({
  auth,
  initialTab,
  user,
}: {
  auth: AuthContextValue;
  initialTab: SettingsSection;
  user: AuthUser;
}) {
  const { t, i18n } = useTranslation(['auth', 'common']);
  const [state, dispatch] = useReducer(
    profilePageReducer,
    { user, initialTab },
    ({ user, initialTab }) => createInitialProfilePageState(user, initialTab),
  );
  const { listSessions } = auth;

  useEffect(() => {
    if (state.activeSection !== 'security') return;
    let cancelled = false;

    async function loadSessions() {
      dispatch({ type: 'patch', patch: { loadingSessions: true } });
      try {
        const items = await listSessions();
        if (!cancelled) {
          dispatch({
            type: 'patch',
            patch: { loadingSessions: false, sessions: items },
          });
        }
      } catch (caughtError) {
        if (!cancelled) {
          dispatch({
            type: 'patch',
            patch: {
              error: getErrorMessage(
                caughtError,
                t('auth:settings.sessionsLoadFailed'),
              ),
              loadingSessions: false,
            },
          });
        }
      }
    }

    void loadSessions();
    return () => {
      cancelled = true;
    };
  }, [listSessions, state.activeSection, t]);

  const handleSectionChange = (section: SettingsSection) => {
    dispatch({
      type: 'patch',
      patch: { activeSection: section, error: null, message: null },
    });
  };

  const handleProfileSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const plan = prepareProfileDetailsSave(state);
    dispatch({ type: 'patch', patch: plan.startPatch });
    try {
      await auth.updatePreferences(plan.payload);
      dispatch({
        type: 'patch',
        patch: plan.successPatch(t('auth:settings.saved')),
      });
    } catch (caughtError) {
      dispatch({
        type: 'patch',
        patch: plan.failurePatch(caughtError, t('auth:settings.saveFailed')),
      });
    } finally {
      dispatch({ type: 'patch', patch: plan.completePatch });
    }
  };

  const handlePasswordSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const plan = preparePasswordChange(state);
    dispatch({ type: 'patch', patch: plan.startPatch });
    try {
      await auth.changePassword(plan.payload);
      dispatch({
        type: 'patch',
        patch: plan.successPatch(t('auth:settings.passwordChanged')),
      });
    } catch (caughtError) {
      dispatch({
        type: 'patch',
        patch: plan.failurePatch(
          caughtError,
          t('auth:settings.passwordChangeFailed'),
        ),
      });
    }
  };

  const handleRevoke = async (sessionId: string) => {
    dispatch({ type: 'patch', patch: { error: null, message: null } });
    try {
      await auth.revokeSession(sessionId);
      const items = await auth.listSessions();
      dispatch({
        type: 'patch',
        patch: { message: t('auth:settings.sessionRevoked'), sessions: items },
      });
    } catch (caughtError) {
      dispatch({
        type: 'patch',
        patch: {
          error: getErrorMessage(
            caughtError,
            t('auth:settings.sessionRevokeFailed'),
          ),
        },
      });
    }
  };

  const saveProfilePreference = async (change: ProfilePreferenceChange) => {
    const plan = prepareProfilePreferenceSave(state, change);
    if (!plan) return;
    dispatch({ type: 'patch', patch: plan.optimisticPatch });
    if (plan.sync?.kind === 'locale') {
      syncLocale(plan.sync.next);
    }
    try {
      await auth.updatePreferences(plan.payload);
    } catch (caughtError) {
      if (plan.sync?.kind === 'locale') {
        syncLocale(plan.sync.previous);
      }
      dispatch({
        type: 'patch',
        patch: {
          ...plan.rollbackPatch,
          error: getErrorMessage(caughtError, t('auth:settings.saveFailed')),
        },
      });
    }
  };

  const saveThemePreference = async (nextThemePreference: ThemePreference) => {
    await saveProfilePreference({ type: 'theme', value: nextThemePreference });
  };

  const saveLocalePreference = async (nextLocaleValue: string) => {
    await saveProfilePreference({ type: 'locale', value: nextLocaleValue });
  };

  const saveTimeZonePreference = async (nextTimeZoneValue: string) => {
    await saveProfilePreference({ type: 'timeZone', value: nextTimeZoneValue });
  };

  const saveDateFormatPreference = async (nextDateFormatValue: string) => {
    await saveProfilePreference({
      type: 'dateFormat',
      value: nextDateFormatValue,
    });
  };

  return {
    dispatch,
    handlePasswordSubmit,
    handleProfileSubmit,
    handleRevoke,
    handleSectionChange,
    i18nLanguage: i18n.language,
    saveDateFormatPreference,
    saveLocalePreference,
    saveThemePreference,
    saveTimeZonePreference,
    state,
    t,
  };
}
