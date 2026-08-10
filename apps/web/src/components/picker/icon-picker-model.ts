export const ICON_PICKER_ALL_GROUP_ID = '__all__';

export type IconPickerGroup = {
  id: string;
  label: string;
  iconKeys: readonly string[];
};

export function uniqueIconPickerKeys(
  iconKeys: Iterable<string>,
): readonly string[] {
  return Array.from(new Set(iconKeys)).sort((left, right) =>
    left.localeCompare(right),
  );
}

export function iconPickerAllKeys(
  groups: readonly IconPickerGroup[],
): readonly string[] {
  return uniqueIconPickerKeys(groups.flatMap((group) => [...group.iconKeys]));
}

export function filterIconPickerKeys(
  iconKeys: readonly string[],
  query: string,
  searchTextForKey?: (iconKey: string) => string,
): readonly string[] {
  const normalizedQuery = query.trim().toLowerCase();
  if (!normalizedQuery) {
    return iconKeys;
  }
  return iconKeys.filter((iconKey) => {
    const searchText = `${iconKey} ${searchTextForKey?.(iconKey) ?? ''}`;
    return searchText.toLowerCase().includes(normalizedQuery);
  });
}
