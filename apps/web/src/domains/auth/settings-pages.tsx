import { useEffect, useState } from 'react';

import { Button, InlineNotice, Input, Panel, Select } from '@aidoo/ui';

import type { AuthSessionItem, ThemePreference } from './auth-api';
import { useAuth } from './auth-provider';

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }

  return fallback;
}

const themeOptions = [
  { value: 'system', label: '시스템 기본값' },
  { value: 'light', label: '라이트' },
  { value: 'dark', label: '다크' },
];

export function AccessDeniedView({
  title = '접근 권한 없음',
  description = '현재 계정에는 이 화면을 볼 권한이 없습니다.',
}: {
  title?: string;
  description?: string;
}) {
  return (
    <div className="p-6">
      <Panel
        eyebrow="Access"
        title={title}
        description={description}
      >
        <InlineNotice tone="warning">
          관리자에게 필요한 권한과 워크스페이스 바인딩을 요청하세요.
        </InlineNotice>
      </Panel>
    </div>
  );
}

export function AccountSettingsView() {
  const auth = useAuth();
  const user = auth.user;
  const [displayName, setDisplayName] = useState(user?.display_name ?? '');
  const [fullName, setFullName] = useState(user?.full_name ?? '');
  const [jobTitle, setJobTitle] = useState('');
  const [themePreference, setThemePreference] = useState<ThemePreference>(
    user?.theme_preference ?? 'system',
  );
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) {
      return;
    }

    setDisplayName(user.display_name);
    setFullName(user.full_name);
    setThemePreference(user.theme_preference);
  }, [user]);

  if (!user) {
    return null;
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setMessage(null);
    setError(null);

    try {
      await auth.updatePreferences({
        display_name: displayName.trim(),
        full_name: fullName.trim(),
        job_title: jobTitle.trim(),
        theme_preference: themePreference,
      });
      setMessage('계정 설정을 저장했습니다.');
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '계정 설정을 저장하지 못했습니다.'));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="grid gap-4 p-6">
      <Panel
        eyebrow="Account"
        title="내 계정"
        description="표시 이름, 기본 테마, 사용자 메타데이터를 관리합니다."
      >
        <form className="grid gap-3" onSubmit={(event) => void handleSubmit(event)}>
          {message ? <InlineNotice tone="success">{message}</InlineNotice> : null}
          {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}
          <div className="grid gap-3 md:grid-cols-2">
            <label className="grid gap-1.5 text-sm font-medium text-[var(--ui-color-ink)]">
              이메일
              <Input disabled value={user.email} />
            </label>
            <label className="grid gap-1.5 text-sm font-medium text-[var(--ui-color-ink)]">
              조직
              <Input disabled value={user.primary_org_unit?.name ?? '미지정'} />
            </label>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <label className="grid gap-1.5 text-sm font-medium text-[var(--ui-color-ink)]">
              표시 이름
              <Input
                onChange={(event) => setDisplayName(event.target.value)}
                value={displayName}
              />
            </label>
            <label className="grid gap-1.5 text-sm font-medium text-[var(--ui-color-ink)]">
              성명
              <Input
                onChange={(event) => setFullName(event.target.value)}
                value={fullName}
              />
            </label>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <label className="grid gap-1.5 text-sm font-medium text-[var(--ui-color-ink)]">
              직함
              <Input
                onChange={(event) => setJobTitle(event.target.value)}
                placeholder="예: Platform Owner"
                value={jobTitle}
              />
            </label>
            <div className="grid gap-1.5 text-sm font-medium text-[var(--ui-color-ink)]">
              테마
              <Select
                onValueChange={(value) => setThemePreference(value as ThemePreference)}
                options={themeOptions}
                value={themePreference}
              />
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button disabled={submitting} type="submit" variant="primary">
              {submitting ? '저장 중...' : '저장'}
            </Button>
            <span className="text-sm text-[var(--ui-color-ink-muted)]">
              그룹: {user.group_slugs.join(', ') || '없음'}
            </span>
          </div>
        </form>
      </Panel>
    </div>
  );
}

