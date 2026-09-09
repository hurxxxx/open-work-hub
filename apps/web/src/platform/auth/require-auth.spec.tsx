import { createAuthUser } from '../../../tests/fixtures/company';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { useEffect } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthContext, type AuthContextValue } from './auth-context';
import { RequireAuth } from './require-auth';
const mock = vi.hoisted(() => ({
  t: (key: string) => key,
  error: vi.fn(),
  mounted: vi.fn(),
}));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: mock.t, i18n: { language: 'en-US' } }),
}));
vi.mock('@open-work-hub/ui', async (original) => ({
  ...(await original<typeof import('@open-work-hub/ui')>()),
  useFeedback: () => ({ error: mock.error }),
}));
const account = createAuthUser({
  id: 'account',
  must_change_password: true,
  time_zone: 'UTC',
  locale: 'en-US',
  date_format: 'iso',
  theme_preference: 'system',
});
function ProtectedContent() {
  useEffect(() => mock.mounted(), []);
  return <p>protected app</p>;
}
function content(auth: AuthContextValue) {
  return (
    <AuthContext value={auth}>
      <MemoryRouter>
        <RequireAuth>
          <ProtectedContent />
        </RequireAuth>
      </MemoryRouter>
    </AuthContext>
  );
}
beforeEach(() => vi.clearAllMocks());
describe('required password rotation boundary', () => {
  it('does not mount app providers until server identity confirms password rotation', async () => {
    let resolveChange!: () => void;
    const auth = {
      status: 'authenticated',
      user: account,
      token: 'token',
      changePassword: vi.fn(
        () =>
          new Promise<void>((resolve) => {
            resolveChange = resolve;
          }),
      ),
      logout: vi.fn(),
    } as unknown as AuthContextValue;
    const result = render(content(auth));
    expect(mock.mounted).not.toHaveBeenCalled();
    expect(screen.queryByText('protected app')).toBeNull();
    expect(screen.queryByText('auth:settings.activeSessions')).toBeNull();
    fireEvent.change(screen.getByLabelText('auth:settings.currentPassword'), {
      target: { value: 'old-example-Password' },
    });
    fireEvent.change(screen.getByLabelText('auth:settings.newPassword'), {
      target: { value: 'new-example-Password' },
    });
    fireEvent.change(
      screen.getByLabelText('auth:settings.newPasswordConfirm'),
      { target: { value: 'new-example-Password' } },
    );
    const form = screen
      .getByLabelText('auth:settings.currentPassword')
      .closest('form');
    if (!form) throw new Error('Password change form missing');
    fireEvent.submit(form);
    await waitFor(() => expect(auth.changePassword).toHaveBeenCalledTimes(1));
    expect(mock.mounted).not.toHaveBeenCalled();
    await act(async () => resolveChange());
    expect(mock.mounted).not.toHaveBeenCalled();
    result.rerender(
      content({ ...auth, user: { ...account, must_change_password: false } }),
    );
    await screen.findByText('protected app');
    expect(mock.mounted).toHaveBeenCalledTimes(1);
  });
  it('keeps protected content blocked after a rejected change', async () => {
    const auth = {
      status: 'authenticated',
      user: account,
      token: 'token',
      changePassword: vi.fn().mockRejectedValue(new Error('Rejected')),
      logout: vi.fn(),
    } as unknown as AuthContextValue;
    render(content(auth));
    for (const label of [
      'currentPassword',
      'newPassword',
      'newPasswordConfirm',
    ])
      fireEvent.change(screen.getByLabelText(`auth:settings.${label}`), {
        target: { value: 'example-Password' },
      });
    const form = screen
      .getByLabelText('auth:settings.currentPassword')
      .closest('form');
    if (!form) throw new Error('Password change form missing');
    fireEvent.submit(form);
    await waitFor(() => expect(mock.error).toHaveBeenCalledWith('Rejected'));
    expect(mock.mounted).not.toHaveBeenCalled();
    expect(screen.queryByText('protected app')).toBeNull();
  });
});
