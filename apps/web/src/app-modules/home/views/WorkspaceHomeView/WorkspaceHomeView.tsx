import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  AlertTriangle,
  BarChart3,
  Bell,
  Calendar,
  CalendarDays,
  ChevronDown,
  ChevronRight,
  ClipboardCheck,
  Circle,
  Database,
  FileBarChart,
  FileSearch,
  FileText,
  Flag,
  FolderSearch,
  Gavel,
  HelpCircle,
  ImageIcon,
  Languages,
  ListTodo,
  Loader2,
  Mail,
  MessageSquare,
  Mic,
  Plus,
  Presentation,
  Scale,
  ScanSearch,
  Search,
  SearchCheck,
  Sparkles,
  Video,
  type LucideIcon,
} from 'lucide-react';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  APP_CONTRACT_BY_ID,
  type AppId,
} from '@open-work-hub/contracts/app-contracts';
import { buildAppHref } from '@open-work-hub/contracts/app-routes';
import { useWorkspaceBootstrapProjection } from '@/src/platform/workspaces/workspace-bootstrap-context';
import type { WorkspaceBootstrapNavItem } from '@/src/platform/workspaces/workspaces-api';
import { getKoreanHolidayNames } from '@/src/lib/korean-holidays';
import {
  getZonedDateParts,
  normalizeTimeZone,
} from '@/src/platform/time/time-utils';
import {
  buildHomeBriefing,
  buildWorkspaceHomeSections,
  formatHomeWeekday,
  getHomeGreeting,
  type WorkspaceHomeBriefing,
  type WorkspaceHomeRow,
  type WorkspaceHomeSection,
} from './workspace-home-model';
import { useWorkspaceHomeController } from './useWorkspaceHomeController';
import { AnnouncementsBoard } from './AnnouncementsBoard';

const PRIORITY_TONE_COLOR: Record<string, string> = {
  danger: 'text-app-danger',
  warning: 'text-orange-400',
  muted: 'text-app-ink/45',
};

// Shared so the quick-action chips and the AI tools trigger render at an
// identical size. A fixed height pins the <button> and <a> to the same box
// regardless of element default line-height differences.
const ACTION_CHIP_CLASS =
  'app-text-body-sm flex h-9 items-center gap-2 rounded-md border border-app-border bg-app-surface px-3 text-app-ink transition-colors hover:border-app-accent/40 hover:bg-app-surface-hover';

const AI_TOOL_ICON_BY_KEY: Record<string, LucideIcon> = {
  'alert-triangle': AlertTriangle,
  'bar-chart-3': BarChart3,
  'clipboard-check': ClipboardCheck,
  database: Database,
  'file-bar-chart': FileBarChart,
  'file-search': FileSearch,
  'file-text': FileText,
  'folder-search': FolderSearch,
  gavel: Gavel,
  'help-circle': HelpCircle,
  image: ImageIcon,
  languages: Languages,
  mail: Mail,
  'message-square': MessageSquare,
  mic: Mic,
  presentation: Presentation,
  scale: Scale,
  'scan-search': ScanSearch,
  search: Search,
  'search-check': SearchCheck,
  sparkles: Sparkles,
};

function resolveAiToolHref(
  item: WorkspaceBootstrapNavItem,
  workspaceSlug: string,
): string {
  if (item.absolute_path) {
    return item.absolute_path;
  }
  const contract = APP_CONTRACT_BY_ID.get(
    (item.link_app_id ?? item.app_id) as AppId,
  );
  if (!contract) return '/';
  return buildAppHref({
    routeId: contract.entry_route_id,
    ...(contract.availability_scope === 'workspace' ? { workspaceSlug } : {}),
  });
}

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
          className="app-text-caption text-app-ink/55 transition-colors hover:text-app-ink"
        >
          {actionLabel}
        </Link>
      ) : null}
    </div>
  );
}