function SessionCard({
  session,
  onRevoke,
}: {
  session: AuthSessionItem;
  onRevoke: (sessionId: string) => Promise<void>;
}) {
  return (
    <div className="grid gap-2 rounded-[var(--ui-radius-md)] border border-[var(--ui-color-border)] bg-[var(--ui-color-surface-subtle)] p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <strong className="text-sm text-[var(--ui-color-ink)]">
          {session.is_current ? '현재 세션' : '저장된 세션'}
        </strong>
        {!session.is_current && !session.revoked_at ? (
          <Button
            onClick={() => {
              void onRevoke(session.id);
            }}
            size="dense"
            variant="secondary"
          >
            세션 종료
          </Button>
        ) : null}
      </div>
      <div className="grid gap-1 text-xs text-[var(--ui-color-ink-muted)]">
        <span>생성: {new Date(session.created_at).toLocaleString()}</span>
        <span>만료: {new Date(session.expires_at).toLocaleString()}</span>
        <span>최근 사용: {session.last_seen_at ? new Date(session.last_seen_at).toLocaleString() : '없음'}</span>
        <span>에이전트: {session.user_agent ?? '알 수 없음'}</span>
        <span>IP: {session.ip_address ?? '알 수 없음'}</span>
      </div>
    </div>
  );
}

export function SecuritySettingsView() {
  const auth = useAuth();
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [sessions, setSessions] = useState<AuthSessionItem[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadSessions() {
    setLoadingSessions(true);
    try {
      const items = await auth.listSessions();
      setSessions(items);
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '세션 목록을 불러오지 못했습니다.'));
    } finally {
      setLoadingSessions(false);
    }
  }

  useEffect(() => {
    void loadSessions();
  }, []);

  async function handlePasswordSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    setError(null);

    try {
      await auth.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      });
      setCurrentPassword('');
      setNewPassword('');
      setMessage('비밀번호를 변경했습니다.');
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '비밀번호를 변경하지 못했습니다.'));
    }
  }

  async function handleRevoke(sessionId: string) {
    setMessage(null);
    setError(null);

    try {
      await auth.revokeSession(sessionId);
      await loadSessions();
      setMessage('세션을 종료했습니다.');
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '세션을 종료하지 못했습니다.'));
    }
  }

  return (
    <div className="grid gap-4 p-6">
      <Panel
        eyebrow="Security"
        title="보안 설정"
        description="비밀번호를 변경하고 현재 로그인 세션을 관리합니다."
      >
        <form className="grid gap-3" onSubmit={(event) => void handlePasswordSubmit(event)}>
          {auth.user?.must_change_password ? (
            <InlineNotice tone="warning">
              현재 계정은 다음 로그인 전에 비밀번호 변경이 필요합니다.
            </InlineNotice>
          ) : null}
          {message ? <InlineNotice tone="success">{message}</InlineNotice> : null}
          {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}
          <div className="grid gap-3 md:grid-cols-2">
            <label className="grid gap-1.5 text-sm font-medium text-[var(--ui-color-ink)]">
              현재 비밀번호
              <Input
                minLength={8}
                onChange={(event) => setCurrentPassword(event.target.value)}
                type="password"
                value={currentPassword}
              />
            </label>
            <label className="grid gap-1.5 text-sm font-medium text-[var(--ui-color-ink)]">
              새 비밀번호
              <Input
                minLength={8}
                onChange={(event) => setNewPassword(event.target.value)}
                type="password"
                value={newPassword}
              />
            </label>
          </div>
          <div className="flex items-center gap-2">
            <Button type="submit" variant="primary">
              비밀번호 변경
            </Button>
          </div>
        </form>
      </Panel>

      <Panel
        eyebrow="Sessions"
        title="현재 세션"
        description="브라우저별 로그인 세션을 확인하고 필요 시 종료합니다."
      >
        {loadingSessions ? (
          <p className="m-0 text-sm text-[var(--ui-color-ink-muted)]">세션을 불러오는 중입니다.</p>
        ) : (
          <div className="grid gap-3">
            {sessions.map((session) => (
              <SessionCard key={session.id} onRevoke={handleRevoke} session={session} />
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
