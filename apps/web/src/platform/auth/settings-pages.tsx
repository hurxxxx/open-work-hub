import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
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

import { InlineNotice } from '@ai-do/ui/feedback/inline-notice';
import { Button } from '@ai-do/ui/primitives/button';

import { cn } from '@/src/lib/utils';
import {
  DEFAULT_TIME_ZONE,
  TIME_ZONE_OPTIONS,
  formatDateTime,
  normalizeTimeZone,
} from '@/src/platform/time/time-utils';
import { LOCALE_OPTIONS, normalizeLocale, syncLocale } from '@/src/platform/i18n';

import type { AuthSessionItem, LocalePreference, ThemePreference } from './auth-api';
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

const themeOptions: { value: ThemePreference; labelKey: string; icon: typeof Sun }[] = [
  { value: 'system', labelKey: 'theme.system', icon: Monitor },
  { value: 'light', labelKey: 'theme.light', icon: Sun },
  { value: 'dark', labelKey: 'theme.dark', icon: Moon },
];

const fieldClassName =
  'app-text-body w-full rounded-md border border-app-border bg-app-bg px-3 py-2 text-app-ink transition-colors focus:border-app-accent focus:outline-none';

type SettingsSection = 'profile' | 'appearance' | 'security' | 'notifications';

/* ── Access Denied ── */

export function AccessDeniedView({
  title,
  description,
}: {
  title?: string;
  description?: string;
}) {
  const { t } = useTranslation('auth');
  return (
    <div className="p-6">
      <div className="rounded-xl border border-app-border bg-app-surface-sidebar p-6">
        <h2 className="app-text-title-md mb-2 text-app-ink">{title ?? t('accessDenied.title')}</h2>
        <p className="app-text-body mb-4 text-gray-500">{description ?? t('accessDenied.description')}</p>
        <InlineNotice tone="warning">
          {t('accessDenied.requestAccess')}
        </InlineNotice>
      </div>
    </div>
  );
}

/* ── Not Found ── */

export function NotFoundView({
  title,
  description,
}: {
  title?: string;
  description?: string;
}) {
  const { t } = useTranslation('auth');
  return (
    <div className="p-6">
      <div className="rounded-xl border border-app-border bg-app-surface-sidebar p-6">
        <h2 className="app-text-title-md mb-2 text-app-ink">{title ?? t('notFound.title')}</h2>
        <p className="app-text-body mb-4 text-gray-500">{description ?? t('notFound.description')}</p>
        <InlineNotice tone="info">
          {t('notFound.hint')}
        </InlineNotice>
      </div>
    </div>
  );
}

/* ── Session Card ── */

