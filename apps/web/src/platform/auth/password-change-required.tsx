import { Button, useFeedback } from '@open-work-hub/ui';
import { useReducer, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import type { AuthUser } from './auth-api';
import { useAuth } from './auth-context';
import { SecuritySettingsSection } from './SecuritySettingsSection';
import {
  createInitialProfilePageState,
  preparePasswordChange,
  profilePageReducer,
} from './settings-page-model';

/** Rendered before any protected app provider or background request mounts. */
export function PasswordChangeRequired({ user }: { user: AuthUser }) {
  const auth = useAuth();
  const { t, i18n } = useTranslation('auth');
  const feedback = useFeedback();
  const [state, dispatch] = useReducer(profilePageReducer, user, (current) =>
    createInitialProfilePageState(current, 'security'),
  );
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (state.submitting) return;
    if (state.newPassword !== state.newPasswordConfirm) {
      feedback.error(t('errors.passwordMismatch'));
      return;
    }
    dispatch({ type: 'patch', patch: { submitting: true } });
    try {
      await auth.changePassword(preparePasswordChange(state).payload);
    } catch (error) {
      feedback.error(
        error instanceof Error
          ? error.message
          : t('settings.passwordChangeFailed'),
      );
    } finally {
      dispatch({ type: 'patch', patch: { submitting: false } });
    }
  }
  return (
    <main className="mx-auto min-h-screen max-w-xl px-6 py-10">
      <SecuritySettingsSection
        dispatch={dispatch}
        i18nLanguage={i18n.language}
        onPasswordSubmit={(event) => void submit(event)}
        onRevoke={() => Promise.resolve()}
        showSessions={false}
        state={state}
        t={t}
        user={user}
      />
      <Button
        disabled={state.submitting}
        onClick={() => void auth.logout()}
        variant="secondary"
      >
        {t('common:actions.signOut')}
      </Button>
    </main>
  );
}
