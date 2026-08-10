import { describe, expect, it } from 'vitest';

import { resolvePersonalWidgetDockPanels } from './personal-widget-registry-model';

describe('personal widget registry model', () => {
  it('includes app-owned panels only while their bootstrap apps are enabled', () => {
    const panels = {
      dmPanel: 'dm',
      pmsPanel: 'pms',
      todayPlannerPanel: 'today-planner',
    };

    expect(
      resolvePersonalWidgetDockPanels({
        ...panels,
        plannerEnabled: false,
        pmsEnabled: false,
      }),
    ).toEqual(['dm']);
    expect(
      resolvePersonalWidgetDockPanels({
        ...panels,
        plannerEnabled: true,
        pmsEnabled: true,
      }),
    ).toEqual(['dm', 'pms', 'today-planner']);
  });
});