function SessionCard({
  session,
  timeZone,
  locale,
  onRevoke,
}: {
  session: AuthSessionItem;
  timeZone: string;
  locale: string;
  onRevoke: (sessionId: string) => Promise<void>;
}) {
  const { t } = useTranslation('auth');
  return (
    <div className="flex items-start justify-between gap-4 rounded-md border border-app-border bg-app-bg px-4 py-3">
      <div className="app-text-body grid gap-1">
        <span className="font-medium text-app-ink">
          {session.is_current ? t('settings.sessionCurrent') : t('settings.sessionStored')}
        </span>
        <span className="app-text-caption text-gray-500">
          {t('settings.sessionCreated')}: {formatDateTime(session.created_at, {
            dateStyle: 'medium',
            fallback: t('common:empty.none'),
            locale,
            timeStyle: 'short',
            timeZone,
          })}
        </span>
        <span className="app-text-caption text-gray-500">
          {t('settings.sessionExpires')}: {formatDateTime(session.expires_at, {
            dateStyle: 'medium',
            fallback: t('common:empty.none'),
            locale,
            timeStyle: 'short',
            timeZone,
          })}
        </span>
        <span className="app-text-caption text-gray-500">
          {t('settings.sessionLastSeen')}: {formatDateTime(session.last_seen_at, {
            dateStyle: 'medium',
            fallback: t('common:empty.none'),
            locale,
            timeStyle: 'short',
            timeZone,
          })}
        </span>
        <span className="app-text-caption max-w-[360px] truncate text-gray-500">
          {session.user_agent ?? t('common:feedback.unknown')}
        </span>
        <span className="app-text-caption text-gray-500">IP: {session.ip_address ?? t('common:feedback.unknown')}</span>
      </div>
      {!session.is_current && !session.revoked_at ? (
        <Button
          onClick={() => { void onRevoke(session.id); }}
          size="dense"
          variant="secondary"
        >
          {t('settings.sessionRevoke')}
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
  const { t, i18n } = useTranslation(['auth', 'common']);
  const auth = useAuth();
  const user = auth.user;

  const [activeSection, setActiveSection] = useState<SettingsSection>(initialTab);
  const [displayName, setDisplayName] = useState(user?.display_name ?? '');
  const [fullName, setFullName] = useState(user?.full_name ?? '');
  const [jobTitle, setJobTitle] = useState(user?.job_title ?? '');
  const [themePreference, setThemePreference] = useState<ThemePreference>(
    user?.theme_preference ?? 'system',
  );
  const [timeZone, setTimeZone] = useState(user?.time_zone ?? DEFAULT_TIME_ZONE);
  const [locale, setLocale] = useState<LocalePreference>(normalizeLocale(user?.locale));
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [sessions, setSessions] = useState<AuthSessionItem[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const { listSessions } = auth;

  useEffect(() => { setActiveSection(initialTab); }, [initialTab]);

  useEffect(() => {
    if (!user) return;
    setDisplayName(user.display_name);
    setFullName(user.full_name);
    setJobTitle(user.job_title ?? '');
    setThemePreference(user.theme_preference);
    setTimeZone(normalizeTimeZone(user.time_zone));
    setLocale(normalizeLocale(user.locale));
  }, [user]);

  useEffect(() => {
    if (activeSection !== 'security') return;
    let cancelled = false;

    async function loadSessions() {
      setLoadingSessions(true);
      try {
        const items = await listSessions();
        if (!cancelled) setSessions(items);
      } catch (caughtError) {
        if (!cancelled) setError(getErrorMessage(caughtError, t('auth:settings.sessionsLoadFailed')));
      } finally {
        if (!cancelled) setLoadingSessions(false);
      }
    }

    void loadSessions();
    return () => { cancelled = true; };
  }, [activeSection, listSessions, t]);

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
        locale,
        time_zone: timeZone,
      });
      setMessage(t('auth:settings.saved'));
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, t('auth:settings.saveFailed')));
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
      setMessage(t('auth:settings.passwordChanged'));
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, t('auth:settings.passwordChangeFailed')));
    }
  }

  async function handleRevoke(sessionId: string) {
    setMessage(null);
    setError(null);
    try {
      await auth.revokeSession(sessionId);
      const items = await auth.listSessions();
      setSessions(items);
      setMessage(t('auth:settings.sessionRevoked'));
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, t('auth:settings.sessionRevokeFailed')));
    }
  }

  function handleSectionChange(section: SettingsSection) {
    setActiveSection(section);
    setMessage(null);
    setError(null);
  }

  async function saveThemePreference(nextThemePreference: ThemePreference) {
    if (nextThemePreference === themePreference) return;
    const previousThemePreference = themePreference;
    setMessage(null);
    setError(null);
    setThemePreference(nextThemePreference);
    try {
      await auth.updatePreferences({ theme_preference: nextThemePreference });
    } catch (caughtError) {
      setThemePreference(previousThemePreference);
      setError(getErrorMessage(caughtError, t('auth:settings.saveFailed')));
    }
  }

  async function saveLocalePreference(nextLocaleValue: string) {
    const previousLocale = locale;
    const nextLocale = normalizeLocale(nextLocaleValue);
    if (nextLocale === previousLocale) return;
    setMessage(null);
    setError(null);
    setLocale(nextLocale);
    syncLocale(nextLocale);
    try {
      await auth.updatePreferences({ locale: nextLocale });
    } catch (caughtError) {
      setLocale(previousLocale);
      syncLocale(previousLocale);
      setError(getErrorMessage(caughtError, t('auth:settings.saveFailed')));
    }
  }

  async function saveTimeZonePreference(nextTimeZoneValue: string) {
    const previousTimeZone = timeZone;
    const nextTimeZone = normalizeTimeZone(nextTimeZoneValue);
    if (nextTimeZone === previousTimeZone) return;
    setMessage(null);
    setError(null);
    setTimeZone(nextTimeZone);
    try {
      await auth.updatePreferences({ time_zone: nextTimeZone });
    } catch (caughtError) {
      setTimeZone(previousTimeZone);
      setError(getErrorMessage(caughtError, t('auth:settings.saveFailed')));
    }
  }

  function getUserInitials(name: string) {
    return name.trim().split(/\s+/).slice(0, 2).map((p) => p[0]?.toUpperCase() ?? '').join('') || 'ID';
  }

  const navItems = [
    { id: 'profile' as const, label: t('auth:settings.profile'), icon: User },
    { id: 'appearance' as const, label: t('auth:settings.appearance'), icon: Palette },
    { id: 'security' as const, label: t('auth:settings.security'), icon: Shield },
    { id: 'notifications' as const, label: t('auth:settings.notifications'), icon: Bell },
  ];

  return (
    <div className="h-full overflow-y-auto custom-scrollbar">
      <div className="mx-auto max-w-5xl px-8 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <h1 className="app-text-title-lg text-app-ink">{t('auth:settings.mySettings')}</h1>
          <button
            className="app-text-control flex items-center gap-2 rounded-md px-3 py-1.5 text-red-500 transition-colors hover:bg-red-500/10"
            onClick={() => { void auth.logout(); }}
            type="button"
          >
            <LogOut size={15} />
            {t('common:actions.signOut')}
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
                <SectionHeader title={t('auth:settings.profile')} description={t('auth:settings.manageProfile')} />

                <form onSubmit={(event) => void handleProfileSubmit(event)}>
                  <div className="border-t border-app-border">
                    <FieldRow label={t('auth:settings.avatar')}>
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

                    <FieldRow label={t('auth:settings.displayName')}>
                      <input
                        className={fieldClassName}
                        onChange={(e) => setDisplayName(e.target.value)}
                        value={displayName}
                      />
                    </FieldRow>

                    <FieldRow label={t('auth:settings.fullName')}>
                      <input
                        className={fieldClassName}
                        onChange={(e) => setFullName(e.target.value)}
                        value={fullName}
                      />
                    </FieldRow>

                    <FieldRow label={t('auth:settings.emailAddress')} description={t('auth:settings.emailChangeHint')}>
                      <input className={cn(fieldClassName, 'opacity-60')} disabled value={user.email} />
                    </FieldRow>

                    <FieldRow label={t('auth:settings.jobTitle')}>
                      <input
                        className={fieldClassName}
                        onChange={(e) => setJobTitle(e.target.value)}
                        placeholder={t('auth:settings.jobTitlePlaceholder')}
                        value={jobTitle}
                      />
                    </FieldRow>

                    <FieldRow label={t('auth:settings.organization')}>
                      <input className={cn(fieldClassName, 'opacity-60')} disabled value={user.primary_org_unit?.name ?? t('common:empty.none')} />
                    </FieldRow>

                    <FieldRow label={t('auth:settings.role')}>
                      <span className="app-text-body text-app-ink">
                        {(user.system_roles ?? []).length > 0 ? user.system_roles.join(', ') : 'Member'}
                      </span>
                    </FieldRow>

                    <FieldRow label={t('auth:settings.groups')}>
                      <span className="app-text-body text-app-ink">{user.group_slugs.join(', ') || t('common:empty.none')}</span>
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
                        setTimeZone(normalizeTimeZone(user.time_zone));
                        setLocale(normalizeLocale(user.locale));
                        setMessage(null);
                        setError(null);
                      }}
                    >
                      {t('common:actions.reset')}
                    </Button>
                    <Button variant="primary" type="submit" disabled={submitting}>
                      {submitting ? t('common:actions.saving') : t('common:actions.saveChanges')}
                    </Button>
                  </div>
                </form>
              </div>
            )}

            {/* ── Appearance ── */}
            {activeSection === 'appearance' && (
              <div>
                <SectionHeader title={t('auth:settings.appearance')} description={t('auth:settings.customizeAppearance')} />

                <div className="border-t border-app-border">
                  <FieldRow label={t('auth:settings.theme')} description={t('auth:settings.themeDescription')}>
                    <div className="flex gap-2">
                      {themeOptions.map((opt) => (
                        <button
                          key={opt.value}
                          type="button"
                          onClick={() => { void saveThemePreference(opt.value); }}
                          className={cn(
                            'app-text-control flex items-center gap-2 rounded-md border px-4 py-2.5 transition-colors',
                            themePreference === opt.value
                              ? 'border-app-accent bg-app-accent/10 text-app-accent'
                              : 'border-app-border bg-app-bg text-app-ink hover:border-app-ink/30',
                          )}
                        >
                          <opt.icon size={15} />
                          {t(`auth:${opt.labelKey}`)}
                        </button>
                      ))}
                    </div>
                  </FieldRow>
                  <FieldRow label={t('auth:settings.language')} description={t('auth:settings.languageDescription')}>
                    <select
                      className={fieldClassName}
                      onChange={(event) => { void saveLocalePreference(event.target.value); }}
                      value={locale}
                    >
                      {LOCALE_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </FieldRow>
                  <FieldRow label={t('auth:settings.timeZone')} description={t('auth:settings.timeZoneDescription')}>
                    <select
                      className={fieldClassName}
                      onChange={(event) => { void saveTimeZonePreference(event.target.value); }}
                      value={timeZone}
                    >
                      {TIME_ZONE_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {t(option.labelKey)}
                        </option>
                      ))}
                    </select>
                  </FieldRow>
                </div>
              </div>
            )}

            {/* ── Security ── */}
            {activeSection === 'security' && (
              <div>
                <SectionHeader title={t('auth:settings.security')} description={t('auth:settings.managePassword')} />

                <div className="border-t border-app-border">
                  {auth.user?.must_change_password ? (
                    <div className="py-4">
                      <InlineNotice tone="warning">
                        {t('auth:settings.passwordRequired')}
                      </InlineNotice>
                    </div>
                  ) : null}

                  <form onSubmit={(event) => void handlePasswordSubmit(event)}>
                    <FieldRow label={t('auth:settings.currentPassword')}>
                      <input
                        className={fieldClassName}
                        onChange={(e) => setCurrentPassword(e.target.value)}
                        placeholder="••••••••"
                        type="password"
                        value={currentPassword}
                      />
                    </FieldRow>

                    <FieldRow label={t('auth:settings.newPassword')}>
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
                        {t('auth:settings.updatePassword')}
                      </Button>
                    </div>
                  </form>
                </div>

                <div className="mt-8">
                  <h3 className="app-text-title-md mb-1 text-app-ink">{t('auth:settings.activeSessions')}</h3>
                  <p className="app-text-caption mb-4 text-gray-500">
                    {t('auth:settings.reviewSessions')}
                  </p>
                  {loadingSessions ? (
                    <p className="app-text-body text-gray-500">{t('common:feedback.loading')}</p>
                  ) : (() => {
                    const active = sessions.filter((s) => !s.revoked_at);
                    const current = active.filter((s) => s.is_current);
                    const others = active.filter((s) => !s.is_current).slice(0, 3);
                    const shown = [...current, ...others];
                    const hiddenCount = active.length - shown.length;

                    return (
                      <div className="grid gap-2">
                        {shown.map((session) => (
                          <SessionCard
                            key={session.id}
                            onRevoke={handleRevoke}
                            session={session}
                            locale={i18n.language}
                            timeZone={normalizeTimeZone(user.time_zone)}
                          />
                        ))}
                        {hiddenCount > 0 && (
                          <p className="app-text-caption py-2 text-center text-gray-500">
                            {t('auth:settings.sessionsMore', { count: hiddenCount })}
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
                <SectionHeader title={t('auth:settings.notifications')} description={t('auth:settings.notificationsDescription')} />

                <div className="border-t border-app-border">
                  <InlineNotice tone="warning" className="mt-4">
                    {t('auth:settings.notificationsNotConnected')}
                  </InlineNotice>

                  {[
                    {
                      title: t('auth:settings.notificationsWorkspaceTitle'),
                      desc: t('auth:settings.notificationsWorkspaceDescription'),
                      email: true,
                      push: true,
                    },
                    {
                      title: t('auth:settings.notificationsSecurityTitle'),
                      desc: t('auth:settings.notificationsSecurityDescription'),
                      email: true,
                      push: true,
                    },
                    {
                      title: t('auth:settings.notificationsWeeklyTitle'),
                      desc: t('auth:settings.notificationsWeeklyDescription'),
                      email: true,
                      push: false,
                    },
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
                          <span className="app-text-caption text-gray-500">{t('auth:settings.notificationsChannelEmail')}</span>
                        </label>
                        <label className="flex items-center gap-1.5 cursor-pointer">
                          <input
                            className="h-3.5 w-3.5 rounded border-app-border bg-app-bg accent-app-accent"
                            defaultChecked={item.push}
                            type="checkbox"
                          />
                          <span className="app-text-caption text-gray-500">{t('auth:settings.notificationsChannelPush')}</span>
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
