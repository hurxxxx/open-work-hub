import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { motion } from 'motion/react';
import { X, Check, CheckCheck, Loader2 } from 'lucide-react';
import { Button } from '@aidoo/ui/primitives/button';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { formatRelativeTime, normalizeTimeZone } from '@/src/platform/time/time-utils';
import {
  listNotifications,
  markNotificationRead,
  markAllNotificationsRead,
  type WorkspaceNotification,
} from '@/src/platform/notifications/notifications-api';

function timeAgo(dateStr: string, timeZone: string, locale: string): string {
  return formatRelativeTime(dateStr, { locale, timeZone });
}

export function NotificationPanel({
  onClose,
  onNavigateToIssue,
  onCountChange,
  workspaceSlug,
}: {
  onClose: () => void;
  onNavigateToIssue?: (issueId: string) => void;
  onCountChange?: (count: number) => void;
  workspaceSlug: string | null;
}) {
  const { token, user } = useAuth();
  const { t, i18n } = useTranslation('shell');
  const timeZone = normalizeTimeZone(user?.time_zone);
  const [notifications, setNotifications] = useState<WorkspaceNotification[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token || !workspaceSlug) {
      setNotifications([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    listNotifications(token, 1, workspaceSlug)
      .then(res => setNotifications(res.items))
      .finally(() => setLoading(false));
  }, [token, workspaceSlug]);

  const handleRead = useCallback(async (n: WorkspaceNotification) => {
    if (!token || !workspaceSlug || n.is_read) return;
    await markNotificationRead(token, n.id, workspaceSlug);
    setNotifications(prev => prev.map(item => item.id === n.id ? { ...item, is_read: true } : item));
    onCountChange?.(-1);
  }, [token, onCountChange, workspaceSlug]);

  const handleClick = useCallback((n: WorkspaceNotification) => {
    void handleRead(n);
    if (n.reference_id && onNavigateToIssue) {
      onNavigateToIssue(n.reference_id);
      onClose();
    }
  }, [handleRead, onNavigateToIssue, onClose]);

  const handleReadAll = useCallback(async () => {
    if (!token || !workspaceSlug) return;
    await markAllNotificationsRead(token, workspaceSlug);
    const unreadCount = notifications.filter(n => !n.is_read).length;
    setNotifications(prev => prev.map(n => ({ ...n, is_read: true })));
    onCountChange?.(-unreadCount);
  }, [token, notifications, onCountChange, workspaceSlug]);

  return (
    <>
      <div className="fixed inset-0 z-40" onClick={onClose} />
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -8 }}
        className="fixed left-3 right-3 top-16 z-50 flex max-h-[min(480px,calc(100vh-5rem))] flex-col overflow-hidden rounded-xl border border-app-border bg-app-bg shadow-2xl lg:bottom-16 lg:left-20 lg:right-auto lg:top-auto lg:w-80"
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-app-border shrink-0">
          <h3 className="app-text-title-md text-app-ink">{t('notifications.title')}</h3>
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="icon" onClick={handleReadAll} title={t('notifications.markAllAsRead')}>
              <CheckCheck size={14} />
            </Button>
            <Button variant="ghost" size="icon" onClick={onClose}>
              <X size={14} />
            </Button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto custom-scrollbar">
          {loading ? (
            <div className="flex justify-center py-8">
              <Loader2 size={18} className="animate-spin text-app-ink/40" />
            </div>
          ) : notifications.length === 0 ? (
            <p className="app-text-body text-center text-app-ink/30 py-8">{t('notifications.empty')}</p>
          ) : (
            notifications.map(n => (
              <div
                key={n.id}
                className={`w-full text-left px-4 py-3 border-b border-app-border hover:bg-app-surface-hover transition-colors ${
                  n.is_read ? 'opacity-60' : ''
                }`}
              >
                <div className="flex items-start gap-2">
                  <button
                    onClick={() => handleClick(n)}
                    className="flex min-w-0 flex-1 items-start gap-2 text-left"
                    type="button"
                  >
                    {!n.is_read && <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-app-accent" />}
                    <div className="flex-1 min-w-0">
                      <p className="app-text-body truncate font-medium text-app-ink">{n.title}</p>
                      <p className="app-text-caption mt-0.5 truncate text-app-ink/50">{n.body}</p>
                      <span className="app-text-micro text-app-ink/30">{timeAgo(n.created_at, timeZone, i18n.language)}</span>
                    </div>
                  </button>
                  {!n.is_read && (
                    <button
                      onClick={() => void handleRead(n)}
                      className="mt-1 shrink-0 text-app-ink/30 hover:text-app-accent"
                      title={t('notifications.markAsRead')}
                      type="button"
                    >
                      <Check size={12} />
                    </button>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </motion.div>
    </>
  );
}
