import { useCallback, useEffect, useMemo, useReducer } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Plus, Loader2, Users, Video, FileText } from 'lucide-react';
import { Button } from '@open-work-hub/ui';
import { buildAppHref } from '@open-work-hub/contracts/app-routes';

import { useAuth } from '@/src/platform/auth/auth-provider';
import { normalizeTimeZone } from '@/src/platform/time/time-utils';
import { listMeetings } from '../../api/meeting-api';

import { MeetingList } from './MeetingList';
import { MeetingCreateModal } from './MeetingCreateModal';
import {
  INITIAL_MEETING_LIST_VIEW_STATE,
  MEETING_CREATE_EVENT,
  MEETING_TABS,
  consumeMeetingCreateSearchParam,
  createMeetingTabSearchParams,
  meetingListViewReducer,
  resolveMeetingScope,
  resolveMeetingTab,
  type MeetingTab,
} from './meeting-list-view-model';

export function MeetingView() {
  const { t } = useTranslation('apps');
  const { token, user } = useAuth();
  const timeZone = normalizeTimeZone(user?.time_zone);
  const navigate = useNavigate();
  const { workspaceSlug } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const [state, dispatch] = useReducer(
    meetingListViewReducer,
    INITIAL_MEETING_LIST_VIEW_STATE,
  );
  const activeTab = resolveMeetingTab(searchParams.get('tab'));

  const scope = useMemo(() => resolveMeetingScope(activeTab), [activeTab]);

  useEffect(() => {
    if (!token || !workspaceSlug) return;
    let cancelled = false;
    dispatch({ type: 'load-started' });
    listMeetings(token, workspaceSlug, { scope })
      .then((response) => {
        if (cancelled) return;
        dispatch({ type: 'load-succeeded', items: response.items });
      })
      .catch((err: Error) => {
        if (cancelled) return;
        dispatch({
          type: 'load-failed',
          error: err.message ?? t('meeting.listLoadFailed'),
        });
      });
    return () => {
      cancelled = true;
    };
  }, [scope, t, token, workspaceSlug]);

  // Listen for the SubSidebar "+" dropdown event so the New Meeting entry
  // there opens this view's create modal directly, mirroring the planner
  // create-event pattern.
  useEffect(() => {
    function handle() {
      dispatch({ type: 'create-opened' });
    }
    window.addEventListener(MEETING_CREATE_EVENT, handle);
    return () => window.removeEventListener(MEETING_CREATE_EVENT, handle);
  }, []);

  useEffect(() => {
    const next = consumeMeetingCreateSearchParam(searchParams);
    if (!next) return;
    dispatch({ type: 'create-opened' });
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  const handleSelect = useCallback(
    (id: string) => {
      if (!workspaceSlug) return;
      navigate(
        buildAppHref({
          routeId: 'meeting.detail',
          workspaceSlug,
          pathParams: { meetingId: id },
        }),
      );
    },
    [navigate, workspaceSlug],
  );

  const handleTabChange = useCallback(
    (tab: MeetingTab) => {
      setSearchParams(createMeetingTabSearchParams({ searchParams, tab }), {
        replace: true,
      });
    },
    [searchParams, setSearchParams],
  );

  const handleCreated = useCallback(
    (id: string) => {
      if (!workspaceSlug) return;
      dispatch({ type: 'create-closed' });
      navigate(
        buildAppHref({
          routeId: 'meeting.detail',
          workspaceSlug,
          pathParams: { meetingId: id },
        }),
      );
    },
    [navigate, workspaceSlug],
  );

  if (!workspaceSlug) {
    return null;
  }

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-app-border bg-app-surface px-6 py-4">
        <div className="flex items-center gap-3">
          <Users size={20} className="text-app-ink/60 dark:text-app-ink/70" />
          <h1 className="app-text-title-md text-app-ink">
            {t('meeting.meetings')}
          </h1>
        </div>
        <Button
          variant="primary"
          onClick={() => dispatch({ type: 'create-opened' })}
          className="dark:border-app-border dark:bg-app-surface-raised dark:text-app-ink dark:hover:bg-app-surface-hover"
        >
          <Plus size={14} className="mr-1" />
          {t('meeting.new')}
        </Button>
      </header>

      <nav className="flex items-center gap-1 border-b border-app-border bg-app-surface px-6">
        {MEETING_TABS.map((tab) => {
          const isActive = tab.id === activeTab;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => handleTabChange(tab.id)}
              className={`app-text-control-sm border-b-2 px-3 py-3 transition-colors ${
                isActive
                  ? 'border-app-accent text-app-ink'
                  : 'border-transparent text-app-ink/60 hover:text-app-ink dark:text-app-ink/70 dark:hover:text-app-ink'
              }`}
            >
              <span className="inline-flex items-center gap-1.5">
                {tab.id === 'recordings' ? <Video size={13} /> : null}
                {tab.id === 'upcoming' ? <FileText size={13} /> : null}
                {t(tab.labelKey)}
              </span>
            </button>
          );
        })}
      </nav>

      <div className="flex-1 overflow-y-auto bg-app-bg">
        {activeTab === 'recordings' ? (
          <RecordingsPlaceholder />
        ) : state.loading && state.items === null ? (
          <div className="flex h-32 items-center justify-center text-app-ink/50">
            <Loader2 size={18} className="animate-spin" />
          </div>
        ) : state.error ? (
          <div className="m-6 rounded-md border border-app-border bg-app-surface p-4 text-app-ink/70">
            {state.error}
          </div>
        ) : state.items && state.items.length === 0 ? (
          <EmptyState onCreate={() => dispatch({ type: 'create-opened' })} />
        ) : (
          <MeetingList
            items={state.items ?? []}
            activeId={null}
            timeZone={timeZone}
            onSelect={handleSelect}
          />
        )}
      </div>

      <MeetingCreateModal
        isOpen={state.createOpen}
        onClose={() => dispatch({ type: 'create-closed' })}
        onCreated={handleCreated}
        workspaceSlug={workspaceSlug}
      />
    </div>
  );
}

function EmptyState({ onCreate }: { onCreate: () => void }) {
  const { t } = useTranslation('apps');
  return (
    <div className="flex h-64 flex-col items-center justify-center gap-3 text-app-ink/60">
      <Users size={28} className="text-app-ink/30" />
      <p className="app-text-body">{t('meeting.empty')}</p>
      <Button variant="secondary" onClick={onCreate}>
        <Plus size={14} className="mr-1" />
        {t('meeting.new')}
      </Button>
    </div>
  );
}

function RecordingsPlaceholder() {
  const { t } = useTranslation('apps');
  return (
    <div className="flex h-64 flex-col items-center justify-center gap-2 text-app-ink/60">
      <Video size={28} className="text-app-ink/30" />
      <p className="app-text-body">{t('meeting.recordingsPlaceholder')}</p>
      <p className="app-text-caption text-app-ink/40">
        {t('meeting.recordingsDescription')}
      </p>
    </div>
  );
}

export default MeetingView;
