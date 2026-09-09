import { formatDateTime } from '@/src/platform/time/time-utils';
import { Button } from '@open-work-hub/ui/primitives/button';

import type { AuthSessionItem } from './auth-api';
import type { SettingsTranslator } from './settings-page-model';

export function SessionCard({
  session,
  timeZone,
  locale,
  onRevoke,
  t,
}: {
  session: AuthSessionItem;
  timeZone: string;
  locale: string;
  onRevoke: (sessionId: string) => Promise<void>;
  t: SettingsTranslator;
}) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-md border border-app-border bg-app-bg px-4 py-3">
      <div className="app-text-body grid gap-1">
        <span className="font-medium text-app-ink">
          {session.is_current
            ? t('auth:settings.sessionCurrent')
            : t('auth:settings.sessionStored')}
        </span>
        <span className="app-text-caption text-app-ink/55">
          {t('auth:settings.sessionCreated')}:{' '}
          {formatDateTime(session.created_at, {
            dateStyle: 'medium',
            fallback: t('common:empty.none'),
            locale,
            timeStyle: 'short',
            timeZone,
          })}
        </span>
        <span className="app-text-caption text-app-ink/55">
          {t('auth:settings.sessionExpires')}:{' '}
          {formatDateTime(session.expires_at, {
            dateStyle: 'medium',
            fallback: t('common:empty.none'),
            locale,
            timeStyle: 'short',
            timeZone,
          })}
        </span>
        <span className="app-text-caption text-app-ink/55">
          {t('auth:settings.sessionLastSeen')}:{' '}
          {formatDateTime(session.last_seen_at, {
            dateStyle: 'medium',
            fallback: t('common:empty.none'),
            locale,
            timeStyle: 'short',
            timeZone,
          })}
        </span>
        <span className="app-text-caption max-w-[360px] truncate text-app-ink/55">
          {session.user_agent ?? t('common:feedback.unknown')}
        </span>
        <span className="app-text-caption text-app-ink/55">
          IP: {session.ip_address ?? t('common:feedback.unknown')}
        </span>
      </div>
      {!session.is_current && !session.revoked_at ? (
        <Button
          onClick={() => {
            void onRevoke(session.id);
          }}
          size="dense"
          variant="secondary"
        >
          {t('auth:settings.sessionRevoke')}
        </Button>
      ) : null}
    </div>
  );
}
