import { useAuth } from '@/src/platform/auth/auth-provider';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  getPmsViewPreferences,
  updatePmsViewPreferences,
  type PmsTaskListGroupBy,
} from '../api/pms-api';

const DEFAULT_GROUP_BY: PmsTaskListGroupBy = 'status';

export function usePmsTaskListGroupPreference({
  enabled,
}: {
  enabled: boolean;
}): {
  groupBy: PmsTaskListGroupBy;
  setGroupBy: (groupBy: PmsTaskListGroupBy) => void;
} {
  const { token } = useAuth();
  const [groupBy, setGroupByState] =
    useState<PmsTaskListGroupBy>(DEFAULT_GROUP_BY);
  const activeScopeRef = useRef(0);
  const loadVersionRef = useRef(0);
  const latestGroupByRef = useRef<PmsTaskListGroupBy>(DEFAULT_GROUP_BY);
  const persistedGroupByRef = useRef<PmsTaskListGroupBy>(DEFAULT_GROUP_BY);
  const saveQueueRef = useRef<Promise<void>>(Promise.resolve());

  useEffect(() => {
    const scope = activeScopeRef.current + 1;
    activeScopeRef.current = scope;
    loadVersionRef.current += 1;
    latestGroupByRef.current = DEFAULT_GROUP_BY;
    persistedGroupByRef.current = DEFAULT_GROUP_BY;
    saveQueueRef.current = Promise.resolve();
    setGroupByState(DEFAULT_GROUP_BY);
    if (!enabled || !token) return undefined;

    const loadVersion = loadVersionRef.current;
    let cancelled = false;
    void getPmsViewPreferences(token).then(
      (preference) => {
        if (
          cancelled ||
          activeScopeRef.current !== scope ||
          loadVersionRef.current !== loadVersion
        ) {
          return;
        }
        latestGroupByRef.current = preference.task_list_group_by;
        persistedGroupByRef.current = preference.task_list_group_by;
        setGroupByState(preference.task_list_group_by);
      },
      () => undefined,
    );

    return () => {
      cancelled = true;
    };
  }, [enabled, token]);

  const setGroupBy = useCallback(
    (nextGroupBy: PmsTaskListGroupBy) => {
      latestGroupByRef.current = nextGroupBy;
      loadVersionRef.current += 1;
      setGroupByState(nextGroupBy);

      const scope = activeScopeRef.current;
      if (!enabled || !token) return;

      const save = saveQueueRef.current.then(() =>
        updatePmsViewPreferences(token, { task_list_group_by: nextGroupBy }),
      );
      saveQueueRef.current = save.then(
        () => undefined,
        () => undefined,
      );
      void save.then(
        (preference) => {
          if (activeScopeRef.current === scope) {
            persistedGroupByRef.current = preference.task_list_group_by;
          }
        },
        () => {
          if (
            activeScopeRef.current === scope &&
            latestGroupByRef.current === nextGroupBy
          ) {
            latestGroupByRef.current = persistedGroupByRef.current;
            setGroupByState(persistedGroupByRef.current);
          }
        },
      );
    },
    [enabled, token],
  );

  return { groupBy, setGroupBy };
}
