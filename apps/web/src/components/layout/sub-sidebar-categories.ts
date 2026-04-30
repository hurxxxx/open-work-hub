export function buildSidebarCategories(
  filteredCategories: string[],
): string[] {
  return Array.from(new Set(filteredCategories));
}
