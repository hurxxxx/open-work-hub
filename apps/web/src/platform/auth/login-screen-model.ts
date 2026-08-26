export type LoginMode = 'login' | 'signup';
export type LoginTextField =
  | 'fullName'
  | 'loginId'
  | 'email'
  | 'password'
  | 'passwordConfirm';

export type DevLoginAccountLike = {
  account_key: string;
  category: string;
  description: string;
  email: string;
  label: string;
};

export type DevLoginAccountGroup<
  TAccount extends DevLoginAccountLike = DevLoginAccountLike,
> = {
  category: string;
  accounts: TAccount[];
};

export type LoginModeFlags = {
  isSetupMode: boolean;
  isSignupMode: boolean;
  hasDevAccountButtons: boolean;
};

export type LoginFormState = {
  mode: LoginMode;
  fullName: string;
  loginId: string;
  email: string;
  password: string;
  passwordConfirm: string;
  submitting: boolean;
};

export type LoginFormAction =
  | { type: 'fieldChanged'; field: LoginTextField; value: string }
  | { type: 'modeChanged'; mode: LoginMode }
  | { type: 'submitStarted' }
  | { type: 'submitFinished' };

export const INITIAL_LOGIN_FORM_STATE: LoginFormState = {
  mode: 'login',
  fullName: '',
  loginId: '',
  email: '',
  password: '',
  passwordConfirm: '',
  submitting: false,
};

export function loginFormReducer(
  state: LoginFormState,
  action: LoginFormAction,
): LoginFormState {
  switch (action.type) {
    case 'fieldChanged':
      return { ...state, [action.field]: action.value };
    case 'modeChanged':
      return { ...state, mode: action.mode };
    case 'submitStarted':
      return { ...state, submitting: true };
    case 'submitFinished':
      return { ...state, submitting: false };
    default:
      return state;
  }
}

export function getLoginErrorMessage(
  caughtError: unknown,
  fallback: string,
): string {
  if (caughtError instanceof Error && caughtError.message) {
    return caughtError.message;
  }

  return fallback;
}

export function groupDevLoginAccounts<TAccount extends DevLoginAccountLike>(
  accounts: readonly TAccount[],
): DevLoginAccountGroup<TAccount>[] {
  const groups: DevLoginAccountGroup<TAccount>[] = [];
  const groupByCategory = new Map<string, TAccount[]>();
  for (const account of accounts) {
    let group = groupByCategory.get(account.category);
    if (!group) {
      group = [];
      groupByCategory.set(account.category, group);
      groups.push({ category: account.category, accounts: group });
    }
    group.push(account);
  }
  return groups;
}

export function getLoginModeFlags({
  devAccountGroupCount,
  mode,
  requiresSetup,
}: {
  devAccountGroupCount: number;
  mode: LoginMode;
  requiresSetup: boolean;
}): LoginModeFlags {
  const isSetupMode = requiresSetup;
  const isSignupMode = !requiresSetup && mode === 'signup';
  return {
    isSetupMode,
    isSignupMode,
    hasDevAccountButtons:
      !isSetupMode && !isSignupMode && devAccountGroupCount > 0,
  };
}
