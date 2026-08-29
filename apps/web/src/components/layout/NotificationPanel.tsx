import {
  useEffect,
  useCallback,
  useId,
  useReducer,
  useRef,
  type KeyboardEvent,
} from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { LazyMotion, domAnimation, m } from 'motion/react';
import { X, Check, CheckCheck, Loader2 } from 'lucide-react';
import { Button } from '@open-work-hub/ui/primitives/button';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { FLOATING_DM_OPEN_EVENT } from '@/src/platform/personal-widgets/floating-panel-events';
import {
  formatRelativeTime,
  normalizeTimeZone,
} from '@/src/platform/time/time-utils';
import {
  listNotifications,
  markNotificationRead,
  markAllNotificationsRead,
  type WorkspaceNotification,
} from '@/src/platform/notifications/notifications-api';
import {
  INITIAL_NOTIFICATION_PANEL_STATE,
  countUnreadNotifications,
  notificationPanelReducer,
  resolveNotificationAction,
} from './notification-panel-model';
import { NOTIFICATION_PANEL_ID } from './useNotificationPanelFocus';

const PANEL_FOCUSABLE_SELECTOR = [
  'button:not([disabled])',
  'a[href]',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

function timeAgo(dateStr: string, timeZone: string, locale: string): string {
  return formatRelativeTime(dateStr, { locale, timeZone });
}

export function NotificationPanel({
  onClose,
  onNavigateToIssue,
  onCountChange,
  refreshKey = 0,
  workspaceSlug,
}: {
  onClose: () => void;
  onNavigateToIssue?: (taskId: string) => void;
  onCountChange?: (count: number) => void;
  refreshKey?: number;
  workspaceSlug: string | null;
}) {
  const { token, user } = useAuth();
  const { t, i18n } = useTranslation('shell');
  const navigate = useNavigate();
  const titleId = useId();
  const panelRef = useRef<HTMLDivElement | null>(null);
  const timeZone = normalizeTimeZone(user?.time_zone);
  const [{ loading, notifications }, dispatch] = useReducer(
    notificationPanelReducer,
    INITIAL_NOTIFICATION_PANEL_STATE,
  );

  useEffect(() => {
    if (!token) {
      dispatch({ type: 'signed-out' });
      return;
    }
    dispatch({ type: 'loading' });
    listNotifications(token, 1, workspaceSlug).then((response) =>
      dispatch({
        type: 'loaded',
        notifications: response.items,
      }),
    );
  }, [refreshKey, token, workspaceSlug]);

  const handleRead = useCallback(
    async (n: WorkspaceNotification) => {
      if (!token || n.is_read) return;
      await markNotificationRead(token, n.id, workspaceSlug);
      dispatch({
        type: 'mark-read',
        notificationId: n.id,
      });
      onCountChange?.(-1);
    },
    [token, onCountChange, workspaceSlug],
  );

  const handleClick = useCallback(
    (n: WorkspaceNotification) => {
      void handleRead(n);
      const action = resolveNotificationAction(n);
      if (action.kind === 'dm') {
        window.dispatchEvent(
          new CustomEvent(FLOATING_DM_OPEN_EVENT, {
            detail: { threadId: action.threadId },
          }),
        );
        onClose();
      } else if (action.kind === 'route') {
        navigate(action.to);
        onClose();
      } else if (action.kind === 'issue' && onNavigateToIssue) {
        onNavigateToIssue(action.taskId);
        onClose();
      }
    },
    [handleRead, navigate, onClose, onNavigateToIssue],
  );

  const handleReadAll = useCallback(async () => {
    if (!token) return;
    await markAllNotificationsRead(token, workspaceSlug);
    const unreadCount = countUnreadNotifications(notifications);
    dispatch({ type: 'mark-all-read' });
    onCountChange?.(-unreadCount);
  }, [token, notifications, onCountChange, workspaceSlug]);

  const handlePanelKeyDown = useCallback(
    (event: KeyboardEvent<HTMLDivElement>) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== 'Tab' || !panelRef.current) return;

      const focusable = Array.from(
        panelRef.current.querySelectorAll<HTMLElement>(
          PANEL_FOCUSABLE_SELECTOR,
        ),
      );
      if (focusable.length === 0) {
        event.preventDefault();
        panelRef.current.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (
        event.shiftKey &&
        (document.activeElement === first ||
          document.activeElement === panelRef.current)
      ) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    },
    [onClose],
  );

  return (
    <LazyMotion features={domAnimation}>
      <button
        type="button"
        aria-label={t('notifications.closePanel', {
          defaultValue: t('notifications.title'),
        })}
        className="fixed inset-0 z-40 cursor-default"
        onClick={onClose}
        tabIndex={-1}
      />
      <m.div
        ref={panelRef}
        id={NOTIFICATION_PANEL_ID}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onKeyDown={handlePanelKeyDown}
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -8 }}
        className="fixed left-3 right-3 top-16 z-50 flex max-h-[min(480px,calc(100vh-5rem))] flex-col overflow-hidden rounded-xl border border-app-border bg-app-bg shadow-2xl lg:bottom-16 lg:left-20 lg:right-auto lg:top-auto lg:w-80"
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-app-border shrink-0">
          <h3 id={titleId} className="app-text-title-md text-app-ink">
            {t('notifications.title')}
          </h3>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              onClick={handleReadAll}
              aria-label={t('notifications.markAllAsRead')}
              title={t('notifications.markAllAsRead')}
            >
              <CheckCheck size={14} />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={onClose}
              aria-label={t('notifications.closePanel')}
            >
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
            <p className="app-text-body text-center text-app-ink/30 py-8">
              {t('notifications.empty')}
            </p>
          ) : (
            notifications.map((n) => (
              <div
                key={n.id}
                className="w-full border-b border-app-border px-4 py-3 text-left transition-colors hover:bg-app-surface-hover"
              >
                <div className="flex items-start gap-2">
                  <button
                    onClick={() => handleClick(n)}
                    className="flex min-w-0 flex-1 items-start gap-2 text-left"
                    type="button"
                  >
                    {!n.is_read && (
                      <span className="mt-1.5 size-2 shrink-0 rounded-full bg-app-accent" />
                    )}
                    <div className="flex-1 min-w-0">
                      <p
                        className={`app-text-body truncate font-medium ${
                          n.is_read ? 'text-app-ink/85' : 'text-app-ink'
                        }`}
                      >
                        {n.title}
                      </p>
                      <p className="app-text-caption mt-0.5 truncate text-app-ink/75">
                        {n.body}
                      </p>
                      <span className="app-text-micro text-app-ink/70">
                        {timeAgo(n.created_at, timeZone, i18n.language)}
                      </span>
                    </div>
                  </button>
                  {!n.is_read && (
                    <button
                      onClick={() => void handleRead(n)}
                      className="mt-1 shrink-0 text-app-ink/70 hover:text-app-accent"
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
      </m.div>
    </LazyMotion>
  );
}