function WorkspaceHomeHeader({
  timeZone,
  userName,
  workspaceName,
}: {
  timeZone: string;
  userName: string;
  workspaceName: string;
}) {
  const { t, i18n } = useTranslation('apps');
  const now = new Date();
  const today = getZonedDateParts(now, timeZone);
  const holidayNames = getKoreanHolidayNames(
    today?.year ?? now.getFullYear(),
    today ? today.month - 1 : now.getMonth(),
    today?.day ?? now.getDate(),
  );

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="app-text-overline text-app-ink/55">
          {t('home.workspaceLabel')}
        </span>
      </div>
      <h1 className="app-text-title-lg text-app-ink">{workspaceName}</h1>
      <p className="app-text-body mt-1 text-app-ink/55">
        {getHomeGreeting(timeZone, t)}, {userName}
        <span className="mx-2 text-gray-300 dark:text-app-ink/40">/</span>
        {formatHomeWeekday(now, timeZone, i18n.language)}
        {holidayNames && holidayNames.length > 0 ? (
          <span className="ml-2 rounded bg-app-danger/10 px-1.5 py-0.5 text-app-danger">
            {holidayNames.join(', ')}
          </span>
        ) : null}
      </p>
    </div>
  );
}

function BriefingBanner({ briefing }: { briefing: WorkspaceHomeBriefing }) {
  const { t } = useTranslation('apps');
  const message =
    briefing.status === 'loading'
      ? t('home.briefingLoading')
      : briefing.status === 'empty'
        ? t('home.briefingEmpty')
        : t('home.briefingSummary', {
            meetings: briefing.meetings,
            tasks: briefing.tasks,
            events: briefing.events,
            docs: briefing.docs,
          });

  return (
    <div className="rounded-xl border border-app-border bg-gradient-to-br from-app-accent/10 to-transparent p-5">
      <div className="mb-1.5 flex items-center gap-2">
        <Sparkles size={15} className="text-app-accent" />
        <span className="app-text-overline text-app-accent">
          {t('home.briefingTitle')}
        </span>
      </div>
      {briefing.status === 'loading' ? (
        <div className="flex items-center gap-2 text-app-ink/55">
          <Loader2 size={14} className="animate-spin" />
          <span className="app-text-body">{message}</span>
        </div>
      ) : (
        <p className="app-text-body text-app-ink">{message}</p>
      )}
    </div>
  );
}

function AiToolsMenu({ workspaceSlug }: { workspaceSlug: string }) {
  const { t } = useTranslation('apps');
  const { t: tShell } = useTranslation('shell');
  const { aiToolAppIds, nav } = useWorkspaceBootstrapProjection();
  const [open, setOpen] = useState(false);

  const items = useMemo(() => {
    const registeredToolAppIds = new Set(aiToolAppIds);
    return nav
      .filter(
        (entry) => registeredToolAppIds.has(entry.app_id) && !entry.coming_soon,
      )
      .slice(0, 12);
  }, [aiToolAppIds, nav]);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className={ACTION_CHIP_CLASS}
      >
        <Sparkles size={14} className="text-app-accent" />
        <span>{t('home.aiTools')}</span>
        <ChevronDown size={14} className="text-app-ink/55" />
      </button>
      {open ? (
        <>
          <button
            type="button"
            aria-hidden
            tabIndex={-1}
            className="fixed inset-0 z-40 cursor-default"
            onClick={() => setOpen(false)}
          />
          <div className="absolute left-0 top-full z-50 mt-1 max-h-80 w-60 overflow-y-auto rounded-lg border border-app-border bg-app-surface py-1 shadow-xl">
            {items.length === 0 ? (
              <p className="app-text-caption px-3 py-2 text-app-ink/55">
                {t('home.aiToolsEmpty')}
              </p>
            ) : (
              items.map((item) => (
                <Link
                  key={item.id}
                  to={resolveAiToolHref(item, workspaceSlug)}
                  onClick={() => setOpen(false)}
                  className="app-text-control-sm flex items-center gap-2 px-3 py-2 text-app-ink hover:bg-app-surface-hover"
                >
                  {(() => {
                    const Icon = AI_TOOL_ICON_BY_KEY[item.icon_key] ?? Sparkles;
                    return (
                      <Icon size={14} className="shrink-0 text-app-ink/55" />
                    );
                  })()}
                  <span className="truncate">
                    {tShell(`nav.${item.id}`, { defaultValue: item.title })}
                  </span>
                </Link>
              ))
            )}
          </div>
        </>
      ) : null}
    </div>
  );
}

