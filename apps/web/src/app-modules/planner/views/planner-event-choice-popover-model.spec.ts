import { describe, expect, it } from 'vitest';

import {
  PLANNER_EVENT_CHOICE_POPOVER_MARGIN,
  PLANNER_EVENT_CHOICE_POPOVER_WIDTH,
  resolvePlannerEventChoicePopoverPlacement,
} from './planner-event-choice-popover-model';

describe('planner event choice popover model', () => {
  it('places an anchored popover with offset inside a normal viewport', () => {
    expect(
      resolvePlannerEventChoicePopoverPlacement({
        anchor: { x: 40, y: 60 },
        viewport: { width: 1000, height: 800 },
      }),
    ).toEqual({
      top: 68,
      left: 48,
      width: PLANNER_EVENT_CHOICE_POPOVER_WIDTH,
    });
  });

  it('clamps anchored placement near viewport edges', () => {
    expect(
      resolvePlannerEventChoicePopoverPlacement({
        anchor: { x: 990, y: 790 },
        viewport: { width: 1000, height: 800 },
      }),
    ).toEqual({
      top: 640,
      left: 768,
      width: PLANNER_EVENT_CHOICE_POPOVER_WIDTH,
    });

    expect(
      resolvePlannerEventChoicePopoverPlacement({
        anchor: { x: -100, y: -100 },
        viewport: { width: 1000, height: 800 },
      }),
    ).toEqual({
      top: PLANNER_EVENT_CHOICE_POPOVER_MARGIN,
      left: PLANNER_EVENT_CHOICE_POPOVER_MARGIN,
      width: PLANNER_EVENT_CHOICE_POPOVER_WIDTH,
    });
  });

  it('centers an unanchored popover while respecting minimum margins', () => {
    expect(
      resolvePlannerEventChoicePopoverPlacement({
        anchor: null,
        viewport: { width: 1000, height: 800 },
      }),
    ).toEqual({
      top: 326,
      left: 390,
      width: PLANNER_EVENT_CHOICE_POPOVER_WIDTH,
    });

    expect(
      resolvePlannerEventChoicePopoverPlacement({
        anchor: null,
        viewport: { width: 200, height: 100 },
      }),
    ).toEqual({
      top: PLANNER_EVENT_CHOICE_POPOVER_MARGIN,
      left: PLANNER_EVENT_CHOICE_POPOVER_MARGIN,
      width: PLANNER_EVENT_CHOICE_POPOVER_WIDTH,
    });
  });
});
