import { useEffect, useState } from 'react';
import {
  Bell,
  LogOut,
  Monitor,
  Moon,
  Palette,
  Shield,
  Sun,
  User,
} from 'lucide-react';

import { Button, InlineNotice } from '@aidoo/ui';

import { cn } from '@/src/lib/utils';

import type { AuthSessionItem, ThemePreference } from './auth-api';
import { useAuth } from './auth-provider';

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }

  if (typeof error === 'string') {
    return error;
  }

  return fallback;
}

const themeOptions: { value: ThemePreference; label: string; icon: typeof Sun }[] = [
  { value: 'system', label: '시스템', icon: Monitor },
  { value: 'light', label: '라이트', icon: Sun },
  { value: 'dark', label: '다크', icon: Moon },
];

const fieldClassName =
  'app-text-body w-full rounded-md border border-app-border bg-app-bg px-3 py-2 text-app-ink transition-colors focus:border-app-accent focus:outline-none';

type SettingsSection = 'profile' | 'appearance' | 'security' | 'notifications';

/* ── Access Denied ── */

export function AccessDeniedView({
  title = '접근 권한 없음',
  description = '현재 계정에는 이 화면을 볼 권한이 없습니다.',
}: {
  title?: string;
  description?: string;
}) {
  return (
    <div className="p-6">
      <div className="rounded-xl border border-app-border bg-app-surface-sidebar p-6">
        <h2 className="app-text-title-md mb-2 text-app-ink">{title}</h2>
        <p className="app-text-body mb-4 text-gray-500">{description}</p>
        <InlineNotice tone="warning">
          관리자에게 필요한 권한과 워크스페이스 바인딩을 요청하세요.
        </InlineNotice>
      </div>
    </div>
  );
}

/* ── Session Card ── */

function SessionCard({
  session,
  onRevoke,
}: {
  session: AuthSessionItem;
  onRevoke: (sessionId: string) => Promise<void>;
}) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-md border border-app-border bg-app-bg px-4 py-3">
      <div className="app-text-body grid gap-1">
        <span className="font-medium text-app-ink">
          {session.is_current ? '현재 세션' : '저장된 세션'}
        </span>
        <span className="app-text-caption text-gray-500">
          생성: {new Date(session.created_at).toLocaleString()}
        </span>
        <span className="app-text-caption text-gray-500">
          만료: {new Date(session.expires_at).toLocaleString()}
        </span>
        <span className="app-text-caption text-gray-500">
          최근 사용: {session.last_seen_at ? new Date(session.last_seen_at).toLocaleString() : '없음'}
        </span>
        <span className="app-text-caption max-w-[360px] truncate text-gray-500">
          {session.user_agent ?? '알 수 없음'}
        </span>
        <span className="app-text-caption text-gray-500">IP: {session.ip_address ?? '알 수 없음'}</span>
      </div>
      {!session.is_current && !session.revoked_at ? (
        <Button
          onClick={() => { void onRevoke(session.id); }}
          size="dense"
          variant="secondary"
        >
          종료
        </Button>
      ) : null}
    </div>
  );
}

/* ── Inline Field Row ── */

function FieldRow({
  label,
  children,
  description,
}: {
  label: string;
  children: React.ReactNode;
  description?: string;
}) {
  return (
    <div className="grid grid-cols-[180px_1fr] items-start gap-6 py-4 border-b border-app-border last:border-b-0 max-[720px]:grid-cols-1 max-[720px]:gap-2">
      <div>
        <label className="app-text-control text-app-ink">{label}</label>
        {description ? <p className="app-text-caption mt-0.5 text-gray-500">{description}</p> : null}
      </div>
      <div className="max-w-md">{children}</div>
    </div>
  );
}

/* ── Section Header ── */

function SectionHeader({ title, description }: { title: string; description?: string }) {
  return (
    <div className="mb-6">
      <h2 className="app-text-title-md text-app-ink">{title}</h2>
      {description ? <p className="app-text-body mt-1 text-gray-500">{description}</p> : null}
    </div>
  );
}

/* ── Main ── */