function QuickActionsRow({
  enabledAppIds,
  workspaceSlug,
}: {
  enabledAppIds: ReadonlySet<string>;
  workspaceSlug: string;
}) {
  const { t } = useTranslation('apps');
  const actions = [
    {
      appId: 'meeting',
      label: t('home.actionNewMeeting'),
      to: buildAppHref({
        routeId: 'meeting.root',
        workspaceSlug,
        queryParams: { create: '1' },
      }),
      icon: Video,
    },
    {
      appId: 'pms',
      label: t('home.actionNewTask'),
      to: buildAppHref({
        routeId: 'pms.root',
        workspaceSlug,
        queryParams: { create: '1' },
      }),
      icon: ListTodo,
    },
    {
      appId: 'docs',
      label: t('home.actionNewDoc'),
      to: buildAppHref({
        routeId: 'docs.root',
        workspaceSlug,
        queryParams: { create: '1' },
      }),
      icon: FileText,
    },
  ];
  return (
    <div className="flex flex-wrap items-center gap-2">
      {actions
        .filter((action) => enabledAppIds.has(action.appId))
        .map((action) => (
          <Link key={action.label} to={action.to} className={ACTION_CHIP_CLASS}>
            <Plus size={14} className="text-app-ink/55" />
            <action.icon size={14} className="text-app-ink/55" />
            <span>{action.label}</span>
          </Link>
        ))}
      <AiToolsMenu workspaceSlug={workspaceSlug} />
    </div>
  );
}

