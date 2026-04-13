import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Plus, Loader2, Users, Video, FileText } from 'lucide-react';
import { Button } from '@aidoo/ui';

import { useAuth } from '@/src/domains/auth/auth-provider';
import {
  listMeetings,
  type MeetingListItem,
  type MeetingScope,
} from '@/src/domains/meeting/meeting-api';

import { MeetingList } from './MeetingList';
import { MeetingDetail } from './MeetingDetail';
import { MeetingCreateModal } from './MeetingCreateModal';

type MeetingTab = 'upcoming' | 'mine' | 'recordings';

const TABS: { id: MeetingTab; label: string; scope: MeetingScope }[] = [
  { id: 'upcoming', label: '예정', scope: 'upcoming' },
  { id: 'mine', label: '내 회의', scope: 'mine' },
  { id: 'recordings', label: '녹음', scope: 'mine' },
];

export function MeetingView() {
  const { token } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const initialTab = (searchParams.get('tab') as MeetingTab | null) ?? 'upcoming';
  const [activeTab, setActiveTab] = useState<MeetingTab>(initialTab);

  const [items, setItems] = useState<MeetingListItem[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(
    searchParams.get('id'),
  );
  const [createOpen, setCreateOpen] = useState(false);
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    setActiveTab((searchParams.get('tab') as MeetingTab | null) ?? 'upcoming');
    setSelectedId(searchParams.get('id'));
  }, [searchParams]);

  const scope = useMemo<MeetingScope>(() => {
    return TABS.find((tab) => tab.id === activeTab)?.scope ?? 'upcoming';
  }, [activeTab]);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    listMeetings(token, { scope })
      .then((response) => {
        if (cancelled) return;
        setItems(response.items);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setError(err.message ?? '회의 목록을 불러올 수 없습니다.');
        setItems([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token, scope, refreshToken]);

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

  const handleSelect = useCallback(
    (id: string) => {
      setSelectedId(id);
      const next = new URLSearchParams(searchParams);
      next.set('id', id);
      setSearchParams(next, { replace: true });
    },
    [searchParams, setSearchParams],
  );

  const handleCloseDetail = useCallback(() => {
    setSelectedId(null);
    const next = new URLSearchParams(searchParams);
    next.delete('id');
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  const handleTabChange = useCallback(
    (tab: MeetingTab) => {
      setActiveTab(tab);
      const next = new URLSearchParams(searchParams);
      next.set('tab', tab);
      setSearchParams(next, { replace: true });
    },
    [searchParams, setSearchParams],
  );

  const handleCreated = useCallback((id: string) => {
    setCreateOpen(false);
    setRefreshToken((value) => value + 1);
    setSelectedId(id);
    const next = new URLSearchParams(searchParams);
    next.set('id', id);
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  const handleAfterMutation = useCallback(() => {
    setRefreshToken((value) => value + 1);
  }, []);

  return (
    <div className="flex h-full">
      <div className="flex flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-app-border bg-app-surface px-6 py-4">
          <div className="flex items-center gap-3">
            <Users size={20} className="text-app-ink/60 dark:text-app-ink/70" />
            <h1 className="app-text-title-md text-app-ink">Meetings</h1>
          </div>
          <Button variant="primary" onClick={() => setCreateOpen(true)}>
            <Plus size={14} className="mr-1" />
            New Meeting
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
                  {tab.label}
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
              activeId={selectedId}
              onSelect={handleSelect}
            />
          )}
        </div>
      </div>

      {selectedId ? (
        <aside className="w-[420px] shrink-0 border-l border-app-border bg-app-surface">
          <MeetingDetail
            meetingId={selectedId}
            onClose={handleCloseDetail}
            onChanged={handleAfterMutation}
            onDeleted={() => {
              handleCloseDetail();
              handleAfterMutation();
            }}
          />
        </aside>
      ) : null}

      <MeetingCreateModal
        isOpen={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={handleCreated}
      />
    </div>
  );
}

function EmptyState({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="flex h-64 flex-col items-center justify-center gap-3 text-app-ink/60">
      <Users size={28} className="text-app-ink/30" />
      <p className="app-text-body">예정된 회의가 없습니다.</p>
      <Button variant="secondary" onClick={onCreate}>
        <Plus size={14} className="mr-1" />
        New Meeting
      </Button>
    </div>
  );
}

function RecordingsPlaceholder() {
  return (
    <div className="flex h-64 flex-col items-center justify-center gap-2 text-app-ink/60">
      <Video size={28} className="text-app-ink/30" />
      <p className="app-text-body">회의 녹음은 회의 상세 패널에서 사용할 수 있습니다.</p>
      <p className="app-text-caption text-app-ink/40">
        회의를 선택하면 오른쪽 패널에서 녹음 시작과 음성 파일 업로드를 사용할 수 있습니다.
      </p>
    </div>
  );
}

export default MeetingView;