export function ProfilePage({ initialTab }: { initialTab: SettingsSection }) {
  const auth = useAuth();
  const user = auth.user;

  const [activeSection, setActiveSection] = useState<SettingsSection>(initialTab);
  const [displayName, setDisplayName] = useState(user?.display_name ?? '');
  const [fullName, setFullName] = useState(user?.full_name ?? '');
  const [jobTitle, setJobTitle] = useState(user?.job_title ?? '');
  const [themePreference, setThemePreference] = useState<ThemePreference>(
    user?.theme_preference ?? 'system',
  );
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [sessions, setSessions] = useState<AuthSessionItem[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(false);

  useEffect(() => { setActiveSection(initialTab); }, [initialTab]);

  useEffect(() => {
    if (!user) return;
    setDisplayName(user.display_name);
    setFullName(user.full_name);
    setJobTitle(user.job_title ?? '');
    setThemePreference(user.theme_preference);
  }, [user]);

  useEffect(() => {
    if (activeSection !== 'security') return;
    let cancelled = false;

    async function loadSessions() {
      setLoadingSessions(true);
      try {
        const items = await auth.listSessions();
        if (!cancelled) setSessions(items);
      } catch (caughtError) {
        if (!cancelled) setError(getErrorMessage(caughtError, '세션 목록을 불러오지 못했습니다.'));
      } finally {
        if (!cancelled) setLoadingSessions(false);
      }
    }

    void loadSessions();
    return () => { cancelled = true; };
  }, [activeSection]);

  if (!user) return null;

  async function handleProfileSubmit(event: React.FormEvent<HTMLFormElement>) {
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
      setMessage('변경사항을 저장했습니다.');
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '저장하지 못했습니다.'));
    } finally {
      setSubmitting(false);
    }
  }

  async function handlePasswordSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    setError(null);
    try {
      await auth.changePassword({ current_password: currentPassword, new_password: newPassword });
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
      const items = await auth.listSessions();
      setSessions(items);
      setMessage('세션을 종료했습니다.');
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '세션을 종료하지 못했습니다.'));
    }
  }

  function handleSectionChange(section: SettingsSection) {
    setActiveSection(section);
    setMessage(null);
    setError(null);
  }

  function getUserInitials(name: string) {
    return name.trim().split(/\s+/).slice(0, 2).map((p) => p[0]?.toUpperCase() ?? '').join('') || 'ID';
  }

  const navItems = [
    { id: 'profile' as const, label: 'Profile', icon: User },
    { id: 'appearance' as const, label: 'Appearance', icon: Palette },
    { id: 'security' as const, label: 'Security', icon: Shield },
    { id: 'notifications' as const, label: 'Notifications', icon: Bell },
  ];

  return (
    <div className="h-full overflow-y-auto custom-scrollbar">
      <div className="mx-auto max-w-5xl px-8 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <h1 className="app-text-title-lg text-app-ink">My Settings</h1>
          <button
            className="app-text-control flex items-center gap-2 rounded-md px-3 py-1.5 text-red-500 transition-colors hover:bg-red-500/10"
            onClick={() => { void auth.logout(); }}
            type="button"
          >
            <LogOut size={15} />
            Sign Out
          </button>
        </div>

        {/* Feedback */}
        {message ? <div className="mb-4"><InlineNotice tone="success">{String(message)}</InlineNotice></div> : null}
        {error ? <div className="mb-4"><InlineNotice tone="danger">{String(error)}</InlineNotice></div> : null}

        <div className="grid grid-cols-[200px_1fr] gap-10 max-[820px]:grid-cols-1 max-[820px]:gap-6">
          {/* Left Nav */}
          <nav className="space-y-1">
            {navItems.map((item) => (
              <button
                key={item.id}
                onClick={() => handleSectionChange(item.id)}
                type="button"
                className={cn(
                  'app-text-control w-full flex items-center gap-2.5 rounded-md px-3 py-2 text-left transition-colors',
                  activeSection === item.id
                    ? 'bg-app-surface-hover text-app-ink font-medium'
                    : 'text-gray-500 hover:text-app-ink hover:bg-app-surface-hover/50',
                )}
              >
                <item.icon size={15} />
                {item.label}
              </button>
            ))}
          </nav>

          {/* Content */}
          <div className="min-w-0">

            {/* ── Profile ── */}
            {activeSection === 'profile' && (
              <div>
                <SectionHeader title="Profile" description="Manage your personal information." />

                <form onSubmit={(event) => void handleProfileSubmit(event)}>
                  <div className="border-t border-app-border">
                    <FieldRow label="Avatar">
                      <div className="flex items-center gap-4">
                        <div className="app-text-title-md flex h-12 w-12 items-center justify-center rounded-full bg-orange-500 font-bold text-white">
                          {getUserInitials(user.display_name || user.full_name)}
                        </div>
                        <div className="app-text-body">
                          <p className="font-medium text-app-ink">{user.display_name || user.full_name}</p>
                          <p className="app-text-caption text-gray-500">{user.email}</p>
                        </div>
                      </div>
                    </FieldRow>

                    <FieldRow label="Display Name">
                      <input
                        className={fieldClassName}
                        onChange={(e) => setDisplayName(e.target.value)}
                        value={displayName}
                      />
                    </FieldRow>

                    <FieldRow label="Full Name">
                      <input
                        className={fieldClassName}
                        onChange={(e) => setFullName(e.target.value)}
                        value={fullName}
                      />
                    </FieldRow>

                    <FieldRow label="Email Address" description="Contact your admin to change.">
                      <input className={cn(fieldClassName, 'opacity-60')} disabled value={user.email} />
                    </FieldRow>

                    <FieldRow label="Job Title">
                      <input
                        className={fieldClassName}
                        onChange={(e) => setJobTitle(e.target.value)}
                        placeholder="e.g. Platform Owner"
                        value={jobTitle}
                      />
                    </FieldRow>

                    <FieldRow label="Organization">
                      <input className={cn(fieldClassName, 'opacity-60')} disabled value={user.primary_org_unit?.name ?? '미지정'} />
                    </FieldRow>

                    <FieldRow label="Role">
                      <span className="app-text-body text-app-ink">
                        {(user.system_roles ?? []).length > 0 ? user.system_roles.join(', ') : 'Member'}
                      </span>
                    </FieldRow>

                    <FieldRow label="Groups">
                      <span className="app-text-body text-app-ink">{user.group_slugs.join(', ') || '없음'}</span>
                    </FieldRow>
                  </div>

                  <div className="flex justify-end gap-3 pt-6">
                    <Button
                      variant="ghost"
                      type="button"
                      onClick={() => {
                        setDisplayName(user.display_name);
                        setFullName(user.full_name);
                        setJobTitle(user.job_title ?? '');
                        setMessage(null);
                        setError(null);
                      }}
                    >
                      Reset
                    </Button>
                    <Button variant="primary" type="submit" disabled={submitting}>
                      {submitting ? 'Saving...' : 'Save Changes'}
                    </Button>
                  </div>
                </form>
              </div>
            )}

            {/* ── Appearance ── */}
            {activeSection === 'appearance' && (
              <div>
                <SectionHeader title="Appearance" description="Customize how the app looks." />

                <div className="border-t border-app-border">
                  <FieldRow label="Theme" description="Select your preferred color scheme.">
                    <div className="flex gap-2">
                      {themeOptions.map((opt) => (
                        <button
                          key={opt.value}
                          type="button"
                          onClick={() => {
                            setThemePreference(opt.value);
                            void auth.updatePreferences({ theme_preference: opt.value });
                          }}
                          className={cn(
                            'app-text-control flex items-center gap-2 rounded-md border px-4 py-2.5 transition-colors',
                            themePreference === opt.value
                              ? 'border-app-accent bg-app-accent/10 text-app-accent'
                              : 'border-app-border bg-app-bg text-app-ink hover:border-app-ink/30',
                          )}
                        >
                          <opt.icon size={15} />
                          {opt.label}
                        </button>
                      ))}
                    </div>
                  </FieldRow>
                </div>
              </div>
            )}

            {/* ── Security ── */}
            {activeSection === 'security' && (
              <div>
                <SectionHeader title="Security" description="Manage your password and sessions." />

                <div className="border-t border-app-border">
                  {auth.user?.must_change_password ? (
                    <div className="py-4">
                      <InlineNotice tone="warning">
                        비밀번호 변경이 필요합니다.
                      </InlineNotice>
                    </div>
                  ) : null}

                  <form onSubmit={(event) => void handlePasswordSubmit(event)}>
                    <FieldRow label="Current Password">
                      <input
                        className={fieldClassName}
                        onChange={(e) => setCurrentPassword(e.target.value)}
                        placeholder="••••••••"
                        type="password"
                        value={currentPassword}
                      />
                    </FieldRow>

                    <FieldRow label="New Password">
                      <input
                        className={fieldClassName}
                        onChange={(e) => setNewPassword(e.target.value)}
                        placeholder="••••••••"
                        type="password"
                        value={newPassword}
                      />
                    </FieldRow>

                    <div className="py-4">
                      <Button variant="primary" type="submit">
                        Update Password
                      </Button>
                    </div>
                  </form>
                </div>

                <div className="mt-8">
                  <h3 className="app-text-title-md mb-1 text-app-ink">Active Sessions</h3>
                  <p className="app-text-caption mb-4 text-gray-500">
                    Review and revoke browser sessions.
                  </p>
                  {loadingSessions ? (
                    <p className="app-text-body text-gray-500">불러오는 중...</p>
                  ) : (() => {
                    const active = sessions.filter((s) => !s.revoked_at);
                    const current = active.filter((s) => s.is_current);
                    const others = active.filter((s) => !s.is_current).slice(0, 3);
                    const shown = [...current, ...others];
                    const hiddenCount = active.length - shown.length;

                    return (
                      <div className="grid gap-2">
                        {shown.map((session) => (
                          <SessionCard key={session.id} onRevoke={handleRevoke} session={session} />
                        ))}
                        {hiddenCount > 0 && (
                          <p className="app-text-caption py-2 text-center text-gray-500">
                            외 {hiddenCount}개 세션
                          </p>
                        )}
                      </div>
                    );
                  })()}
                </div>
              </div>
            )}

            {/* ── Notifications ── */}
            {activeSection === 'notifications' && (
              <div>
                <SectionHeader title="Notifications" description="Choose what you get notified about." />

                <div className="border-t border-app-border">
                  <InlineNotice tone="warning" className="mt-4">
                    알림 설정은 아직 연결되지 않았습니다.
                  </InlineNotice>

                  {[
                    { title: 'Workspace Updates', desc: 'Important changes in your assigned workspaces', email: true, push: true },
                    { title: 'Security Events', desc: 'Password changes and suspicious login attempts', email: true, push: true },
                    { title: 'Weekly Digest', desc: 'Summary of your access and workspaces', email: true, push: false },
                  ].map((item) => (
                    <div
                      key={item.title}
                      className="flex items-center justify-between py-4 border-b border-app-border last:border-b-0"
                    >
                      <div>
                        <div className="app-text-body font-medium text-app-ink">{item.title}</div>
                        <div className="app-text-caption mt-0.5 text-gray-500">{item.desc}</div>
                      </div>
                      <div className="flex items-center gap-5">
                        <label className="flex items-center gap-1.5 cursor-pointer">
                          <input
                            className="h-3.5 w-3.5 rounded border-app-border bg-app-bg accent-app-accent"
                            defaultChecked={item.email}
                            type="checkbox"
                          />
                          <span className="app-text-caption text-gray-500">Email</span>
                        </label>
                        <label className="flex items-center gap-1.5 cursor-pointer">
                          <input
                            className="h-3.5 w-3.5 rounded border-app-border bg-app-bg accent-app-accent"
                            defaultChecked={item.push}
                            type="checkbox"
                          />
                          <span className="app-text-caption text-gray-500">Push</span>
                        </label>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

          </div>
        </div>
      </div>
    </div>
  );
}

export function AccountSettingsView() {
  return <ProfilePage initialTab="profile" />;
}

export function SecuritySettingsView() {
  return <ProfilePage initialTab="security" />;
}
