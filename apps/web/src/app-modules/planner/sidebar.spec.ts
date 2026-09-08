import { describe, expect, it, vi } from 'vitest';

import type { AppSidebarActionContext } from '@/src/app/shell/sidebar-types';
import { plannerSidebarConfig } from './sidebar';

function actionContext(
  enabledShellAppIds: readonly string[],
): AppSidebarActionContext {
  return {
    currentPathname: '/apps/planner',
    enabledShellAppIds,
    navigate: vi.fn() as unknown as AppSidebarActionContext['navigate'],
    user: null,
  };
}

describe('planner sidebar config', () => {
  it('keeps event creation available when meeting is disabled', () => {
    const actions =
      plannerSidebarConfig.createActions?.(actionContext(['planner'])) ?? [];

    expect(actions.map((action) => action.id)).toEqual([
      'planner-create-event',
    ]);
  });

  it('shows meeting creation only when the meeting app is enabled', () => {
    const actions =
      plannerSidebarConfig.createActions?.(
        actionContext(['planner', 'meeting']),
      ) ?? [];

    expect(actions.map((action) => action.id)).toEqual([
      'planner-create-event',
      'planner-create-meeting',
    ]);
  });
});
