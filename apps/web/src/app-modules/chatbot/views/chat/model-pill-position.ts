export interface PanelPosition {
  top: number;
  left: number;
  width: number;
}

// Pure helper so the clamp logic can be unit-tested without jsdom layout.
// Anchors the panel's right edge to the trigger's right edge, then clamps
// `left` within [margin, viewportWidth - width - margin] so the panel can
// never overflow either side of the viewport.
export function computePanelPosition(
  triggerRect: { bottom: number; right: number },
  viewportWidth: number,
  options?: { desiredWidth?: number; margin?: number; offset?: number },
): PanelPosition {
  const { desiredWidth = 320, margin = 8, offset = 8 } = options ?? {};
  const width = Math.max(0, Math.min(desiredWidth, viewportWidth - margin * 2));
  const maxLeft = Math.max(margin, viewportWidth - width - margin);
  const preferredLeft = triggerRect.right - width;
  const left = Math.max(margin, Math.min(maxLeft, preferredLeft));
  return { top: triggerRect.bottom + offset, left, width };
}
