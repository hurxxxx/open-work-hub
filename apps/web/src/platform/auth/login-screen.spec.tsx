import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { LoginScreen } from './login-screen';

const testContext = vi.hoisted(() => ({
  feedbackError: vi.fn(),
  login: vi.fn(),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('@open-work-hub/ui/feedback/feedback-provider', () => ({
  useFeedback: () => ({ error: testContext.feedbackError }),
}));

vi.mock('./auth-context', () => ({
  useAuth: () => ({
    bootstrapError: null,
    devAdminLoginAvailable: false,
    devLoginAccounts: [],
    login: testContext.login,
    loginAsDevelopmentAccount: vi.fn(),
    loginAsDevelopmentAdmin: vi.fn(),
    requiresSetup: false,
    setupFirstUser: vi.fn(),
    signup: vi.fn(),
  }),
}));

beforeEach(() => {
  testContext.login.mockRejectedValue(
    new Error('ID 또는 비밀번호가 올바르지 않습니다.'),
  );
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('LoginScreen', () => {
  it('reports invalid credentials through global feedback instead of inline content', async () => {
    render(<LoginScreen />);

    fireEvent.change(screen.getByLabelText('login.loginId'), {
      target: { value: 'administrator' },
    });
    fireEvent.change(screen.getByLabelText('login.password'), {
      target: { value: 'wrong-password' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'login.signIn' }));

    await waitFor(() =>
      expect(testContext.feedbackError).toHaveBeenCalledWith(
        'ID 또는 비밀번호가 올바르지 않습니다.',
      ),
    );
    expect(
      screen.queryByText('ID 또는 비밀번호가 올바르지 않습니다.'),
    ).toBeNull();
  });
});
