import { useCallback, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CalendarDays, ClipboardList, MessagesSquare } from 'lucide-react';

import {
  dmManifest,
  FloatingDmWidget,
  type DmThreadScrollSnapshots,
  useFloatingDmUnreadCount,
} from '@/src/app-modules/dm';
import {
  FloatingTodayPlannerWidget,
  plannerManifest,
  useFloatingTodayPlannerCount,
} from '@/src/app-modules/planner';
import {
  FloatingPmsWidget,
  pmsManifest,
  type FloatingPmsWidgetOpenRequest,
  useFloatingPmsAssignedSummary,
} from '@/src/app-modules/pms';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { normalizeTimeZone } from '@/src/platform/time/time-utils';
import { useWorkspaceBootstrapContext } from '@/src/platform/workspaces/workspace-bootstrap-context';
import {
  PersonalWidgetHost,
  type PersonalWidgetSecondaryPanelAdapter,
} from '@/src/platform/personal-widgets/PersonalWidgetHost';
import type { PersonalTodoItem } from '@/src/platform/personal-widgets/personal-widgets-api';
import {
  FLOATING_DM_OPEN_EVENT,
  type FloatingDmOpenEventDetail,
  FLOATING_PMS_OPEN_EVENT,
  dispatchFloatingPmsOpen,
  type FloatingPmsOpenEventDetail,
} from '@/src/platform/personal-widgets/floating-panel-events';
import { resolvePersonalWidgetDockPanels } from './personal-widget-registry-model';