function WorkspaceSummaryRow({ row }: { row: WorkspaceHomeRow }) {
  if (row.kind === 'meeting') {
    return (
      <Link
        to={row.to}
        className="group -mx-2 flex items-center gap-3 border-b border-app-border px-2 py-3 transition-colors last:border-b-0 hover:bg-app-surface-hover/50"
      >
        <Calendar
          size={16}
          className="shrink-0 text-app-ink/45 transition-colors group-hover:text-app-accent"
        />
        <span className="app-text-body flex-1 truncate text-app-ink">
          {row.title}
        </span>
        <span className="app-text-caption shrink-0 text-app-ink/55">
          {row.trailing}
        </span>
        <ChevronRight
          size={14}
          className="shrink-0 text-app-ink/45 opacity-0 transition-opacity group-hover:opacity-100"
        />
      </Link>
    );
  }

  if (row.kind === 'planner') {
    return (
      <Link
        to={row.to}
        className="group -mx-2 flex items-center gap-3 border-b border-app-border px-2 py-3 transition-colors last:border-b-0 hover:bg-app-surface-hover/50"
      >
        <CalendarDays size={16} className="shrink-0 text-teal-500" />
        <span className="app-text-body flex-1 truncate text-app-ink">
          {row.title}
        </span>
        <span className="app-text-caption shrink-0 text-app-ink/55">
          {row.trailing}
        </span>
        <ChevronRight
          size={14}
          className="shrink-0 text-app-ink/45 opacity-0 transition-opacity group-hover:opacity-100"
        />
      </Link>
    );
  }

  if (row.kind === 'task') {
    return (
      <Link
        to={row.to}
        className="group -mx-2 flex items-center gap-3 border-b border-app-border px-2 py-3 transition-colors last:border-b-0 hover:bg-app-surface-hover/50"
      >
        <Circle
          size={16}
          className="shrink-0 text-app-ink/45 transition-colors group-hover:text-app-accent"
        />
        <span className="app-text-body flex-1 truncate text-app-ink">
          {row.title}
        </span>
        {row.trailing ? (
          <span className="app-text-caption shrink-0 text-app-ink/55">
            {row.trailing}
          </span>
        ) : null}
        <Flag
          size={13}
          className={`shrink-0 ${PRIORITY_TONE_COLOR[row.priorityTone]}`}
        />
      </Link>
    );
  }

  if (row.kind === 'notification') {
    const rowClass =
      'group -mx-2 flex items-center gap-3 border-b border-app-border px-2 py-3 transition-colors last:border-b-0';
    const content = (
      <>
        <Bell
          size={16}
          className={`shrink-0 ${row.isRead ? 'text-app-ink/45' : 'text-app-accent'}`}
        />
        <div className="min-w-0 flex-1">
          <span className="app-text-body block truncate text-app-ink">
            {row.title}
          </span>
          {row.subtitle ? (
            <span className="app-text-caption block truncate text-app-ink/55">
              {row.subtitle}
            </span>
          ) : null}
        </div>
        {row.trailing ? (
          <span className="app-text-micro shrink-0 text-app-ink/45">
            {row.trailing}
          </span>
        ) : null}
      </>
    );
    return row.to ? (
      <Link to={row.to} className={`${rowClass} hover:bg-app-surface-hover/50`}>
        {content}
      </Link>
    ) : (
      <div className={rowClass}>{content}</div>
    );
  }

  return (
    <Link
      to={row.to}
      className="group -mx-2 flex items-center gap-3 border-b border-app-border px-2 py-3 transition-colors last:border-b-0 hover:bg-app-surface-hover/50"
    >
      <FileText
        size={16}
        className="shrink-0 text-app-ink/45 transition-colors group-hover:text-app-accent"
      />
      <div className="min-w-0 flex-1">
        <span className="app-text-body block truncate text-app-ink">
          {row.title}
        </span>
        <span className="app-text-caption block truncate text-app-ink/55">
          {row.subtitle}
        </span>
      </div>
      <ChevronRight
        size={14}
        className="shrink-0 text-app-ink/45 opacity-0 transition-opacity group-hover:opacity-100"
      />
    </Link>
  );
}

function WorkspaceSummarySection({
  section,
}: {
  section: WorkspaceHomeSection;
}) {
  const { t } = useTranslation('apps');

  return (
    <section className="rounded-lg border border-app-border bg-app-surface p-4">
      <SectionHeader
        title={t(section.titleKey)}
        actionLabel={t(section.actionLabelKey)}
        actionTo={section.actionTo}
      />
      <div>
        {section.status === 'loading' ? (
          <div className="flex justify-center py-6">
            <Loader2 size={16} className="animate-spin text-app-ink/45" />
          </div>
        ) : section.status === 'empty' ? (
          <div className="flex flex-col items-center gap-2.5 py-6">
            <p className="app-text-body text-center text-app-ink/55">
              {t(section.emptyKey)}
            </p>
            {section.emptyCtaTo ? (
              <Link
                to={section.emptyCtaTo}
                className="app-text-caption inline-flex items-center gap-1 rounded-md border border-app-border px-2.5 py-1 text-app-ink transition-colors hover:border-app-accent/40 hover:bg-app-surface-hover"
              >
                <Plus size={12} className="text-app-ink/55" />
                {t(section.emptyCtaLabelKey)}
              </Link>
            ) : null}
          </div>
        ) : (
          section.rows.map((row) => (
            <WorkspaceSummaryRow key={`${row.kind}:${row.id}`} row={row} />
          ))
        )}
      </div>
    </section>
  );
}

function ComingSoonMailWidget() {
  const { t } = useTranslation('apps');
  return (
    <section className="rounded-lg border border-app-border bg-app-surface p-4">
      <div className="mb-2 flex items-center gap-2">
        <h2 className="app-text-title-md text-app-ink">{t('home.mail')}</h2>
        <span className="app-text-micro rounded-full border border-app-border px-1.5 py-0.5 text-app-ink/55">
          {t('home.comingSoon')}
        </span>
      </div>
      <div className="flex flex-col items-center gap-2 py-6 text-app-ink/55">
        <Mail size={20} className="text-app-ink/45" />
        <p className="app-text-body text-center">{t('home.mailComingSoon')}</p>
      </div>
    </section>
  );
}

