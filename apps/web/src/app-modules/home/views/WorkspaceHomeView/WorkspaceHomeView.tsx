import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  Calendar,
  ChevronRight,
  Circle,
  FileText,
  Flag,
  ListTodo,
  Loader2,
  Plus,
  Video,
} from 'lucide-react';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  listAssignedIssues,
  type PmsIssue,
} from '@/src/app-modules/pms/public-api';
import {
  listRecentPages,
  type RecentPageItem,
} from '@/src/app-modules/docs/public-api';
import {
  listMeetings,
  type MeetingListItem,
} from '@/src/app-modules/meeting/public-api';
import { buildWorkspaceAppPath } from '@/src/platform/workspaces/workspace-utils';
import { getKoreanHolidayNames } from '@/src/lib/korean-holidays';

function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}

function formatWeekday(date: Date): string {
  return new Intl.DateTimeFormat('ko-KR', {
    month: 'long',
    day: 'numeric',
    weekday: 'long',
  }).format(date);
}

function formatTime(iso: string): string {
  return new Intl.DateTimeFormat('ko-KR', {
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(iso));
}

function formatDueDate(due: string | null): string {
  if (!due) return '';
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const target = new Date(`${due}T00:00:00`);
  const diffDays = Math.round((target.getTime() - today.getTime()) / 86_400_000);
  if (diffDays === 0) return '오늘';
  if (diffDays === 1) return '내일';
  if (diffDays === -1) return '어제';
  if (diffDays < 0) return `${-diffDays}일 지연`;
  if (diffDays < 7) return `${diffDays}일 후`;
  return new Intl.DateTimeFormat('ko-KR', {
    month: 'short',
    day: 'numeric',
  }).format(target);
}

const PRIORITY_COLOR: Record<string, string> = {
  critical: 'text-red-500',
  high: 'text-red-500',
  medium: 'text-orange-400',
  low: 'text-gray-400',
};

function SectionHeader({
  title,
  actionLabel,
  actionTo,
}: {
  title: string;
  actionLabel?: string;
  actionTo?: string;
}) {
  return (
    <div className="mb-2 flex items-center justify-between">
      <h2 className="app-text-title-md text-app-ink">{title}</h2>
      {actionLabel && actionTo ? (
        <Link
          to={actionTo}
          className="app-text-caption text-gray-500 transition-colors hover:text-app-ink"
        >
          {actionLabel}
        </Link>
      ) : null}
    </div>
  );
}

function GreetingHeader({ userName }: { userName: string }) {
  const now = new Date();
  const holidayNames = getKoreanHolidayNames(
    now.getFullYear(),
    now.getMonth(),
    now.getDate(),
  );

  return (
    <div>
      <h1 className="app-text-title-lg text-app-ink">
        {getGreeting()}, {userName}
      </h1>
      <p className="app-text-body mt-1 text-gray-500">
        {formatWeekday(now)}
        {holidayNames && holidayNames.length > 0 ? (
          <span className="ml-2 rounded bg-red-500/10 px-1.5 py-0.5 text-red-500">
            {holidayNames.join(', ')}
          </span>
        ) : null}
      </p>
    </div>
  );
}

function QuickActionsRow({ workspaceSlug }: { workspaceSlug: string }) {
  const actions = [
    {
      label: '새 회의',
      to: buildWorkspaceAppPath(workspaceSlug, 'meeting', '?create=1'),
      icon: Video,
    },
    {
      label: '새 태스크',
      to: buildWorkspaceAppPath(workspaceSlug, 'pms', '?create=1'),
      icon: ListTodo,
    },
    {
      label: '새 Doc',
      to: buildWorkspaceAppPath(workspaceSlug, 'docs', '?create=1'),
      icon: FileText,
    },
  ];
  return (
    <div className="flex flex-wrap gap-2">
      {actions.map((action) => (
        <Link
          key={action.label}
          to={action.to}
          className="app-text-body-sm flex items-center gap-2 rounded-md border border-app-border bg-app-surface px-3 py-2 text-app-ink transition-colors hover:border-app-accent/40 hover:bg-app-surface-hover"
        >
          <Plus size={14} className="text-gray-500" />
          <action.icon size={14} className="text-gray-500" />
          <span>{action.label}</span>
        </Link>
      ))}
    </div>
  );
}

function isToday(iso: string): boolean {
  const target = new Date(iso);
  const now = new Date();
  return (
    target.getFullYear() === now.getFullYear()
    && target.getMonth() === now.getMonth()
    && target.getDate() === now.getDate()
  );
}

function TodayMeetingsWidget({
  workspaceSlug,
  meetings,
  loading,
}: {
  workspaceSlug: string;
  meetings: MeetingListItem[];
  loading: boolean;
}) {
  const todayMeetings = useMemo(
    () => meetings.filter((meeting) => isToday(meeting.start_at)).slice(0, 5),
    [meetings],
  );
  const meetingRoot = `/w/${encodeURIComponent(workspaceSlug)}/meeting`;

  return (
    <section>
      <SectionHeader title="오늘의 회의" actionLabel="See all" actionTo={meetingRoot} />
      <div className="border-t border-app-border">
        {loading ? (
          <div className="flex justify-center py-6">
            <Loader2 size={16} className="animate-spin text-gray-400" />
          </div>
        ) : todayMeetings.length === 0 ? (
          <p className="app-text-body py-6 text-center text-gray-500">오늘 예정된 회의가 없습니다.</p>
        ) : (
          todayMeetings.map((meeting) => (
            <Link
              key={meeting.id}
              to={`${meetingRoot}/${meeting.id}`}
              className="group -mx-2 flex items-center gap-3 border-b border-app-border px-2 py-3 transition-colors last:border-b-0 hover:bg-app-surface-hover/50"
            >
              <Calendar size={16} className="shrink-0 text-gray-400 transition-colors group-hover:text-app-accent" />
              <span className="app-text-body flex-1 truncate text-app-ink">{meeting.title}</span>
              <span className="app-text-caption shrink-0 text-gray-500">
                {formatTime(meeting.start_at)}
              </span>
              <ChevronRight size={14} className="shrink-0 text-gray-400 opacity-0 transition-opacity group-hover:opacity-100" />
            </Link>
          ))
        )}
      </div>
    </section>
  );
}

function AssignedTasksWidget({
  workspaceSlug,
  issues,
  loading,
}: {
  workspaceSlug: string;
  issues: PmsIssue[];
  loading: boolean;
}) {
  const assignedLink = buildWorkspaceAppPath(workspaceSlug, 'pms', '/assigned');
  const topIssues = issues.slice(0, 5);

  return (
    <section>
      <SectionHeader title="내 태스크" actionLabel="See all" actionTo={assignedLink} />
      <div className="border-t border-app-border">
        {loading ? (
          <div className="flex justify-center py-6">
            <Loader2 size={16} className="animate-spin text-gray-400" />
          </div>
        ) : topIssues.length === 0 ? (
          <p className="app-text-body py-6 text-center text-gray-500">할당된 작업이 없습니다.</p>
        ) : (
          topIssues.map((issue) => (
            <Link
              key={issue.id}
              to={`${assignedLink}?issue=${encodeURIComponent(issue.id)}`}
              className="group -mx-2 flex items-center gap-3 border-b border-app-border px-2 py-3 transition-colors last:border-b-0 hover:bg-app-surface-hover/50"
            >
              <Circle size={16} className="shrink-0 text-gray-400 transition-colors group-hover:text-app-accent" />
              <span className="app-text-body flex-1 truncate text-app-ink">{issue.title}</span>
              {issue.due_date ? (
                <span className="app-text-caption shrink-0 text-gray-500">
                  {formatDueDate(issue.due_date)}
                </span>
              ) : null}
              <Flag
                size={13}
                className={`shrink-0 ${PRIORITY_COLOR[issue.priority] ?? 'text-gray-400'}`}
              />
            </Link>
          ))
        )}
      </div>
    </section>
  );
}

function RecentDocsWidget({
  workspaceSlug,
  pages,
  loading,
}: {
  workspaceSlug: string;
  pages: RecentPageItem[];
  loading: boolean;
}) {
  const docsRoot = `/w/${encodeURIComponent(workspaceSlug)}/docs`;
  const topPages = pages.slice(0, 5);

  return (
    <section>
      <SectionHeader title="최근 Docs" actionLabel="See all" actionTo={docsRoot} />
      <div className="border-t border-app-border">
        {loading ? (
          <div className="flex justify-center py-6">
            <Loader2 size={16} className="animate-spin text-gray-400" />
          </div>
        ) : topPages.length === 0 ? (
          <p className="app-text-body py-6 text-center text-gray-500">최근 열어본 페이지가 없습니다.</p>
        ) : (
          topPages.map((page) => (
            <Link
              key={page.page_id}
              to={`${docsRoot}/${page.doc_id}`}
              className="group -mx-2 flex items-center gap-3 border-b border-app-border px-2 py-3 transition-colors last:border-b-0 hover:bg-app-surface-hover/50"
            >
              <FileText size={16} className="shrink-0 text-gray-400 transition-colors group-hover:text-app-accent" />
              <div className="min-w-0 flex-1">
                <span className="app-text-body block truncate text-app-ink">
                  {page.page_title || 'Untitled'}
                </span>
                <span className="app-text-caption block truncate text-gray-500">
                  {page.doc_title}
                </span>
              </div>
              <ChevronRight size={14} className="shrink-0 text-gray-400 opacity-0 transition-opacity group-hover:opacity-100" />
            </Link>
          ))
        )}
      </div>
    </section>
  );
}

export const WorkspaceHomeView = () => {
  const { token, user } = useAuth();
  const { workspaceSlug = '' } = useParams();
  const userName = user?.display_name || user?.full_name || 'User';

  const [meetings, setMeetings] = useState<MeetingListItem[]>([]);
  const [meetingsLoading, setMeetingsLoading] = useState(true);
  const [issues, setIssues] = useState<PmsIssue[]>([]);
  const [issuesLoading, setIssuesLoading] = useState(true);
  const [recentPages, setRecentPages] = useState<RecentPageItem[]>([]);
  const [pagesLoading, setPagesLoading] = useState(true);

  useEffect(() => {
    if (!token || !workspaceSlug) return;
    let cancelled = false;

    setMeetingsLoading(true);
    listMeetings(token, workspaceSlug, { scope: 'upcoming' })
      .then((response) => {
        if (!cancelled) setMeetings(response.items);
      })
      .catch(() => {
        if (!cancelled) setMeetings([]);
      })
      .finally(() => {
        if (!cancelled) setMeetingsLoading(false);
      });

    setIssuesLoading(true);
    listAssignedIssues(token, { limit: 10, workspaceSlug })
      .then((response) => {
        if (!cancelled) setIssues(response.items);
      })
      .catch(() => {
        if (!cancelled) setIssues([]);
      })
      .finally(() => {
        if (!cancelled) setIssuesLoading(false);
      });

    setPagesLoading(true);
    listRecentPages(token, 10, workspaceSlug)
      .then((response) => {
        if (!cancelled) setRecentPages(response);
      })
      .catch(() => {
        if (!cancelled) setRecentPages([]);
      })
      .finally(() => {
        if (!cancelled) setPagesLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [token, workspaceSlug]);

  return (
    <div className="custom-scrollbar h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl space-y-10 px-8 py-10">
        <GreetingHeader userName={userName} />
        <QuickActionsRow workspaceSlug={workspaceSlug} />
        <TodayMeetingsWidget
          workspaceSlug={workspaceSlug}
          meetings={meetings}
          loading={meetingsLoading}
        />
        <AssignedTasksWidget
          workspaceSlug={workspaceSlug}
          issues={issues}
          loading={issuesLoading}
        />
        <RecentDocsWidget
          workspaceSlug={workspaceSlug}
          pages={recentPages}
          loading={pagesLoading}
        />
      </div>
    </div>
  );
};