export function ShellPersonalWidgetHost() {
  const { token, user } = useAuth();
  const { t } = useTranslation('shell');
  const workspaceBootstrap = useWorkspaceBootstrapContext();
  const currentWorkspaceSlug = workspaceBootstrap.data?.workspace.slug ?? null;
  const plannerEnabled = Boolean(
    workspaceBootstrap.globalApps?.platform_enabled_app_ids.includes(
      plannerManifest.appBarItem.id,
    ),
  );
  const timeZone = normalizeTimeZone(user?.time_zone);
  const [dmThreadId, setDmThreadId] = useState('');
  const [dmReloadSeq, setDmReloadSeq] = useState(0);
  const [pmsReloadSeq, setPmsReloadSeq] = useState(0);
  const [pmsOpenRequest, setPmsOpenRequest] =
    useState<FloatingPmsWidgetOpenRequest | null>(null);
  const [plannerReloadSeq, setPlannerReloadSeq] = useState(0);
  const pmsOpenRequestSeqRef = useRef(0);
  const dmThreadScrollSnapshotsRef = useRef<DmThreadScrollSnapshots>({});
  const dmUnreadCount = useFloatingDmUnreadCount(token, dmReloadSeq);
  const pmsAssignedSummary = useFloatingPmsAssignedSummary(token, pmsReloadSeq);
  const pmsEnabled = pmsAssignedSummary.available;
  const pmsAssignedCount = pmsAssignedSummary.count;
  const todayPlannerCount = useFloatingTodayPlannerCount(
    plannerEnabled ? token : null,
    timeZone,
    plannerReloadSeq,
  );
  const handleConvertTodoToPms = useCallback((todo: PersonalTodoItem) => {
    dispatchFloatingPmsOpen({
      mode: 'createTask',
      preserveActivePanel: true,
      sourceTodoId: todo.id,
      title: todo.title,
    });
  }, []);
  const handlePmsCreateTaskOpenRequest = useCallback((requestId: number) => {
    setPmsOpenRequest((current) =>
      current?.id === requestId ? null : current,
    );
  }, []);
  const dmPanel = useMemo<PersonalWidgetSecondaryPanelAdapter>(
    () => ({
      badgeClassName: 'bg-blue-600 text-white',
      getLauncherLabel: (count) =>
        t('personalWidgets.dm.openWithUnread', { count }),
      id: dmManifest.moduleId,
      onOpenEvent: (event) => {
        const detail = (event as CustomEvent<FloatingDmOpenEventDetail>).detail;
        setDmThreadId(detail?.threadId ?? '');
      },
      onReload: () => setDmReloadSeq((current) => current + 1),
      openEventName: FLOATING_DM_OPEN_EVENT,
      renderIcon: (size) => (
        <MessagesSquare aria-hidden="true" size={size} strokeWidth={2.2} />
      ),
      renderPanel: () => (
        <FloatingDmWidget
          onThreadIdChange={setDmThreadId}
          reloadSeq={dmReloadSeq}
          threadScrollSnapshotsRef={dmThreadScrollSnapshotsRef}
          threadId={dmThreadId}
        />
      ),
      shortTitle: t('personalWidgets.dm.shortTitle'),
      title: t('personalWidgets.dm.title'),
      unreadCount: dmUnreadCount,
    }),
    [dmReloadSeq, dmThreadId, dmThreadScrollSnapshotsRef, dmUnreadCount, t],
  );
  const pmsPanel = useMemo<PersonalWidgetSecondaryPanelAdapter>(
    () => ({
      badgeClassName: 'bg-emerald-600 text-white',
      getLauncherLabel: (count) =>
        t('personalWidgets.pms.openWithAssigned', { count }),
      id: pmsManifest.appBarItem.id,
      mountInBackgroundOnOpen: true,
      onOpenEvent: (event) => {
        const detail = (event as CustomEvent<FloatingPmsOpenEventDetail>)
          .detail;
        pmsOpenRequestSeqRef.current += 1;
        setPmsOpenRequest({
          detail: detail ?? { mode: 'panel' },
          id: pmsOpenRequestSeqRef.current,
        });
      },
      onReload: () => setPmsReloadSeq((current) => current + 1),
      openEventName: FLOATING_PMS_OPEN_EVENT,
      renderIcon: (size) => (
        <ClipboardList aria-hidden="true" size={size} strokeWidth={2.1} />
      ),
      renderPanel: () => (
        <FloatingPmsWidget
          onChanged={() => setPmsReloadSeq((current) => current + 1)}
          onCreateTaskOpenRequestHandled={handlePmsCreateTaskOpenRequest}
          openRequest={pmsOpenRequest}
          reloadSeq={pmsReloadSeq}
          workspaceSlug={currentWorkspaceSlug}
        />
      ),
      shouldActivateOnOpen: (event) => {
        const detail = (event as CustomEvent<FloatingPmsOpenEventDetail>)
          .detail;
        return !(
          detail?.mode === 'createTask' && detail.preserveActivePanel === true
        );
      },
      shortTitle: t('personalWidgets.pms.shortTitle'),
      title: t('personalWidgets.pms.title'),
      unreadCount: pmsAssignedCount,
    }),
    [
      currentWorkspaceSlug,
      handlePmsCreateTaskOpenRequest,
      pmsAssignedCount,
      pmsOpenRequest,
      pmsReloadSeq,
      t,
    ],
  );
  const todayPlannerPanel = useMemo<PersonalWidgetSecondaryPanelAdapter>(
    () => ({
      badgeClassName: 'bg-amber-600 text-white',
      getLauncherLabel: (count) =>
        t('personalWidgets.planner.openWithToday', { count }),
      id: 'today-planner',
      onReload: () => setPlannerReloadSeq((current) => current + 1),
      renderIcon: (size) => (
        <CalendarDays aria-hidden="true" size={size} strokeWidth={2.1} />
      ),
      renderPanel: () => (
        <FloatingTodayPlannerWidget
          onChanged={() => setPlannerReloadSeq((current) => current + 1)}
          reloadSeq={plannerReloadSeq}
        />
      ),
      shortTitle: t('personalWidgets.planner.shortTitle'),
      title: t('personalWidgets.planner.title'),
      unreadCount: todayPlannerCount,
    }),
    [plannerReloadSeq, t, todayPlannerCount],
  );
  const dockPanels = useMemo(
    () =>
      resolvePersonalWidgetDockPanels({
        dmPanel,
        plannerEnabled,
        pmsEnabled,
        pmsPanel,
        todayPlannerPanel,
      }),
    [dmPanel, plannerEnabled, pmsEnabled, pmsPanel, todayPlannerPanel],
  );

  return (
    <PersonalWidgetHost
      dockPanels={dockPanels}
      onConvertTodoToPms={handleConvertTodoToPms}
    />
  );
}
