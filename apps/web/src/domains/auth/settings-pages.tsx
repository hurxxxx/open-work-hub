import { useEffect, useState } from 'react';
import { motion } from 'motion/react';
import {
  Bell,
  Camera,
  Calendar,
  CheckCircle,
  LogOut,
  Settings,
  Shield,
  User,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';

import { Button, InlineNotice, Panel, Select } from '@aidoo/ui';

import { cn } from '@/src/lib/utils';

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

const fieldClassName =
  'w-full rounded-lg border border-clickup-border bg-clickup-bg px-4 py-2 text-sm text-clickup-text focus:border-clickup-purple focus:outline-none';

type ProfileTab = 'overview' | 'settings' | 'security' | 'notifications';

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

function getUserInitials(fullName: string) {
  const initials = fullName
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('');

  return initials || 'ID';
}

function SessionCard({
  session,
  onRevoke,
}: {
  session: AuthSessionItem;
  onRevoke: (sessionId: string) => Promise<void>;
}) {
  return (
    <div className="rounded-xl border border-clickup-border bg-clickup-bg p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-sm font-medium text-clickup-text">
            {session.is_current ? '현재 세션' : '저장된 세션'}
          </div>
          <div className="mt-1 text-xs text-gray-500">
            생성: {new Date(session.created_at).toLocaleString()}
          </div>
        </div>
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
      <div className="mt-3 grid gap-1 text-xs text-gray-500">
        <span>만료: {new Date(session.expires_at).toLocaleString()}</span>
        <span>
          최근 사용:{' '}
          {session.last_seen_at ? new Date(session.last_seen_at).toLocaleString() : '없음'}
        </span>
        <span>에이전트: {session.user_agent ?? '알 수 없음'}</span>
        <span>IP: {session.ip_address ?? '알 수 없음'}</span>
      </div>
    </div>
  );
}

function ProfilePage({ initialTab }: { initialTab: ProfileTab }) {
  const auth = useAuth();
  const navigate = useNavigate();
  const user = auth.user;
  const [activeTab, setActiveTab] = useState<ProfileTab>(initialTab);
  const [displayName, setDisplayName] = useState(user?.display_name ?? '');
  const [fullName, setFullName] = useState(user?.full_name ?? '');
  const [jobTitle, setJobTitle] = useState('');
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

  useEffect(() => {
    setActiveTab(initialTab);
  }, [initialTab]);

  useEffect(() => {
    if (!user) {
      return;
    }

    setDisplayName(user.display_name);
    setFullName(user.full_name);
    setThemePreference(user.theme_preference);
  }, [user]);

  useEffect(() => {
    if (activeTab !== 'security') {
      return;
    }

    let cancelled = false;

    async function loadSessions() {
      setLoadingSessions(true);
      try {
        const items = await auth.listSessions();
        if (!cancelled) {
          setSessions(items);
        }
      } catch (caughtError) {
        if (!cancelled) {
          setError(getErrorMessage(caughtError, '세션 목록을 불러오지 못했습니다.'));
        }
      } finally {
        if (!cancelled) {
          setLoadingSessions(false);
        }
      }
    }

    void loadSessions();

    return () => {
      cancelled = true;
    };
  }, [activeTab]);

  if (!user) {
    return null;
  }

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
      setMessage('프로필 설정을 저장했습니다.');
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '프로필 설정을 저장하지 못했습니다.'));
    } finally {
      setSubmitting(false);
    }
  }

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
      const items = await auth.listSessions();
      setSessions(items);
      setMessage('세션을 종료했습니다.');
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '세션을 종료하지 못했습니다.'));
    }
  }

  function handleTabChange(tab: ProfileTab) {
    setActiveTab(tab);
    if (tab === 'security') {
      navigate('/settings/security');
      return;
    }

    navigate('/settings/account');
  }

  const tabs = [
    { id: 'overview', label: 'Overview', icon: User },
    { id: 'settings', label: 'Settings', icon: Settings },
    { id: 'security', label: 'Security', icon: Shield },
    { id: 'notifications', label: 'Notifications', icon: Bell },
  ] as const;

  const stats = [
    {
      label: 'Workspaces',
      value: String(user.workspace_roles.length),
      icon: CheckCircle,
      color: 'text-green-500',
      bg: 'bg-green-500/10',
    },
    {
      label: 'Permissions',
      value: String(user.permissions.length),
      icon: Shield,
      color: 'text-blue-500',
      bg: 'bg-blue-500/10',
    },
    {
      label: 'Groups',
      value: String(user.group_slugs.length),
      icon: Calendar,
      color: 'text-purple-500',
      bg: 'bg-purple-500/10',
    },
  ];

  const recentActivities = [
    {
      id: 1,
      action: '기본 조직',
      target: user.primary_org_unit?.name ?? '미지정',
      time: 'Organization',
    },
    {
      id: 2,
      action: '테마 설정',
      target:
        themeOptions.find((option) => option.value === user.theme_preference)?.label ??
        '시스템 기본값',
      time: 'Preference',
    },
    {
      id: 3,
      action: '워크스페이스',
      target: user.workspace_roles.map((workspace) => workspace.name).join(', ') || '없음',
      time: 'Access',
    },
    {
      id: 4,
      action: '그룹',
      target: user.group_slugs.join(', ') || '없음',
      time: 'Membership',
    },
  ];

  return (
    <div className="custom-scrollbar h-full overflow-y-auto p-8">
      <div className="mx-auto max-w-6xl">
        <div className="mb-8 flex items-center justify-between">
          <h1 className="text-2xl font-bold text-clickup-text">My Profile</h1>
          <button
            className="flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-red-500 transition-colors hover:bg-red-500/10"
            onClick={() => {
              void auth.logout();
            }}
            type="button"
          >
            <LogOut size={16} />
            Sign Out
          </button>
        </div>

        {message ? (
          <div className="mb-4">
            <InlineNotice tone="success">{message}</InlineNotice>
          </div>
        ) : null}
        {error ? (
          <div className="mb-4">
            <InlineNotice tone="danger">{error}</InlineNotice>
          </div>
        ) : null}

        <div className="grid grid-cols-1 gap-8 lg:grid-cols-4">
          <div className="space-y-6 lg:col-span-1">
            <div className="relative overflow-hidden rounded-xl border border-clickup-border bg-clickup-sidebar p-6 text-center">
              <div className="absolute top-0 left-0 right-0 h-24 bg-gradient-to-r from-clickup-purple/20 to-blue-500/20" />

              <div className="relative mt-8 mb-4">
                <div className="mx-auto flex h-24 w-24 items-center justify-center rounded-full bg-orange-500 text-3xl font-bold text-white shadow-lg">
                  {getUserInitials(user.display_name || user.full_name)}
                </div>
                <button
                  aria-label="아바타 업로드 준비 중"
                  className="absolute right-1/2 bottom-0 translate-x-10 rounded-full border border-clickup-border bg-clickup-bg p-1.5 text-gray-400 opacity-70"
                  disabled
                  title="아바타 업로드 준비 중"
                  type="button"
                >
                  <Camera size={14} />
                </button>
              </div>

              <h2 className="text-xl font-bold text-clickup-text">
                {user.display_name || user.full_name}
              </h2>
              <p className="mb-4 text-sm text-gray-500">
                {jobTitle || user.workspace_roles[0]?.role || 'Workspace Member'}
              </p>

              <div className="mb-6 flex flex-wrap justify-center gap-2">
                <span className="rounded-full border border-clickup-border bg-clickup-bg px-2.5 py-1 text-xs text-gray-400">
                  {user.primary_org_unit?.name ?? '조직 미지정'}
                </span>
                <span className="rounded-full border border-clickup-border bg-clickup-bg px-2.5 py-1 text-xs text-gray-400">
                  {user.is_admin ? 'Admin' : 'Member'}
                </span>
              </div>

              <div className="space-y-4 border-t border-clickup-border pt-6">
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Email</span>
                  <span className="font-medium text-clickup-text">{user.email}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Theme</span>
                  <span className="font-medium text-clickup-text">
                    {themeOptions.find((option) => option.value === user.theme_preference)?.label ??
                      '시스템 기본값'}
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Status</span>
                  <span className="font-medium text-clickup-text">{user.status}</span>
                </div>
              </div>
            </div>

            <div className="rounded-xl border border-clickup-border bg-clickup-sidebar p-2">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  className={cn(
                    'w-full flex items-center gap-3 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors',
                    activeTab === tab.id
                      ? 'bg-clickup-hover text-clickup-text'
                      : 'text-gray-500 hover:bg-clickup-bg hover:text-clickup-text',
                  )}
                  onClick={() => handleTabChange(tab.id)}
                  type="button"
                >
                  <tab.icon size={16} />
                  {tab.label}
                </button>
              ))}
            </div>
          </div>

          <div className="lg:col-span-3">
            <motion.div
              key={activeTab}
              animate={{ opacity: 1, y: 0 }}
              initial={{ opacity: 0, y: 10 }}
              transition={{ duration: 0.2 }}
            >
              {activeTab === 'overview' && (
                <div className="space-y-6">
                  <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                    {stats.map((stat) => (
                      <div
                        key={stat.label}
                        className="flex items-center gap-4 rounded-xl border border-clickup-border bg-clickup-sidebar p-6"
                      >
                        <div
                          className={cn(
                            'flex h-12 w-12 items-center justify-center rounded-xl',
                            stat.bg,
                            stat.color,
                          )}
                        >
                          <stat.icon size={24} />
                        </div>
                        <div>
                          <div className="text-2xl font-bold text-clickup-text">{stat.value}</div>
                          <div className="text-sm text-gray-500">{stat.label}</div>
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="rounded-xl border border-clickup-border bg-clickup-sidebar p-6">
                    <h3 className="mb-6 text-lg font-bold text-clickup-text">Access Snapshot</h3>
                    <div className="space-y-6">
                      {recentActivities.map((activity, index) => (
                        <div key={activity.id} className="relative flex gap-4">
                          {index !== recentActivities.length - 1 ? (
                            <div className="absolute top-8 bottom-[-24px] left-4 w-px bg-clickup-border" />
                          ) : null}
                          <div className="z-10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-clickup-border bg-clickup-bg">
                            <div className="h-2 w-2 rounded-full bg-clickup-purple" />
                          </div>
                          <div className="pt-1.5">
                            <p className="text-sm text-clickup-text">
                              <span className="text-gray-400">{activity.action}</span>{' '}
                              <span className="font-medium">{activity.target}</span>
                            </p>
                            <p className="mt-1 text-xs text-gray-500">{activity.time}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'settings' && (
                <div className="space-y-6 rounded-xl border border-clickup-border bg-clickup-sidebar p-6">
                  <h3 className="mb-6 text-lg font-bold text-clickup-text">Personal Information</h3>

                  <form className="space-y-6" onSubmit={(event) => void handleProfileSubmit(event)}>
                    <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
                      <div className="space-y-2">
                        <label className="text-sm font-medium text-gray-400">Display Name</label>
                        <input
                          className={fieldClassName}
                          onChange={(event) => setDisplayName(event.target.value)}
                          value={displayName}
                        />
                      </div>
                      <div className="space-y-2">
                        <label className="text-sm font-medium text-gray-400">Full Name</label>
                        <input
                          className={fieldClassName}
                          onChange={(event) => setFullName(event.target.value)}
                          value={fullName}
                        />
                      </div>
                      <div className="space-y-2">
                        <label className="text-sm font-medium text-gray-400">Email Address</label>
                        <input
                          className={cn(fieldClassName, 'opacity-70')}
                          disabled
                          value={user.email}
                        />
                      </div>
                      <div className="space-y-2">
                        <label className="text-sm font-medium text-gray-400">Job Title</label>
                        <input
                          className={fieldClassName}
                          onChange={(event) => setJobTitle(event.target.value)}
                          placeholder="Platform Owner"
                          value={jobTitle}
                        />
                      </div>
                      <div className="space-y-2">
                        <label className="text-sm font-medium text-gray-400">Organization</label>
                        <input
                          className={cn(fieldClassName, 'opacity-70')}
                          disabled
                          value={user.primary_org_unit?.name ?? '미지정'}
                        />
                      </div>
                      <div className="space-y-2">
                        <label className="text-sm font-medium text-gray-400">Theme</label>
                        <Select
                          onValueChange={(value) => setThemePreference(value as ThemePreference)}
                          options={themeOptions}
                          value={themePreference}
                        />
                      </div>
                      <div className="space-y-2 md:col-span-2">
                        <label className="text-sm font-medium text-gray-400">Groups</label>
                        <textarea
                          className="w-full resize-none rounded-lg border border-clickup-border bg-clickup-bg px-4 py-2 text-sm text-clickup-text focus:border-clickup-purple focus:outline-none"
                          disabled
                          rows={4}
                          value={user.group_slugs.join(', ') || '없음'}
                        />
                      </div>
                    </div>

                    <div className="flex justify-end gap-3 border-t border-clickup-border pt-6">
                      <button
                        className="px-4 py-2 text-sm font-medium text-gray-400 transition-colors hover:text-clickup-text"
                        onClick={() => {
                          setDisplayName(user.display_name);
                          setFullName(user.full_name);
                          setThemePreference(user.theme_preference);
                          setJobTitle('');
                          setMessage(null);
                          setError(null);
                        }}
                        type="button"
                      >
                        Reset
                      </button>
                      <button
                        className="rounded-lg bg-clickup-purple px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-opacity-90"
                        disabled={submitting}
                        type="submit"
                      >
                        {submitting ? 'Saving...' : 'Save Changes'}
                      </button>
                    </div>
                  </form>
                </div>
              )}

              {activeTab === 'security' && (
                <div className="space-y-8 rounded-xl border border-clickup-border bg-clickup-sidebar p-6">
                  <div>
                    <h3 className="mb-2 text-lg font-bold text-clickup-text">Change Password</h3>
                    <p className="mb-6 text-sm text-gray-500">
                      Update your password associated with your account.
                    </p>

                    <form className="max-w-md space-y-4" onSubmit={(event) => void handlePasswordSubmit(event)}>
                      {auth.user?.must_change_password ? (
                        <InlineNotice tone="warning">
                          현재 계정은 다음 로그인 전에 비밀번호 변경이 필요합니다.
                        </InlineNotice>
                      ) : null}
                      <div className="space-y-2">
                        <label className="text-sm font-medium text-gray-400">Current Password</label>
                        <input
                          className={fieldClassName}
                          onChange={(event) => setCurrentPassword(event.target.value)}
                          placeholder="••••••••"
                          type="password"
                          value={currentPassword}
                        />
                      </div>
                      <div className="space-y-2">
                        <label className="text-sm font-medium text-gray-400">New Password</label>
                        <input
                          className={fieldClassName}
                          onChange={(event) => setNewPassword(event.target.value)}
                          placeholder="••••••••"
                          type="password"
                          value={newPassword}
                        />
                      </div>
                      <button
                        className="mt-2 rounded-lg bg-clickup-purple px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-opacity-90"
                        type="submit"
                      >
                        Update Password
                      </button>
                    </form>
                  </div>

                  <div className="border-t border-clickup-border pt-8">
                    <h3 className="mb-2 text-lg font-bold text-clickup-text">Active Sessions</h3>
                    <p className="mb-6 text-sm text-gray-500">
                      Review browser sessions and revoke the ones you no longer trust.
                    </p>
                    {loadingSessions ? (
                      <p className="m-0 text-sm text-gray-500">세션을 불러오는 중입니다.</p>
                    ) : (
                      <div className="grid gap-3">
                        {sessions.map((session) => (
                          <SessionCard key={session.id} onRevoke={handleRevoke} session={session} />
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {activeTab === 'notifications' && (
                <div className="space-y-6 rounded-xl border border-clickup-border bg-clickup-sidebar p-6">
                  <h3 className="mb-6 text-lg font-bold text-clickup-text">Notification Preferences</h3>
                  <InlineNotice tone="warning">
                    이 탭은 템플릿 화면을 먼저 적용한 상태이며, 저장 기능은 아직 연결되지 않았습니다.
                  </InlineNotice>
                  <div className="space-y-6">
                    {[
                      {
                        title: 'Workspace Updates',
                        desc: 'Important changes in your assigned workspaces',
                        email: true,
                        push: true,
                      },
                      {
                        title: 'Security Events',
                        desc: 'Password changes and suspicious login attempts',
                        email: true,
                        push: true,
                      },
                      {
                        title: 'Weekly Digest',
                        desc: 'Summary of your current access and workspaces',
                        email: true,
                        push: false,
                      },
                    ].map((item) => (
                      <div
                        key={item.title}
                        className="flex items-center justify-between border-b border-clickup-border py-4 last:border-0 last:pb-0"
                      >
                        <div>
                          <div className="font-medium text-clickup-text">{item.title}</div>
                          <div className="text-sm text-gray-500">{item.desc}</div>
                        </div>
                        <div className="flex items-center gap-6">
                          <label className="flex cursor-pointer items-center gap-2">
                            <input
                              className="h-4 w-4 rounded border-clickup-border bg-clickup-bg text-clickup-purple"
                              defaultChecked={item.email}
                              type="checkbox"
                            />
                            <span className="text-sm text-gray-400">Email</span>
                          </label>
                          <label className="flex cursor-pointer items-center gap-2">
                            <input
                              className="h-4 w-4 rounded border-clickup-border bg-clickup-bg text-clickup-purple"
                              defaultChecked={item.push}
                              type="checkbox"
                            />
                            <span className="text-sm text-gray-400">Push</span>
                          </label>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </motion.div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function AccountSettingsView() {
  return <ProfilePage initialTab="overview" />;
}

export function SecuritySettingsView() {
  return <ProfilePage initialTab="security" />;
}
