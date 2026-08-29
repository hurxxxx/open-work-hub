import { useEffect, useReducer } from 'react';

import {
  listRecentPages,
  type RecentPageItem,
} from '@/src/app-modules/docs/public-api';
import {
  listMeetings,
  type MeetingListItem,
} from '@/src/app-modules/meeting/public-api';
import {
  listPlannerEvents,
  type PlannerEvent,
} from '@/src/app-modules/planner/public-api';
import {
  listAssignedTasks,
  type PmsTask,
} from '@/src/app-modules/pms/public-api';
import { zonedDateKey } from '@/src/platform/time/time-utils';
import {
  INITIAL_WORKSPACE_HOME_STATE,
  workspaceHomeReducer,
  type WorkspaceHomeState,
} from './workspace-home-model';

const PLANNER_LOOKAHEAD_DAYS = 31;
const DAY_MS = 24 * 60 * 60 * 1000;

export interface WorkspaceHomeClient {
  listAssignedTasks(
    token: string,
    options: { limit: number; workspaceSlug: string },
  ): Promise<{ items: PmsTask[] }>;
  listMeetings(
    token: string,
    workspaceSlug: string,
    options: { scope: 'upcoming' },
  ): Promise<{ items: MeetingListItem[] }>;
  listPlannerEvents(
    token: string,
    options: { from?: string; to?: string },
  ): Promise<{ items: PlannerEvent[] }>;
  listRecentPages(
    token: string,
    limit: number,
    workspaceSlug: string,
  ): Promise<RecentPageItem[]>;
}

export interface WorkspaceHomeControllerOptions {
  client?: WorkspaceHomeClient;
  enabledAppIds: readonly string[] | null;
  timeZone: string;
  token: string | null | undefined;
  workspaceSlug: string;
}

export interface WorkspaceHomeController {
  state: WorkspaceHomeState;
}

const defaultClient: WorkspaceHomeClient = {
  listAssignedTasks,
  listMeetings,
  listPlannerEvents,
  listRecentPages,
};

export function useWorkspaceHomeController({
  client = defaultClient,
  enabledAppIds,
  timeZone,
  token,
  workspaceSlug,
}: WorkspaceHomeControllerOptions): WorkspaceHomeController {
  const [state, dispatch] = useReducer(
    workspaceHomeReducer,
    INITIAL_WORKSPACE_HOME_STATE,
  );

  useEffect(() => {
    if (!token || !workspaceSlug || enabledAppIds === null) return undefined;
    let cancelled = false;
    const enabledApps = new Set(enabledAppIds);

    dispatch({ type: 'load-started' });
    if (enabledApps.has('meeting')) {
      void client
        .listMeetings(token, workspaceSlug, { scope: 'upcoming' })
        .then((response) => {
          if (!cancelled) {
            dispatch({ type: 'meetings-loaded', items: response.items });
          }
        })
        .catch(() => {
          if (!cancelled) dispatch({ type: 'meetings-failed' });
        });
    } else {
      dispatch({ type: 'meetings-loaded', items: [] });
    }

    if (enabledApps.has('pms')) {
      void client
        .listAssignedTasks(token, { limit: 10, workspaceSlug })
        .then((response) => {
          if (!cancelled) {
            dispatch({ type: 'issues-loaded', items: response.items });
          }
        })
        .catch(() => {
          if (!cancelled) dispatch({ type: 'issues-failed' });
        });
    } else {
      dispatch({ type: 'issues-loaded', items: [] });
    }

    if (enabledApps.has('docs')) {
      void client
        .listRecentPages(token, 10, workspaceSlug)
        .then((response) => {
          if (!cancelled) dispatch({ type: 'pages-loaded', items: response });
        })
        .catch(() => {
          if (!cancelled) dispatch({ type: 'pages-failed' });
        });
    } else {
      dispatch({ type: 'pages-loaded', items: [] });
    }

    if (enabledApps.has('planner')) {
      const now = new Date();
      const plannerFrom = zonedDateKey(now, timeZone);
      const plannerTo = zonedDateKey(
        new Date(now.getTime() + PLANNER_LOOKAHEAD_DAYS * DAY_MS),
        timeZone,
      );
      void client
        .listPlannerEvents(token, {
          from: plannerFrom,
          to: plannerTo,
        })
        .then((response) => {
          if (!cancelled) {
            dispatch({ type: 'planner-loaded', items: response.items });
          }
        })
        .catch(() => {
          if (!cancelled) dispatch({ type: 'planner-failed' });
        });
    } else {
      dispatch({ type: 'planner-loaded', items: [] });
    }

    return () => {
      cancelled = true;
    };
  }, [client, enabledAppIds, timeZone, token, workspaceSlug]);

  return { state };
}
