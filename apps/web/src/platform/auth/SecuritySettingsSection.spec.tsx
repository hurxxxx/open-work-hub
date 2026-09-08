import { createAuthUser } from '../../../tests/fixtures/company';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { SecuritySettingsSection } from './SecuritySettingsSection';
import { createInitialProfilePageState } from './settings-page-model';

afterEach(cleanup);

describe('SecuritySettingsSection', () => {
  it('requires the new password to be entered twice', () => {
    const dispatch = vi.fn();
    const state = {
      ...createInitialProfilePageState(createAuthUser(), 'security'),
      currentPassword: '',
      loadingSessions: false,
      newPassword: '',
      newPasswordConfirm: '',
      sessions: [],
    };

    render(
      <SecuritySettingsSection
        dispatch={dispatch}
        i18nLanguage="ko-KR"
        onPasswordSubmit={vi.fn()}
        onRevoke={vi.fn()}
        state={state}
        t={(key) => key}
        user={createAuthUser({
          must_change_password: false,
          time_zone: 'Asia/Seoul',
        })}
      />,
    );

    const newPassword = screen.getByLabelText('auth:settings.newPassword');
    const confirmation = screen.getByLabelText(
      'auth:settings.newPasswordConfirm',
    );

    expect(newPassword.hasAttribute('required')).toBe(true);
    expect(confirmation.hasAttribute('required')).toBe(true);
    expect(newPassword.getAttribute('autocomplete')).toBe('new-password');
    expect(confirmation.getAttribute('autocomplete')).toBe('new-password');

    fireEvent.change(confirmation, { target: { value: 'new-password' } });
    expect(dispatch).toHaveBeenCalledWith({
      type: 'patch',
      patch: { newPasswordConfirm: 'new-password' },
    });
  });
});
