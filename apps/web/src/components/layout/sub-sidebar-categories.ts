export function buildSidebarCategories(
  filteredCategories: string[],
  activeAppId: string,
  canShowPmsSpaces: boolean,
): string[] {
  const categories = Array.from(new Set(filteredCategories));
  if (activeAppId !== 'pms' || !canShowPmsSpaces) {
    return categories;
  }

  return ['Spaces', ...categories.filter((category) => category !== 'Spaces')];
}
