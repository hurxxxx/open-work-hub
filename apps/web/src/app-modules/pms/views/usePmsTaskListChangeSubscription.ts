import { useEffect, useRef } from 'react';

import {
  PMS_TASK_LIST_CHANGED_EVENT,
  type PmsTaskListChangedDetail,
} from './pms-events';

export function usePmsTaskListChangeSubscription(
  onChange: (detail: PmsTaskListChangedDetail) => void,
): void {
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  useEffect(() => {
    const handleTaskListChanged = (event: Event) => {
      const detail = (event as CustomEvent<PmsTaskListChangedDetail>).detail;
      if (detail) onChangeRef.current(detail);
    };

    window.addEventListener(PMS_TASK_LIST_CHANGED_EVENT, handleTaskListChanged);
    return () => {
      window.removeEventListener(
        PMS_TASK_LIST_CHANGED_EVENT,
        handleTaskListChanged,
      );
    };
  }, []);
}
