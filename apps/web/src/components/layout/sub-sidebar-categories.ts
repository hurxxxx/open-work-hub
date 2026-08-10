export function buildSidebarCategories(
  filteredCategories: readonly string[],
): string[] {
  return Array.from(new Set(filteredCategories));
}

export interface SubSidebarCategoryExpansionState {
  key: string;
  expandedCategories: string[];
}

const CATEGORY_EXPANSION_KEY_SEPARATOR = '\u0000';

export function subSidebarCategoryExpansionKey(
  categories: readonly string[],
): string {
  return categories.join(CATEGORY_EXPANSION_KEY_SEPARATOR);
}

export function normalizeSubSidebarCategoryExpansionState(
  state: SubSidebarCategoryExpansionState,
  categories: readonly string[],
): SubSidebarCategoryExpansionState {
  const key = subSidebarCategoryExpansionKey(categories);
  if (state.key === key) {
    return state;
  }
  return {
    key,
    expandedCategories: Array.from(categories),
  };
}

export function toggleSubSidebarCategoryExpansion(
  state: SubSidebarCategoryExpansionState,
  categories: readonly string[],
  category: string,
): SubSidebarCategoryExpansionState {
  const normalized = normalizeSubSidebarCategoryExpansionState(
    state,
    categories,
  );
  return {
    key: normalized.key,
    expandedCategories: normalized.expandedCategories.includes(category)
      ? normalized.expandedCategories.filter((current) => current !== category)
      : [...normalized.expandedCategories, category],
  };
}
