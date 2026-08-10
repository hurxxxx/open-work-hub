export type PlannerEventChoicePopoverAnchor = {
  x: number;
  y: number;
};

export type PlannerEventChoicePopoverViewport = {
  width: number;
  height: number;
};

export type PlannerEventChoicePopoverPlacement = {
  top: number;
  left: number;
  width: number;
};

export const PLANNER_EVENT_CHOICE_POPOVER_WIDTH = 220;
export const PLANNER_EVENT_CHOICE_POPOVER_HEIGHT = 148;
export const PLANNER_EVENT_CHOICE_POPOVER_MARGIN = 12;
export const PLANNER_EVENT_CHOICE_POPOVER_OFFSET = 8;

export function resolvePlannerEventChoicePopoverPlacement({
  anchor,
  viewport,
}: {
  anchor: PlannerEventChoicePopoverAnchor | null;
  viewport: PlannerEventChoicePopoverViewport;
}): PlannerEventChoicePopoverPlacement {
  if (anchor) {
    return {
      top: clampPopoverAxis(
        anchor.y + PLANNER_EVENT_CHOICE_POPOVER_OFFSET,
        viewport.height,
        PLANNER_EVENT_CHOICE_POPOVER_HEIGHT,
      ),
      left: clampPopoverAxis(
        anchor.x + PLANNER_EVENT_CHOICE_POPOVER_OFFSET,
        viewport.width,
        PLANNER_EVENT_CHOICE_POPOVER_WIDTH,
      ),
      width: PLANNER_EVENT_CHOICE_POPOVER_WIDTH,
    };
  }

  return {
    top: Math.max(
      (viewport.height - PLANNER_EVENT_CHOICE_POPOVER_HEIGHT) / 2,
      PLANNER_EVENT_CHOICE_POPOVER_MARGIN,
    ),
    left: Math.max(
      (viewport.width - PLANNER_EVENT_CHOICE_POPOVER_WIDTH) / 2,
      PLANNER_EVENT_CHOICE_POPOVER_MARGIN,
    ),
    width: PLANNER_EVENT_CHOICE_POPOVER_WIDTH,
  };
}

function clampPopoverAxis(
  value: number,
  viewportSize: number,
  popoverSize: number,
): number {
  return Math.min(
    Math.max(value, PLANNER_EVENT_CHOICE_POPOVER_MARGIN),
    viewportSize - popoverSize - PLANNER_EVENT_CHOICE_POPOVER_MARGIN,
  );
}
