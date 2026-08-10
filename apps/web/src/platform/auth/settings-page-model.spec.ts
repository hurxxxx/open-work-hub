import { describe, expect, it } from 'vitest';

import type { AuthSessionItem } from './auth-api';
import type { ProfilePageState } from './settings-page-model';
import {
  preparePasswordChange,
  prepareProfileDetailsSave,
  prepareProfilePreferenceSave,
  selectVisibleAuthSessions,
} from './settings-page-model';

function state(overrides: Partial<ProfilePageState> = {}): ProfilePageState {
  return {
    activeSection: 'appearance',
    currentPassword: '',
    dateFormat: 'korean',
    defaultWorkspaceId: 'workspace-a',
    displayName: 'Member',
    error: 'previous error',
    fullName: 'Open ALM Member',
    jobTitle: '',
    loadingSessions: false,
    locale: 'ko-KR',
    message: 'previous message',
    newPassword: '',
    sessions: [],
    submitting: false,
    themePreference: 'system',
    timeZone: 'Asia/Seoul',
    ...overrides,
  };
}

function session(
  id: string,
  overrides: Partial<AuthSessionItem> = {},
): AuthSessionItem {
  return {
    created_at: '2026-05-01T00:00:00Z',
    expires_at: '2026-06-01T00:00:00Z',
    id,
    ip_address: null,
    is_current: false,
    last_seen_at: '2026-05-02T00:00:00Z',
    revoked_at: null,
    user_agent: null,
    ...overrides,
  };
}

describe('settings page model', () => {
  it('plans theme preference saves and no-ops unchanged values', () => {
    expect(
      prepareProfilePreferenceSave(state(), {
        type: 'theme',
        value: 'system',
      }),
    ).toBeNull();

    expect(
      prepareProfilePreferenceSave(state(), {
        type: 'theme',
        value: 'dark',
      }),
    ).toEqual({
      optimisticPatch: {
        error: null,
        message: null,
        themePreference: 'dark',
      },
      payload: { theme_preference: 'dark' },
      rollbackPatch: { themePreference: 'system' },
    });
  });

  it('normalizes locale saves and includes sync rollback metadata', () => {
    expect(
      prepareProfilePreferenceSave(state(), {
        type: 'locale',
        value: 'en-US',
      }),
    ).toEqual({
      optimisticPatch: {
        error: null,
        locale: 'en-US',
        message: null,
      },
      payload: { locale: 'en-US' },
      rollbackPatch: { locale: 'ko-KR' },
      sync: { kind: 'locale', next: 'en-US', previous: 'ko-KR' },
    });
  });

  it('normalizes timezone and date format saves', () => {
    expect(
      prepareProfilePreferenceSave(state(), {
        type: 'timeZone',
        value: 'UTC',
      }),
    ).toMatchObject({
      optimisticPatch: { error: null, message: null, timeZone: 'UTC' },
      payload: { time_zone: 'UTC' },
      rollbackPatch: { timeZone: 'Asia/Seoul' },
    });

    expect(
      prepareProfilePreferenceSave(state(), {
        type: 'dateFormat',
        value: 'iso',
      }),
    ).toEqual({
      optimisticPatch: {
        dateFormat: 'iso',
        error: null,
        message: null,
      },
      payload: { date_format: 'iso' },
      rollbackPatch: { dateFormat: 'korean' },
    });
  });

  it('trims default workspace saves and sends null for blank values', () => {
    expect(
      prepareProfilePreferenceSave(state(), {
        type: 'defaultWorkspace',
        value: ' workspace-b ',
      }),
    ).toEqual({
      optimisticPatch: {
        defaultWorkspaceId: 'workspace-b',
        error: null,
        message: null,
      },
      payload: { default_workspace_id: 'workspace-b' },
      rollbackPatch: { defaultWorkspaceId: 'workspace-a' },
    });

    expect(
      prepareProfilePreferenceSave(state(), {
        type: 'defaultWorkspace',
        value: '   ',
      })?.payload,
    ).toEqual({ default_workspace_id: null });
  });

  it('plans full profile detail saves with trimmed identity fields', () => {
    const plan = prepareProfileDetailsSave(
      state({
        displayName: '  Open ALM  ',
        fullName: '  Open ALM Member  ',
        jobTitle: '  Builder  ',
        submitting: false,
      }),
    );

    expect(plan.startPatch).toEqual({
      error: null,
      message: null,
      submitting: true,
    });
    expect(plan.payload).toEqual({
      date_format: 'korean',
      display_name: 'Open ALM',
      full_name: 'Open ALM Member',
      job_title: 'Builder',
      locale: 'ko-KR',
      theme_preference: 'system',
      time_zone: 'Asia/Seoul',
    });
    expect(plan.successPatch('Saved')).toEqual({ message: 'Saved' });
    expect(plan.failurePatch(new Error('Nope'), 'Fallback')).toEqual({
      error: 'Nope',
    });
    expect(plan.completePatch).toEqual({ submitting: false });
  });

  it('plans password changes and clears password fields after success', () => {
    const plan = preparePasswordChange(
      state({
        currentPassword: 'old-password',
        newPassword: 'new-password',
      }),
    );

    expect(plan.startPatch).toEqual({ error: null, message: null });
    expect(plan.payload).toEqual({
      current_password: 'old-password',
      new_password: 'new-password',
    });
    expect(plan.successPatch('Changed')).toEqual({
      currentPassword: '',
      message: 'Changed',
      newPassword: '',
    });
    expect(plan.failurePatch('Bad password', 'Fallback')).toEqual({
      error: 'Bad password',
    });
  });

  it('selects visible active sessions with current sessions first', () => {
    const result = selectVisibleAuthSessions([
      session('other-1'),
      session('revoked', { revoked_at: '2026-05-03T00:00:00Z' }),
      session('current', { is_current: true }),
      session('other-2'),
      session('other-3'),
      session('other-4'),
    ]);

    expect(result.shownSessions.map((item) => item.id)).toEqual([
      'current',
      'other-1',
      'other-2',
      'other-3',
    ]);
    expect(result.hiddenCount).toBe(1);
  });
});
