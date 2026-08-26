import { useEffect, useReducer, useState, type FormEvent } from 'react';
import { LazyMotion, domAnimation, m } from 'motion/react';
import {
  ArrowRight,
  AtSign,
  Eye,
  EyeOff,
  Lock,
  Mail,
  ShieldCheck,
  User,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { InlineNotice } from '@open-work-hub/ui/feedback/inline-notice';
import { useFeedback } from '@open-work-hub/ui/feedback/feedback-provider';

import { useAuth } from './auth-context';
import {
  getLoginErrorMessage,
  getLoginModeFlags,
  groupDevLoginAccounts,
  INITIAL_LOGIN_FORM_STATE,
  loginFormReducer,
  type DevLoginAccountGroup,
  type LoginFormState,
  type LoginModeFlags,
  type LoginTextField,
} from './login-screen-model';

const fieldClassName =
  'w-full rounded-lg border border-app-border bg-app-bg-strong py-2.5 pr-4 app-text-body text-app-ink transition-all placeholder:text-app-ink/45 focus:border-app-accent focus:outline-none focus:ring-1 focus:ring-app-accent';

function PasswordField({
  autoComplete,
  id,
  label,
  minLength,
  onChange,
  required = true,
  value,
}: {
  autoComplete: string;
  id: string;
  label: string;
  minLength?: number;
  onChange: (value: string) => void;
  required?: boolean;
  value: string;
}) {
  const { t } = useTranslation('auth');
  const [visible, setVisible] = useState(false);
  const visibilityLabel = t(
    visible ? 'login.hidePasswordField' : 'login.showPasswordField',
    {
      field: label,
    },
  );

  return (
    <div className="relative">
      <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
        <Lock size={16} className="text-app-ink/55" />
      </div>
      <input
        aria-label={label}
        autoComplete={autoComplete}
        className={`${fieldClassName} pl-10 pr-11`}
        id={id}
        minLength={minLength}
        onChange={(event) => onChange(event.target.value)}
        placeholder="••••••••"
        required={required}
        type={visible ? 'text' : 'password'}
        value={value}
      />
      <button
        aria-label={visibilityLabel}
        aria-pressed={visible}
        className="absolute inset-y-0 right-0 flex w-10 items-center justify-center rounded-r-lg text-app-ink/55 transition-colors hover:text-app-ink focus:outline-none focus:ring-1 focus:ring-inset focus:ring-app-accent"
        onClick={() => setVisible((current) => !current)}
        title={visibilityLabel}
        type="button"
      >
        {visible ? <EyeOff size={16} /> : <Eye size={16} />}
      </button>
    </div>
  );
}

function DevAccountsPanel({
  groups,
  submitting,
  onLogin,
}: {
  groups: DevLoginAccountGroup[];
  submitting: boolean;
  onLogin: (accountKey: string) => void;
}) {
  const { t } = useTranslation('auth');

  return (
    <div className="order-2 rounded-2xl border border-app-border bg-app-surface/95 p-4 shadow-xl lg:order-1">
      <div className="mb-4">
        <div className="text-[0.68rem] font-semibold uppercase tracking-[0.12em] text-app-ink/55">
          {t('login.seedAccounts')}
        </div>
        <p className="mt-2 app-text-caption leading-5 text-app-ink/45">
          {t('login.devAccountsDescription')}
        </p>
      </div>

      <div className="space-y-4">
        {groups.map((group) => (
          <div key={group.category} className="space-y-2">
            <div className="text-[0.68rem] font-semibold uppercase tracking-[0.08em] text-app-ink/55">
              {group.category}
            </div>
            <div className="grid gap-2">
              {group.accounts.map((account) => (
                <button
                  key={account.account_key}
                  className="w-full rounded-xl border border-app-border bg-app-bg px-3 py-2.5 text-left transition-colors hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-70"
                  disabled={submitting}
                  onClick={() => onLogin(account.account_key)}
                  type="button"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="truncate text-[0.82rem] font-semibold text-app-ink">
                        {account.label}
                      </div>
                      <div className="mt-0.5 truncate text-[0.68rem] text-app-ink/55">
                        {account.email}
                      </div>
                    </div>
                    <ShieldCheck
                      size={14}
                      className="mt-0.5 shrink-0 text-app-accent"
                    />
                  </div>
                  <div className="mt-2 line-clamp-2 text-[0.7rem] leading-4 text-app-ink/45">
                    {account.description}
                  </div>
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function LoginScreen() {
  const auth = useAuth();
  const feedback = useFeedback();
  const { t } = useTranslation(['auth', 'shell']);
  const [form, dispatch] = useReducer(
    loginFormReducer,
    INITIAL_LOGIN_FORM_STATE,
  );
  const devAccountGroups = groupDevLoginAccounts(auth.devLoginAccounts);
  const modeFlags = getLoginModeFlags({
    devAccountGroupCount: devAccountGroups.length,
    mode: form.mode,
    requiresSetup: auth.requiresSetup,
  });
  const { isSetupMode, isSignupMode, hasDevAccountButtons } = modeFlags;

  useEffect(() => {
    const root = document.documentElement;
    const hadDark = root.classList.contains('dark');
    root.classList.add('dark');

    return () => {
      if (!hadDark) {
        root.classList.remove('dark');
      }
    };
  }, []);

  useEffect(() => {
    const title = isSetupMode
      ? t('auth:login.setupTitle')
      : isSignupMode
        ? t('auth:login.signUp')
        : t('auth:login.signIn');
    document.title = t('shell:documentTitle.app', { app: title });
  }, [isSetupMode, isSignupMode, t]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    dispatch({ type: 'submitStarted' });

    try {
      if (isSetupMode) {
        await auth.setupFirstUser({
          full_name: form.fullName.trim(),
          login_id: form.loginId.trim(),
          email: form.email.trim(),
          password: form.password,
        });
      } else if (isSignupMode) {
        await auth.signup({
          full_name: form.fullName.trim(),
          login_id: form.loginId.trim(),
          email: form.email.trim(),
          password: form.password,
          password_confirm: form.passwordConfirm,
        });
      } else {
        await auth.login({
          login_id: form.loginId.trim(),
          password: form.password,
        });
      }
    } catch (caughtError) {
      feedback.error(
        getLoginErrorMessage(
          caughtError,
          isSetupMode
            ? t('errors.setup')
            : isSignupMode
              ? t('errors.signup')
              : t('errors.login'),
        ),
      );
    } finally {
      dispatch({ type: 'submitFinished' });
    }
  }

  async function handleDevAccountLogin(accountKey: string) {
    dispatch({ type: 'submitStarted' });
    try {
      await auth.loginAsDevelopmentAccount(accountKey);
    } catch (caughtError) {
      feedback.error(getLoginErrorMessage(caughtError, t('errors.devLogin')));
    } finally {
      dispatch({ type: 'submitFinished' });
    }
  }

  async function handleDevAdminLogin() {
    dispatch({ type: 'submitStarted' });
    try {
      await auth.loginAsDevelopmentAdmin();
    } catch (caughtError) {
      feedback.error(
        getLoginErrorMessage(caughtError, t('errors.devAdminLogin')),
      );
    } finally {
      dispatch({ type: 'submitFinished' });
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-app-bg-strong p-4">
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -top-[20%] -left-[10%] size-[50%] rounded-full bg-app-accent/10 blur-[120px]" />
        <div className="absolute top-[60%] -right-[10%] h-[60%] w-[40%] rounded-full bg-app-info/10 blur-[120px]" />
      </div>

      <LazyMotion features={domAnimation}>
        <m.div
          animate={{ opacity: 1, y: 0 }}
          className={`z-10 w-full ${hasDevAccountButtons ? 'max-w-5xl' : 'max-w-md'}`}
          initial={{ opacity: 0, y: 20 }}
          transition={{ duration: 0.5 }}
        >
          <div
            className={`grid gap-4 ${hasDevAccountButtons ? 'lg:grid-cols-[260px_minmax(0,1fr)] lg:items-start' : ''}`}
          >
            {hasDevAccountButtons ? (
              <DevAccountsPanel
                groups={devAccountGroups}
                onLogin={(accountKey) => void handleDevAccountLogin(accountKey)}
                submitting={form.submitting}
              />
            ) : null}

            <LoginFormCard
              auth={auth}
              form={form}
              modeFlags={modeFlags}
              onDevAdminLogin={handleDevAdminLogin}
              onFieldChange={(field, value) =>
                dispatch({ type: 'fieldChanged', field, value })
              }
              onModeChange={(mode) => dispatch({ type: 'modeChanged', mode })}
              onSubmit={handleSubmit}
            />
          </div>
        </m.div>
      </LazyMotion>
    </div>
  );
}

function LoginFormCard({
  auth,
  form,
  modeFlags,
  onDevAdminLogin,
  onFieldChange,
  onModeChange,
  onSubmit,
}: {
  auth: ReturnType<typeof useAuth>;
  form: LoginFormState;
  modeFlags: LoginModeFlags;
  onDevAdminLogin: () => Promise<void>;
  onFieldChange: (field: LoginTextField, value: string) => void;
  onModeChange: (mode: 'login' | 'signup') => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => Promise<void>;
}) {
  const { t } = useTranslation('auth');
  const { isSetupMode, isSignupMode, hasDevAccountButtons } = modeFlags;

  return (
    <div className="order-1 rounded-2xl border border-app-border bg-app-surface p-8 shadow-2xl lg:order-2">
      <div className="mb-8 text-center">
        <div className="mx-auto mb-4 flex size-12 items-center justify-center rounded-xl bg-app-accent text-xl font-bold text-app-accent-fg shadow-lg shadow-app-accent/20">
          ID
        </div>
        <h1 className="mb-2 text-2xl font-bold text-app-ink">
          {isSetupMode
            ? t('login.setupTitle')
            : isSignupMode
              ? t('login.signUp')
              : t('login.signIn')}
        </h1>
        <p className="app-text-body text-app-ink/45">
          {isSetupMode
            ? t('login.setupDescription')
            : isSignupMode
              ? t('login.signupDescription')
              : hasDevAccountButtons
                ? t('login.devAccountsDescription')
                : auth.devAdminLoginAvailable
                  ? t('login.devAdminHint')
                  : t('login.localLoginHint')}
        </p>
      </div>

      <form className="space-y-4" onSubmit={(event) => void onSubmit(event)}>
        {auth.bootstrapError ? (
          <InlineNotice tone="danger">{auth.bootstrapError}</InlineNotice>
        ) : null}

        {isSetupMode || isSignupMode ? (
          <div className="space-y-1">
            <label
              className="ml-1 app-text-caption font-medium text-app-ink/45"
              htmlFor="auth-full-name"
            >
              {t('login.name')}
            </label>
            <div className="relative">
              <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
                <User size={16} className="text-app-ink/55" />
              </div>
              <input
                autoComplete="name"
                className={`${fieldClassName} pl-10`}
                id="auth-full-name"
                minLength={2}
                onChange={(event) =>
                  onFieldChange('fullName', event.target.value)
                }
                placeholder={t('login.namePlaceholder')}
                required
                value={form.fullName}
              />
            </div>
          </div>
        ) : null}

        <div className="space-y-1">
          <label
            className="ml-1 app-text-caption font-medium text-app-ink/45"
            htmlFor="auth-login-id"
          >
            {t('login.loginId')}
          </label>
          <div className="relative">
            <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
              <AtSign size={16} className="text-app-ink/55" />
            </div>
            <input
              autoComplete="username"
              className={`${fieldClassName} pl-10`}
              id="auth-login-id"
              maxLength={40}
              minLength={3}
              onChange={(event) => onFieldChange('loginId', event.target.value)}
              placeholder={t('login.loginIdPlaceholder')}
              required
              value={form.loginId}
            />
          </div>
        </div>

        {isSetupMode || isSignupMode ? (
          <div className="space-y-1">
            <label
              className="ml-1 app-text-caption font-medium text-app-ink/45"
              htmlFor="auth-email"
            >
              {t('login.email')}
            </label>
            <div className="relative">
              <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
                <Mail size={16} className="text-app-ink/55" />
              </div>
              <input
                autoComplete="email"
                className={`${fieldClassName} pl-10`}
                id="auth-email"
                onChange={(event) => onFieldChange('email', event.target.value)}
                placeholder={t('login.emailPlaceholder')}
                required
                type="email"
                value={form.email}
              />
            </div>
          </div>
        ) : null}

        <div className="space-y-1">
          <div className="ml-1 flex items-center justify-between">
            <label
              className="app-text-caption font-medium text-app-ink/45"
              htmlFor="auth-password"
            >
              {t('login.password')}
            </label>
            {!isSetupMode && !isSignupMode ? (
              <span className="app-text-caption text-app-accent">
                {t('login.localCredentialBadge')}
              </span>
            ) : null}
          </div>
          <PasswordField
            autoComplete={isSetupMode || isSignupMode ? 'new-password' : 'current-password'}
            id="auth-password"
            label={t('login.password')}
            minLength={isSetupMode || isSignupMode ? 8 : 1}
            onChange={(value) => onFieldChange('password', value)}
            value={form.password}
          />
        </div>

        {isSignupMode ? (
          <div className="space-y-1">
            <label
              className="ml-1 app-text-caption font-medium text-app-ink/45"
              htmlFor="auth-password-confirm"
            >
              {t('login.passwordConfirm')}
            </label>
            <PasswordField
              autoComplete="new-password"
              id="auth-password-confirm"
              label={t('login.passwordConfirm')}
              minLength={8}
              onChange={(value) => onFieldChange('passwordConfirm', value)}
              value={form.passwordConfirm}
            />
          </div>
        ) : null}

        <button
          className="mt-6 flex w-full items-center justify-center gap-2 rounded-lg bg-app-accent py-2.5 app-text-body font-medium text-app-accent-fg transition-all hover:bg-opacity-90 disabled:cursor-not-allowed disabled:opacity-70"
          disabled={form.submitting}
          type="submit"
        >
          {form.submitting ? (
            <div className="size-5 animate-spin rounded-full border-2 border-app-bg/30 border-t-app-bg" />
          ) : (
            <>
              {isSetupMode
                ? t('login.createAdmin')
                : isSignupMode
                  ? t('login.createAccount')
                  : t('login.signIn')}
              <ArrowRight size={16} />
            </>
          )}
        </button>
      </form>

      {!isSetupMode ? (
        <p className="mt-6 text-center app-text-caption text-app-ink/55">
          {isSignupMode ? t('login.alreadyHaveAccount') : t('login.noAccount')}{' '}
          <button
            className="font-medium text-app-accent hover:underline"
            onClick={() => onModeChange(isSignupMode ? 'login' : 'signup')}
            type="button"
          >
            {isSignupMode ? t('login.goToSignIn') : t('login.goToSignup')}
          </button>
        </p>
      ) : null}

      {!hasDevAccountButtons &&
      !isSetupMode &&
      !isSignupMode &&
      auth.devAdminLoginAvailable ? (
        <>
          <div className="mt-6">
            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-app-border" />
              </div>
              <div className="relative flex justify-center app-text-caption">
                <span className="bg-app-surface px-2 text-app-ink/55">
                  {t('login.quickStart')}
                </span>
              </div>
            </div>

            <div className="mt-6 grid gap-3">
              <button
                className="flex items-center justify-center gap-2 rounded-lg border border-app-border py-2.5 app-text-body font-medium text-app-ink transition-colors hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-70"
                disabled={form.submitting}
                onClick={() => void onDevAdminLogin()}
                type="button"
              >
                <ShieldCheck size={16} />
                {t('login.devAdminButton')}
              </button>
            </div>
          </div>

          <p className="mt-8 text-center app-text-caption text-app-ink/55">
            {t('login.devAdminDescription')}
          </p>
        </>
      ) : null}
    </div>
  );
}
