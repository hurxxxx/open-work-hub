import type { Dispatch, FormEvent } from 'react';
import { Button } from '@open-alm/ui/primitives/button';
import { InlineNotice } from '@open-alm/ui/feedback/inline-notice';

import { normalizeTimeZone } from '@/src/platform/time/time-utils';
import { SettingsFieldRow } from './SettingsFieldRow';
import { SettingsSectionHeader } from './SettingsSectionHeader';
import { SessionCard } from './SessionCard';
import {
  fieldClassName,
  selectVisibleAuthSessions,
  type ProfilePageAction,
  type ProfilePageState,
  type SettingsTranslator,
} from './settings-page-model';
import type { AuthUser } from './auth-api';

export function SecuritySettingsSection({
  dispatch,
  i18nLanguage,
  onPasswordSubmit,
  onRevoke,
  state,
  t,
  user,
}: {
  dispatch: Dispatch<ProfilePageAction>;
  i18nLanguage: string;
  onPasswordSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onRevoke: (sessionId: string) => Promise<void>;
  state: ProfilePageState;
  t: SettingsTranslator;
  user: AuthUser;
}) {
  const { hiddenCount, shownSessions } = selectVisibleAuthSessions(
    state.sessions,
  );
  const passwordChangeAvailable = user.auth_provider !== 'groupware';

  return (
    <div>
      <SettingsSectionHeader
        title={t('auth:settings.security')}
        description={t(
          passwordChangeAvailable
            ? 'auth:settings.managePassword'
            : 'auth:settings.reviewSessions',
        )}
      />

      {passwordChangeAvailable ? (
        <div className="border-t border-app-border">
          {user.must_change_password ? (
            <div className="py-4">
              <InlineNotice tone="warning">
                {t('auth:settings.passwordRequired')}
              </InlineNotice>
            </div>
          ) : null}

          <form onSubmit={onPasswordSubmit}>
            <SettingsFieldRow label={t('auth:settings.currentPassword')}>
              <input
                aria-label={t('auth:settings.currentPassword')}
                className={fieldClassName}
                onChange={(event) =>
                  dispatch({
                    type: 'patch',
                    patch: { currentPassword: event.target.value },
                  })
                }
                placeholder="********"
                type="password"
                value={state.currentPassword}
              />
            </SettingsFieldRow>

            <SettingsFieldRow label={t('auth:settings.newPassword')}>
              <input
                aria-label={t('auth:settings.newPassword')}
                className={fieldClassName}
                onChange={(event) =>
                  dispatch({
                    type: 'patch',
                    patch: { newPassword: event.target.value },
                  })
                }
                placeholder="********"
                type="password"
                value={state.newPassword}
              />
            </SettingsFieldRow>

            <div className="py-4">
              <Button variant="primary" type="submit">
                {t('auth:settings.updatePassword')}
              </Button>
            </div>
          </form>
        </div>
      ) : null}

      <div className="mt-8">
        <h3 className="app-text-title-md mb-1 text-app-ink">
          {t('auth:settings.activeSessions')}
        </h3>
        <p className="app-text-caption mb-4 text-app-ink/55">
          {t('auth:settings.reviewSessions')}
        </p>
        {state.loadingSessions ? (
          <p className="app-text-body text-app-ink/55">
            {t('common:feedback.loading')}
          </p>
        ) : (
          <div className="grid gap-2">
            {shownSessions.map((session) => (
              <SessionCard
                key={session.id}
                onRevoke={onRevoke}
                session={session}
                locale={i18nLanguage}
                timeZone={normalizeTimeZone(user.time_zone)}
                t={t}
              />
            ))}
            {hiddenCount > 0 ? (
              <p className="app-text-caption py-2 text-center text-app-ink/55">
                {t('auth:settings.sessionsMore', {
                  count: hiddenCount,
                })}
              </p>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}
