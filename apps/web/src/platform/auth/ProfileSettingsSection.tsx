import type { Dispatch, FormEvent } from 'react';
import { Button } from '@open-work-hub/ui/primitives/button';
import { cn } from '@/src/lib/utils';

import type { AuthUser } from './auth-api';
import { SettingsFieldRow } from './SettingsFieldRow';
import { SettingsSectionHeader } from './SettingsSectionHeader';
import {
  fieldClassName,
  getUserInitials,
  type ProfilePageAction,
  type ProfilePageState,
  type SettingsTranslator,
} from './settings-page-model';

export function ProfileSettingsSection({
  dispatch,
  onSubmit,
  state,
  t,
  user,
}: {
  dispatch: Dispatch<ProfilePageAction>;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  state: ProfilePageState;
  t: SettingsTranslator;
  user: AuthUser;
}) {
  return (
    <div>
      <SettingsSectionHeader
        title={t('auth:settings.profile')}
        description={t('auth:settings.manageProfile')}
      />

      <form onSubmit={onSubmit}>
        <div className="border-t border-app-border">
          <SettingsFieldRow label={t('auth:settings.avatar')}>
            <div className="flex items-center gap-4">
              <div className="app-text-title-md flex size-12 items-center justify-center rounded-full bg-orange-500 font-bold text-white">
                {getUserInitials(user.display_name || user.full_name)}
              </div>
              <div className="app-text-body">
                <p className="font-medium text-app-ink">
                  {user.display_name || user.full_name}
                </p>
                <p className="app-text-caption text-app-ink/55">{user.email}</p>
              </div>
            </div>
          </SettingsFieldRow>

          <SettingsFieldRow label={t('auth:settings.displayName')}>
            <input
              aria-label={t('auth:settings.displayName')}
              className={fieldClassName}
              onChange={(event) =>
                dispatch({
                  type: 'patch',
                  patch: { displayName: event.target.value },
                })
              }
              value={state.displayName}
            />
          </SettingsFieldRow>

          <SettingsFieldRow label={t('auth:settings.fullName')}>
            <input
              aria-label={t('auth:settings.fullName')}
              className={fieldClassName}
              onChange={(event) =>
                dispatch({
                  type: 'patch',
                  patch: { fullName: event.target.value },
                })
              }
              value={state.fullName}
            />
          </SettingsFieldRow>

          <SettingsFieldRow
            label={t('auth:settings.loginId')}
            description={t('auth:settings.loginIdChangeHint')}
          >
            <input
              aria-label={t('auth:settings.loginId')}
              className={cn(fieldClassName, 'opacity-60')}
              disabled
              readOnly
              value={user.login_id}
            />
          </SettingsFieldRow>

          <SettingsFieldRow
            label={t('auth:settings.emailAddress')}
            description={t('auth:settings.emailChangeHint')}
          >
            <input
              aria-label={t('auth:settings.emailAddress')}
              className={cn(fieldClassName, 'opacity-60')}
              disabled
              readOnly
              value={user.email}
            />
          </SettingsFieldRow>

          <SettingsFieldRow label={t('auth:settings.role')}>
            <span className="app-text-body text-app-ink">
              {(user.system_roles ?? []).length > 0
                ? user.system_roles.join(', ')
                : 'Member'}
            </span>
          </SettingsFieldRow>
        </div>

        <div className="flex justify-end gap-3 pt-6">
          <Button
            variant="ghost"
            type="button"
            onClick={() => dispatch({ type: 'resetProfile', user })}
          >
            {t('common:actions.reset')}
          </Button>
          <Button variant="primary" type="submit" disabled={state.submitting}>
            {state.submitting
              ? t('common:actions.saving')
              : t('common:actions.saveChanges')}
          </Button>
        </div>
      </form>
    </div>
  );
}
