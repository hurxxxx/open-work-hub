import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Hash, Settings } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { AppSidebarConfig } from '@/src/app/shell/sidebar-types';
import { cn } from '@/src/lib/utils';
import { hasAdminConsoleAccess } from '@/src/platform/auth/auth-api';
import { useAuth } from '@/src/platform/auth/auth-provider';

import {
  listCommunityChannels,
  type CommunityChannel,
} from './api/community-api';
import { buildCommunityListUrl } from './community-url';
import { DEFAULT_COMMUNITY_CHANNEL_KEY } from './community-constants';

function CommunitySidebarChannels({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useTranslation('apps');
  const { search } = useLocation();
  const { token, user } = useAuth();
  const [channels, setChannels] = useState<CommunityChannel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const activeChannelKey =
    new URLSearchParams(search).get('channel') || DEFAULT_COMMUNITY_CHANNEL_KEY;
  const canManageChannels = hasAdminConsoleAccess(user);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    listCommunityChannels(token)
      .then((response) => {
        if (cancelled) return;
        setChannels(response.channels);
      })
      .catch(() => {
        if (cancelled) return;
        setChannels([]);
        setError(t('community.errors.channelsFailed'));
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [t, token]);

  const channelHrefByKey = useMemo(() => {
    const hrefByKey = new Map<string, string>();
    for (const channel of channels) {
      hrefByKey.set(channel.key, buildCommunityListUrl(channel.key));
    }
    return hrefByKey;
  }, [channels]);

  const handleNavigate = useCallback(() => {
    onNavigate?.();
  }, [onNavigate]);

  return (
    <div className="space-y-5">
      <section className="space-y-1">
        <div className="sidebar-section-label px-3 py-1 text-app-ink/60">
          {t('community.channelsLabel')}
        </div>

        {loading && channels.length === 0 ? (
          <div className="sidebar-submenu-group text-app-ink/60">
            {t('community.loading')}
          </div>
        ) : null}

        {channels.map((channel) => (
          <Link
            className={cn(
              'sidebar-submenu-item ml-1',
              channel.key === activeChannelKey && 'sidebar-submenu-item-active',
            )}
            key={channel.key}
            onClick={handleNavigate}
            to={channelHrefByKey.get(channel.key) ?? buildCommunityListUrl()}
          >
            <Hash size={16} className="text-app-ink/55 dark:text-app-ink/65" />
            <span className="sidebar-submenu-label">
              {t(`community.channels.${channel.key}`, {
                defaultValue: channel.name,
              })}
            </span>
          </Link>
        ))}

        {error ? (
          <div className="px-3 py-2 app-text-caption text-app-danger dark:text-app-danger-text">
            {error}
          </div>
        ) : null}
      </section>

      {canManageChannels ? (
        <section className="border-t border-app-border pt-3">
          <Link
            className="sidebar-submenu-item ml-1"
            onClick={handleNavigate}
            to="/admin/community"
          >
            <Settings
              size={16}
              className="text-app-ink/55 dark:text-app-ink/65"
            />
            <span className="sidebar-submenu-label">
              {t('community.channelManager.open')}
            </span>
          </Link>
        </section>
      ) : null}
    </div>
  );
}

export const communitySidebarConfig: AppSidebarConfig = {
  beforeCategories: (context) => (
    <CommunitySidebarChannels onNavigate={context.onNavigate} />
  ),
  // The registered root item validates the server bootstrap contract. Channel
  // navigation owns this sidebar, so the generic root category stays hidden.
  extendCategories: () => [],
};