export const WorkspaceHomeView = () => {
  const { token, user } = useAuth();
  const { t, i18n } = useTranslation('apps');
  const { workspaceSlug = '' } = useParams();
  const { apps: workspaceApps, loading: workspaceAppsLoading } =
    useWorkspaceBootstrapProjection();
  const currentWorkspace =
    user?.workspaces.find((workspace) => workspace.slug === workspaceSlug) ??
    null;
  const userName =
    user?.display_name || user?.full_name || t('home.userFallback');
  const workspaceName =
    currentWorkspace?.name || workspaceSlug || t('home.workspaceFallback');
  const timeZone = normalizeTimeZone(user?.time_zone);
  const enabledAppIds = useMemo(
    () =>
      workspaceAppsLoading
        ? null
        : workspaceApps.flatMap((app) => (app.enabled ? [app.app_id] : [])),
    [workspaceApps, workspaceAppsLoading],
  );
  const enabledAppIdSet = useMemo(
    () => new Set(enabledAppIds ?? []),
    [enabledAppIds],
  );

  const { state } = useWorkspaceHomeController({
    enabledAppIds,
    timeZone,
    token,
    workspaceSlug,
  });
  const sections = useMemo(
    () =>
      buildWorkspaceHomeSections({
        locale: i18n.language,
        state,
        timeZone,
        t,
        workspaceSlug,
      }),
    [i18n.language, state, timeZone, t, workspaceSlug],
  );
  const briefing = useMemo(
    () => buildHomeBriefing({ state, timeZone }),
    [state, timeZone],
  );

  const plannerSection = enabledAppIdSet.has('planner')
    ? sections.find((section) => section.id === 'planner')
    : undefined;
  const meetingsSection = enabledAppIdSet.has('meeting')
    ? sections.find((section) => section.id === 'meetings')
    : undefined;
  const tasksSection = enabledAppIdSet.has('pms')
    ? sections.find((section) => section.id === 'tasks')
    : undefined;
  const docsSection = enabledAppIdSet.has('docs')
    ? sections.find((section) => section.id === 'docs')
    : undefined;
  const notificationsSection = sections.find(
    (section) => section.id === 'notifications',
  );

  return (
    <div className="custom-scrollbar h-full overflow-y-auto">
      <div className="w-full space-y-6 px-8 py-10">
        <WorkspaceHomeHeader
          userName={userName}
          workspaceName={workspaceName}
          timeZone={timeZone}
        />
        <BriefingBanner briefing={briefing} />
        <QuickActionsRow
          enabledAppIds={enabledAppIdSet}
          workspaceSlug={workspaceSlug}
        />
        {/* One grid so all columns share an identical width. Column 1 holds
            the two announcement boards (row 1 + row 2); columns 2-4 hold the
            widgets. auto-rows-fr keeps the two rows equal height. */}
        <div className="grid auto-rows-fr grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          <AnnouncementsBoard
            scope="workspace"
            title={`${workspaceName} ${t('home.announcements')}`}
          />
          {plannerSection ? (
            <WorkspaceSummarySection section={plannerSection} />
          ) : null}
          {meetingsSection ? (
            <WorkspaceSummarySection section={meetingsSection} />
          ) : null}
          {tasksSection ? (
            <WorkspaceSummarySection section={tasksSection} />
          ) : null}
          <AnnouncementsBoard
            scope="company"
            title={t('home.announcementsCompany')}
          />
          {docsSection ? (
            <WorkspaceSummarySection section={docsSection} />
          ) : null}
          {notificationsSection ? (
            <WorkspaceSummarySection section={notificationsSection} />
          ) : null}
          <ComingSoonMailWidget />
        </div>
      </div>
    </div>
  );
};
