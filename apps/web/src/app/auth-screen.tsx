import type { FormEvent } from 'react';
import { Button, Input, Panel, StatusBadge } from '@aidoo/ui';
import { useState } from 'react';

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

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (isSetup) {
      await onSetup({ fullName, email, password });
      return;
    }

    await onLogin({ email, password });
  }

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,#dce7ef,transparent_34%),linear-gradient(180deg,#f4f7f9_0%,#eef2f5_100%)] px-4 py-10">
      <div className="mx-auto grid max-w-5xl gap-6 lg:grid-cols-[minmax(0,1.1fr)_420px]">
        <section className="grid content-between rounded-[28px] border border-slate-200/80 bg-slate-950 px-8 py-8 text-white shadow-[0_32px_90px_rgba(15,23,42,0.24)]">
          <div className="grid gap-5">
            <div className="inline-flex w-fit items-center gap-2 rounded-full border border-white/15 bg-white/8 px-3 py-1 text-xs font-semibold tracking-[0.14em] text-cyan-200">
              <span>두원공조</span>
              <span className="text-white/35">/</span>
              <span>AIDOO</span>
            </div>
            <div className="grid gap-3">
              <h1 className="m-0 text-[clamp(2.2rem,5vw,4.4rem)] font-semibold leading-[0.92] tracking-[-0.06em]">
                아이두
                <br />
                AI 업무 포털
              </h1>
              <p className="m-0 max-w-[34rem] text-sm leading-6 text-slate-300">
                두원공조 업무 문서, 사내 지식, 기안 흐름을 하나로 묶는 내부 AI 작업면입니다.
                지금은 자체 계정 로그인으로 운영하고, 이후 사내 SSO로 확장할 수 있게 구성합니다.
              </p>
            </div>
          </div>
          <div className="grid gap-3 border-t border-white/10 pt-5 text-sm text-slate-300 sm:grid-cols-3">
            <div>
              <div className="text-xs uppercase tracking-[0.12em] text-slate-500">Stage</div>
              <div className="mt-1 font-medium text-white">Internal Preview</div>
            </div>
            <div>
              <div className="text-xs uppercase tracking-[0.12em] text-slate-500">Access</div>
              <div className="mt-1 font-medium text-white">Local Accounts</div>
            </div>
            <div>
              <div className="text-xs uppercase tracking-[0.12em] text-slate-500">Next</div>
              <div className="mt-1 font-medium text-white">SSO Integration</div>
            </div>
          </div>
        </section>

        <Panel
          className="self-center"
          eyebrow="AIDOO Access"
          title={mode === 'loading' ? '환경 확인 중' : isSetup ? '첫 관리자 계정 생성' : '로그인'}
          description={
            mode === 'loading'
              ? '인증 상태와 초기 설정 여부를 확인하고 있습니다.'
              : isSetup
                ? '아직 계정이 없습니다. 첫 사용자를 관리자 계정으로 생성합니다.'
                : '등록된 자체 계정으로 아이두에 로그인합니다.'
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
                <div className="rounded-[var(--ui-radius-md)] border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                  {error}
                </div>
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
