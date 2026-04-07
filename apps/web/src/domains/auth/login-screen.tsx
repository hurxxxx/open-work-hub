import { useState } from 'react';

import { Button, InlineNotice, Input, Panel } from '@aidoo/ui';

import { useAuth } from './auth-provider';

const LOCAL_ADMIN_EMAIL = 'admin@aidoo.local';
const LOCAL_ADMIN_PASSWORD = 'supersecret123';

function getMessage(caughtError: unknown, fallback: string): string {
  if (caughtError instanceof Error && caughtError.message) {
    return caughtError.message;
  }

  return fallback;
}

export function LoginScreen() {
  const auth = useAuth();
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const isSetupMode = auth.requiresSetup;

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
    <div className="min-h-screen bg-[linear-gradient(180deg,#eef3f9_0%,#f7f9fc_100%)] text-[var(--ui-color-ink)]">
      <div className="mx-auto grid min-h-screen w-full max-w-6xl gap-6 px-6 py-8 lg:grid-cols-[minmax(0,1.1fr)_420px] lg:px-8">
        <section className="flex flex-col justify-between rounded-[var(--ui-radius-lg)] border border-[var(--ui-color-border)] bg-[color-mix(in_srgb,var(--ui-color-surface)_86%,transparent)] p-6 shadow-[var(--ui-shadow-sm)] backdrop-blur-sm">
          <div className="grid gap-6">
            <div className="grid gap-3">
              <p className="m-0 text-[0.72rem] font-semibold uppercase tracking-[0.12em] text-[var(--ui-color-ink-subtle)]">
                AIDOO Portal
              </p>
              <div className="grid gap-2">
                <h1 className="m-0 text-[2rem] font-semibold tracking-[-0.03em] text-[var(--ui-color-ink)]">
                  내부 업무 포털 인증
                </h1>
                <p className="m-0 max-w-[56ch] text-[0.94rem] leading-6 text-[var(--ui-color-ink-muted)]">
                  검색, PMS, 문서 작업면에 들어가기 전에 세션을 확인합니다. 1차 구현은
                  사내 ID/PW 기반 로그인만 지원합니다.
                </p>
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-3">
              <div className="rounded-[var(--ui-radius-md)] border border-[var(--ui-color-border)] bg-[var(--ui-color-surface)] p-4">
                <p className="m-0 text-[0.72rem] font-semibold uppercase tracking-[0.08em] text-[var(--ui-color-ink-subtle)]">
                  Access
                </p>
                <strong className="mt-2 block text-[0.98rem]">Bearer session</strong>
                <p className="m-0 mt-2 text-[0.82rem] leading-5 text-[var(--ui-color-ink-muted)]">
                  브라우저 재접속 시 저장된 세션 토큰을 검증한 뒤 앱 셸을 복원합니다.
                </p>
              </div>
              <div className="rounded-[var(--ui-radius-md)] border border-[var(--ui-color-border)] bg-[var(--ui-color-surface)] p-4">
                <p className="m-0 text-[0.72rem] font-semibold uppercase tracking-[0.08em] text-[var(--ui-color-ink-subtle)]">
                  Bootstrap
                </p>
                <strong className="mt-2 block text-[0.98rem]">Initial admin</strong>
                <p className="m-0 mt-2 text-[0.82rem] leading-5 text-[var(--ui-color-ink-muted)]">
                  사용자가 아직 없으면 최초 관리자 계정을 만들고 즉시 로그인합니다.
                </p>
              </div>
              <div className="rounded-[var(--ui-radius-md)] border border-[var(--ui-color-border)] bg-[var(--ui-color-surface)] p-4">
                <p className="m-0 text-[0.72rem] font-semibold uppercase tracking-[0.08em] text-[var(--ui-color-ink-subtle)]">
                  Scope
                </p>
                <strong className="mt-2 block text-[0.98rem]">Auth gate v1</strong>
                <p className="m-0 mt-2 text-[0.82rem] leading-5 text-[var(--ui-color-ink-muted)]">
                  이번 단계는 라우트 보호, 세션 복원, 로그아웃까지를 닫습니다.
                </p>
              </div>
            </div>
          </div>

          <div className="rounded-[var(--ui-radius-md)] border border-dashed border-[var(--ui-color-border-strong)] bg-[color-mix(in_srgb,var(--ui-color-surface)_72%,transparent)] p-4 text-[0.82rem] text-[var(--ui-color-ink-muted)]">
            첫 계정은 관리자 권한으로 생성됩니다. SSO/AD 연동은 후속 범위입니다.
          </div>
        </section>

        <div className="flex items-center justify-center">
          <Panel
            className="w-full max-w-[420px] p-5"
            eyebrow={isSetupMode ? 'Initial setup' : 'Sign in'}
            title={isSetupMode ? '최초 관리자 설정' : '로그인'}
            description={
              isSetupMode
                ? '첫 사용자를 만든 뒤 바로 보호된 앱 셸로 진입합니다.'
                : '등록된 계정으로 세션을 발급받아 업무 화면에 진입합니다.'
            }
            actions={
              auth.bootstrapError ? (
                <Button
                  variant="secondary"
                  onClick={() => {
                    void auth.refreshSession();
                  }}
                >
                  다시 확인
                </Button>
              ) : null
            }
          >
            <form className="grid gap-3" onSubmit={(event) => void handleSubmit(event)}>
              {auth.bootstrapError ? (
                <InlineNotice tone="danger">{auth.bootstrapError}</InlineNotice>
              ) : null}
              {formError ? <InlineNotice tone="danger">{formError}</InlineNotice> : null}
              {isSetupMode ? (
                <label className="grid gap-1.5 text-[0.8rem] font-medium text-[var(--ui-color-ink)]">
                  이름
                  <Input
                    autoComplete="name"
                    minLength={2}
                    onChange={(event) => setFullName(event.target.value)}
                    placeholder="홍길동"
                    required
                    value={fullName}
                  />
                </label>
              ) : null}
              <label className="grid gap-1.5 text-[0.8rem] font-medium text-[var(--ui-color-ink)]">
                이메일
                <Input
                  autoComplete="email"
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="name@company.com"
                  required
                  type="email"
                  value={email}
                />
              </label>
              <label className="grid gap-1.5 text-[0.8rem] font-medium text-[var(--ui-color-ink)]">
                비밀번호
                <Input
                  autoComplete={isSetupMode ? 'new-password' : 'current-password'}
                  minLength={8}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="8자 이상"
                  required
                  type="password"
                  value={password}
                />
              </label>

              <Button
                fullWidth
                disabled={submitting}
                size="comfortable"
                type="submit"
                variant="primary"
              >
                {submitting
                  ? isSetupMode
                    ? '계정 생성 중...'
                    : '로그인 중...'
                  : isSetupMode
                    ? '관리자 계정 만들기'
                    : '로그인'}
              </Button>
              {!isSetupMode ? (
                <Button
                  fullWidth
                  disabled={submitting}
                  onClick={() => {
                    setEmail(LOCAL_ADMIN_EMAIL);
                    setPassword(LOCAL_ADMIN_PASSWORD);
                    setFormError(null);
                  }}
                  size="comfortable"
                  type="button"
                  variant="secondary"
                >
                  관리자 계정 자동 입력
                </Button>
              ) : null}
            </form>
          </Panel>
        </div>
      </div>
    </div>
  );
}
