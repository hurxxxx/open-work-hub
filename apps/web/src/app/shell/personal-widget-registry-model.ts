export function resolvePersonalWidgetDockPanels<T>({
  dmPanel,
  plannerEnabled,
  pmsEnabled,
  pmsPanel,
  todayPlannerPanel,
}: {
  dmPanel: T;
  plannerEnabled: boolean;
  pmsEnabled: boolean;
  pmsPanel: T;
  todayPlannerPanel: T;
}): T[] {
  return [
    dmPanel,
    ...(pmsEnabled ? [pmsPanel] : []),
    ...(plannerEnabled ? [todayPlannerPanel] : []),
  ];
}
