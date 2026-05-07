import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Plus, Loader2, Users, Video, FileText } from 'lucide-react';
import { Button } from '@ai-do/ui';

import { useAuth } from '@/src/platform/auth/auth-provider';
import { normalizeTimeZone } from '@/src/platform/time/time-utils';
import {
  listMeetings,
  type MeetingListItem,
  type MeetingScope,
} from '../../api/meeting-api';
import { buildWorkspaceAppPath } from '@/src/platform/workspaces/workspace-utils';

import { MeetingList } from './MeetingList';
import { MeetingCreateModal } from './MeetingCreateModal';

type MeetingTab = 'upcoming' | 'mine' | 'recordings';

const TABS: { id: MeetingTab; labelKey: string; scope: MeetingScope }[] = [
  { id: 'upcoming', labelKey: 'meeting.scheduled', scope: 'upcoming' },
  { id: 'mine', labelKey: 'meeting.mine', scope: 'mine' },
  { id: 'recordings', labelKey: 'meeting.recordings', scope: 'mine' },
];

export function MeetingView() {
  const { t } = useTranslation('apps');
  const { token, user } = useAuth();
  const timeZone = normalizeTimeZone(user?.time_zone);
  const navigate = useNavigate();
  const { workspaceSlug } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();

  const initialTab = (searchParams.get('tab') as MeetingTab | null) ?? 'upcoming';
  const [activeTab, setActiveTab] = useState<MeetingTab>(initialTab);

  const [items, setItems] = useState<MeetingListItem[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    setActiveTab((searchParams.get('tab') as MeetingTab | null) ?? 'upcoming');
  }, [searchParams]);

  useEffect(() => {
    if (!workspaceSlug) return;
    const legacyId = searchParams.get('id');
    if (!legacyId) return;
    navigate(
      buildWorkspaceAppPath(workspaceSlug, 'meeting', `/${legacyId}`),
      { replace: true },
    );
  }, [navigate, searchParams, workspaceSlug]);

  const scope = useMemo<MeetingScope>(() => {
    return TABS.find((tab) => tab.id === activeTab)?.scope ?? 'upcoming';
  }, [activeTab]);

  useEffect(() => {
    if (!token || !workspaceSlug) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    listMeetings(token, workspaceSlug, { scope })
      .then((response) => {
        if (cancelled) return;
        setItems(response.items);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setError(err.message ?? t('meeting.listLoadFailed'));
        setItems([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshToken, scope, t, token, workspaceSlug]);

  // Listen for the SubSidebar "+" dropdown event so the New Meeting entry
  // there opens this view's create modal directly, mirroring the planner
  // create-event pattern.
  useEffect(() => {
    function handle() {
      setCreateOpen(true);
    }
    window.addEventListener('meeting:create-event', handle);
    return () => window.removeEventListener('meeting:create-event', handle);
  }, []);

  useEffect(() => {
    if (searchParams.get('create') !== '1') return;
    setCreateOpen(true);
    const next = new URLSearchParams(searchParams);
    next.delete('create');
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  const handleSelect = useCallback(
    (id: string) => {
      if (!workspaceSlug) return;
      navigate(buildWorkspaceAppPath(workspaceSlug, 'meeting', `/${id}`));
    },
    [navigate, workspaceSlug],
  );

  const handleTabChange = useCallback(
    (tab: MeetingTab) => {
      setActiveTab(tab);
      const next = new URLSearchParams(searchParams);
      next.set('tab', tab);
      next.delete('id');
      setSearchParams(next, { replace: true });
    },
    [searchParams, setSearchParams],
  );

  const handleCreated = useCallback((id: string) => {
    if (!workspaceSlug) return;
    setCreateOpen(false);
    setRefreshToken((value) => value + 1);
    navigate(buildWorkspaceAppPath(workspaceSlug, 'meeting', `/${id}`));
  }, [navigate, workspaceSlug]);

  if (!workspaceSlug) {
    return null;
  }

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-app-border bg-app-surface px-6 py-4">
        <div className="flex items-center gap-3">
          <Users size={20} className="text-app-ink/60 dark:text-app-ink/70" />
          <h1 className="app-text-title-md text-app-ink">{t('meeting.meetings')}</h1>
        </div>
        <Button
          variant="primary"
          onClick={() => setCreateOpen(true)}
          className="dark:border-app-border dark:bg-app-surface-raised dark:text-app-ink dark:hover:bg-app-surface-hover"
        >
          <Plus size={14} className="mr-1" />
          {t('meeting.new')}
        </Button>
      </header>

      <nav className="flex items-center gap-1 border-b border-app-border bg-app-surface px-6">
        {TABS.map((tab) => {
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
        ) : loading && items === null ? (
          <div className="flex h-32 items-center justify-center text-app-ink/50">
            <Loader2 size={18} className="animate-spin" />
          </div>
        ) : error ? (
          <div className="m-6 rounded-md border border-app-border bg-app-surface p-4 text-app-ink/70">
            {error}
          </div>
        ) : items && items.length === 0 ? (
          <EmptyState onCreate={() => setCreateOpen(true)} />
        ) : (
          <MeetingList
	            items={items ?? []}
	            activeId={null}
	            timeZone={timeZone}
	            onSelect={handleSelect}
	          />
        )}
      </div>

      <MeetingCreateModal
        isOpen={createOpen}
        onClose={() => setCreateOpen(false)}
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
