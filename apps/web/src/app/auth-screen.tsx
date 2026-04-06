import type { FormEvent } from 'react';
import { Button, Input, Panel, StatusBadge } from '@aidoo/ui';
import { useState } from 'react';

const DEV_ADMIN_PRESET = {
  email: 'admin@aidoo.local',
  password: 'AidooAdmin2026',
};

export interface AuthScreenProps {
  mode: 'loading' | 'login' | 'setup';
  busy?: boolean;
  error?: string | null;
  onLogin: (payload: { email: string; password: string }) => Promise<void>;
  onSetup: (payload: { fullName: string; email: string; password: string }) => Promise<void>;
}

export function AuthScreen({
  mode,
  busy = false,
  error,
  onLogin,
  onSetup,
}: AuthScreenProps) {
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const isSetup = mode === 'setup';
  const showDevAdminShortcut = import.meta.env.MODE === 'development' && !isSetup;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (isSetup) {
      await onSetup({ fullName, email, password });
      return;
    }

    await onLogin({ email, password });
  }

  return (
    <div className="min-h-screen bg-[linear-gradient(180deg,#f4f7fb_0%,#eef3f8_100%)] px-4 py-8">
      <div className="mx-auto grid max-w-5xl gap-5 lg:grid-cols-[minmax(0,1.15fr)_420px]">
        <section className="grid content-between rounded-[18px] border border-white/6 bg-[#111923] px-7 py-7 text-white shadow-[0_22px_48px_rgba(15,23,42,0.16)]">
          <div className="grid gap-6">
            <div className="inline-flex w-fit items-center gap-2 rounded-[var(--ui-radius-sm)] border border-white/10 bg-white/5 px-2.5 py-1 text-[0.68rem] font-semibold uppercase tracking-[0.12em] text-white/72">
              <span>두원공조</span>
              <span className="text-white/28">/</span>
              <span>AIDOO Portal</span>
            </div>
            <div className="grid gap-2">
              <h1 className="m-0 text-[clamp(2rem,4vw,3.3rem)] font-semibold leading-[0.98] tracking-[-0.05em]">
                아이두 업무 포털
              </h1>
              <p className="m-0 max-w-[34rem] text-[0.92rem] leading-6 text-slate-300">
                문서 검색, 프로젝트 관리, 기안 작업을 한 셸 안에서 운영하는 내부 업무 도구입니다.
                지금은 자체 계정으로 로그인하고, 이후 사내 SSO로 확장할 수 있게 구성합니다.
              </p>
            </div>
          </div>
          <div className="grid gap-3 border-t border-white/8 pt-5 text-[0.84rem] text-slate-300 sm:grid-cols-3">
            <div>
              <div className="text-[0.66rem] uppercase tracking-[0.12em] text-slate-500">Stage</div>
              <div className="mt-1 font-medium text-white">Internal Workspace</div>
            </div>
            <div>
              <div className="text-[0.66rem] uppercase tracking-[0.12em] text-slate-500">Access</div>
              <div className="mt-1 font-medium text-white">Local Accounts</div>
            </div>
            <div>
              <div className="text-[0.66rem] uppercase tracking-[0.12em] text-slate-500">Next</div>
              <div className="mt-1 font-medium text-white">SSO Integration</div>
            </div>
          </div>
        </section>

        <Panel
          className="self-center"
          eyebrow="Access"
          title={mode === 'loading' ? '환경 확인 중' : isSetup ? '첫 관리자 계정 생성' : '로그인'}
          description={
            mode === 'loading'
              ? '인증 상태와 초기 설정 여부를 확인하고 있습니다.'
              : isSetup
                ? '아직 계정이 없습니다. 첫 사용자를 관리자 계정으로 생성합니다.'
                : '등록된 자체 계정으로 업무 포털에 로그인합니다.'
          }
          status={<StatusBadge>{isSetup ? 'Bootstrap' : 'Auth'}</StatusBadge>}
        >
          {mode === 'loading' ? (
            <div className="grid gap-3">
              <div className="h-11 animate-pulse rounded-[var(--ui-radius-md)] bg-slate-200" />
              <div className="h-11 animate-pulse rounded-[var(--ui-radius-md)] bg-slate-200" />
              <div className="h-11 animate-pulse rounded-[var(--ui-radius-md)] bg-slate-200" />
            </div>
          ) : (
            <form className="grid gap-4" onSubmit={handleSubmit}>
              {isSetup ? (
                <label className="grid gap-1.5 text-sm text-[var(--ui-color-ink-muted)]">
                  이름
                  <Input
                    autoComplete="name"
                    disabled={busy}
                    onChange={(event) => setFullName(event.target.value)}
                    placeholder="예: 홍길동"
                    value={fullName}
                  />
                </label>
              ) : null}

              <label className="grid gap-1.5 text-sm text-[var(--ui-color-ink-muted)]">
                이메일
                <Input
                  autoComplete="email"
                  disabled={busy}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="name@company.com"
                  type="email"
                  value={email}
                />
              </label>

              <label className="grid gap-1.5 text-sm text-[var(--ui-color-ink-muted)]">
                비밀번호
                <Input
                  autoComplete={isSetup ? 'new-password' : 'current-password'}
                  disabled={busy}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="8자 이상"
                  type="password"
                  value={password}
                />
              </label>

              {error ? (
                <div className="rounded-[var(--ui-radius-sm)] border border-rose-200 bg-rose-50 px-3 py-2 text-[0.84rem] text-rose-700">
                  {error}
                </div>
              ) : null}

              {showDevAdminShortcut ? (
                <Button
                  className="justify-center"
                  disabled={busy}
                  onClick={() => {
                    setEmail(DEV_ADMIN_PRESET.email);
                    setPassword(DEV_ADMIN_PRESET.password);
                  }}
                  type="button"
                  variant="subtle"
                >
                  관리자 계정 자동 입력
                </Button>
              ) : null}

              <Button className="mt-2 justify-center" disabled={busy} type="submit">
                {busy ? '처리 중...' : isSetup ? '관리자 계정 생성' : '로그인'}
              </Button>
            </form>
          )}
        </Panel>
      </div>
    </div>
  );
}
