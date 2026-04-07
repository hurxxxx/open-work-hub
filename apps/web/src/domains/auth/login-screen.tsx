import { useEffect, useState } from 'react';
import { motion } from 'motion/react';
import { ArrowRight, Lock, Mail, ShieldCheck, User } from 'lucide-react';

import { InlineNotice } from '@aidoo/ui';

import { useAuth } from './auth-provider';

function getMessage(caughtError: unknown, fallback: string): string {
  if (caughtError instanceof Error && caughtError.message) {
    return caughtError.message;
  }

  return fallback;
}

const fieldClassName =
  'w-full rounded-lg border border-[#3d3e40] bg-[#1e1f21] py-2.5 pr-4 text-sm text-[#d5d6d7] transition-all placeholder:text-gray-500 focus:border-clickup-purple focus:outline-none focus:ring-1 focus:ring-clickup-purple';

export function LoginScreen() {
  const auth = useAuth();
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const isSetupMode = auth.requiresSetup;

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

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setFormError(null);

    try {
      if (isSetupMode) {
        await auth.setupFirstUser({
          full_name: fullName.trim(),
          email: email.trim(),
          password,
        });
      } else {
        await auth.login({
          email: email.trim(),
          password,
        });
      }
    } catch (caughtError) {
      setFormError(
        getMessage(
          caughtError,
          isSetupMode ? '최초 관리자 계정을 만들지 못했습니다.' : '로그인하지 못했습니다.',
        ),
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-clickup-dark p-4">
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -top-[20%] -left-[10%] h-[50%] w-[50%] rounded-full bg-clickup-purple/10 blur-[120px]" />
        <div className="absolute top-[60%] -right-[10%] h-[60%] w-[40%] rounded-full bg-blue-500/10 blur-[120px]" />
      </div>

      <motion.div
        animate={{ opacity: 1, y: 0 }}
        className="z-10 w-full max-w-md"
        initial={{ opacity: 0, y: 20 }}
        transition={{ duration: 0.5 }}
      >
        <div className="rounded-2xl border border-[#3d3e40] bg-[#2a2b2d] p-8 shadow-2xl">
          <div className="mb-8 text-center">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-clickup-purple text-xl font-bold text-white shadow-lg shadow-clickup-purple/20">
              ID
            </div>
            <h1 className="mb-2 text-2xl font-bold text-[#d5d6d7]">
              {isSetupMode ? '최초 관리자 설정' : '로그인'}
            </h1>
            <p className="text-sm text-gray-400">
              {isSetupMode
                ? '첫 관리자 계정을 생성해 워크스페이스를 시작합니다.'
                : '원격 dev DB 기준 관리자 빠른 로그인을 지원합니다.'}
            </p>
          </div>

          <form className="space-y-4" onSubmit={(event) => void handleSubmit(event)}>
            {auth.bootstrapError ? (
              <InlineNotice tone="danger">{auth.bootstrapError}</InlineNotice>
            ) : null}
            {formError ? <InlineNotice tone="danger">{formError}</InlineNotice> : null}

            {isSetupMode ? (
              <div className="space-y-1">
                <label className="ml-1 text-xs font-medium text-gray-400" htmlFor="auth-full-name">
                  이름
                </label>
                <div className="relative">
                  <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
                    <User size={16} className="text-gray-500" />
                  </div>
                  <input
                    autoComplete="name"
                    className={`${fieldClassName} pl-10`}
                    id="auth-full-name"
                    minLength={2}
                    onChange={(event) => setFullName(event.target.value)}
                    placeholder="홍길동"
                    required
                    value={fullName}
                  />
                </div>
              </div>
            ) : null}

            <div className="space-y-1">
              <label className="ml-1 text-xs font-medium text-gray-400" htmlFor="auth-email">
                이메일
              </label>
              <div className="relative">
                <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
                  <Mail size={16} className="text-gray-500" />
                </div>
                <input
                  autoComplete="email"
                  className={`${fieldClassName} pl-10`}
                  id="auth-email"
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="name@company.com"
                  required
                  type="email"
                  value={email}
                />
              </div>
            </div>

            <div className="space-y-1">
              <div className="ml-1 flex items-center justify-between">
                <label className="text-xs font-medium text-gray-400" htmlFor="auth-password">
                  비밀번호
                </label>
                {!isSetupMode ? (
                  <span className="text-xs text-clickup-purple">Local ID/PW</span>
                ) : null}
              </div>
              <div className="relative">
                <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
                  <Lock size={16} className="text-gray-500" />
                </div>
                <input
                  autoComplete={isSetupMode ? 'new-password' : 'current-password'}
                  className={`${fieldClassName} pl-10`}
                  id="auth-password"
                  minLength={8}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="••••••••"
                  required
                  type="password"
                  value={password}
                />
              </div>
            </div>

            <button
              className="mt-6 flex w-full items-center justify-center gap-2 rounded-lg bg-clickup-purple py-2.5 text-sm font-medium text-white transition-all hover:bg-opacity-90 disabled:cursor-not-allowed disabled:opacity-70"
              disabled={submitting}
              type="submit"
            >
              {submitting ? (
                <div className="h-5 w-5 animate-spin rounded-full border-2 border-white/30 border-t-white" />
              ) : (
                <>
                  {isSetupMode ? '관리자 계정 만들기' : '로그인'}
                  <ArrowRight size={16} />
                </>
              )}
            </button>
          </form>

          {!isSetupMode ? (
            <>
              <div className="mt-6">
                <div className="relative">
                  <div className="absolute inset-0 flex items-center">
                    <div className="w-full border-t border-[#3d3e40]" />
                  </div>
                  <div className="relative flex justify-center text-xs">
                    <span className="bg-[#2a2b2d] px-2 text-gray-500">빠른 실행</span>
                  </div>
                </div>

                <div className="mt-6 grid gap-3">
                  <button
                    className="flex items-center justify-center gap-2 rounded-lg border border-[#3d3e40] py-2.5 text-sm font-medium text-[#d5d6d7] transition-colors hover:bg-[#353638] disabled:cursor-not-allowed disabled:opacity-70"
                    disabled={submitting}
                    onClick={() => {
                      setSubmitting(true);
                      setFormError(null);
                      void auth
                        .loginAsDevelopmentAdmin()
                        .catch((caughtError) => {
                          setFormError(
                            getMessage(
                              caughtError,
                              '개발용 관리자 바로 로그인을 실행하지 못했습니다.',
                            ),
                          );
                        })
                        .finally(() => {
                          setSubmitting(false);
                        });
                    }}
                    type="button"
                  >
                    <ShieldCheck size={16} />
                    개발용 관리자 바로 로그인
                  </button>
                </div>
              </div>

              <p className="mt-8 text-center text-xs text-gray-500">
                원격 dev DB에서는 이 버튼이 첫 활성 관리자 세션을 바로 발급합니다.
              </p>
            </>
          ) : null}
        </div>
      </motion.div>
    </div>
  );
}
