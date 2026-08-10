export type PersonalWidgetMode = 'collapsed' | 'panel' | 'fullscreen';
export type PersonalWidgetId = 'todo' | 'memo';

export interface PersonalWidgetPreferences {
  activeWidget: PersonalWidgetId;
  mode: PersonalWidgetMode;
}

export interface PersonalWidgetTodoLike {
  completed: boolean;
  createdAt?: string;
  sortOrder: number;
}

export const PERSONAL_WIDGET_STORAGE_KEY = 'open-alm.personalWidget.v1';

export const DEFAULT_PERSONAL_WIDGET_PREFERENCES: PersonalWidgetPreferences = {
  activeWidget: 'todo',
  mode: 'collapsed',
};

export function parsePersonalWidgetPreferences(
  rawValue: string | null,
): PersonalWidgetPreferences {
  if (!rawValue) {
    return DEFAULT_PERSONAL_WIDGET_PREFERENCES;
  }
  try {
    const parsed = JSON.parse(rawValue) as Partial<PersonalWidgetPreferences>;
    return {
      activeWidget: isPersonalWidgetId(parsed.activeWidget)
        ? parsed.activeWidget
        : 'todo',
      mode: isPersonalWidgetMode(parsed.mode)
        ? parsed.mode
        : DEFAULT_PERSONAL_WIDGET_PREFERENCES.mode,
    };
  } catch {
    return DEFAULT_PERSONAL_WIDGET_PREFERENCES;
  }
}

export function serializePersonalWidgetPreferences(
  preferences: PersonalWidgetPreferences,
): string {
  return JSON.stringify(preferences);
}

export function countOpenTodos<T extends { completed: boolean }>(
  items: readonly T[],
): number {
  return items.filter((item) => !item.completed).length;
}

export function sortPersonalTodos<T extends PersonalWidgetTodoLike>(
  items: readonly T[],
): T[] {
  return [...items].sort((left, right) => {
    if (left.completed !== right.completed) {
      return left.completed ? 1 : -1;
    }
    if (left.sortOrder !== right.sortOrder) {
      return left.sortOrder - right.sortOrder;
    }
    return Date.parse(right.createdAt ?? '') - Date.parse(left.createdAt ?? '');
  });
}

function isPersonalWidgetMode(value: unknown): value is PersonalWidgetMode {
  return value === 'collapsed' || value === 'panel' || value === 'fullscreen';
}

function isPersonalWidgetId(value: unknown): value is PersonalWidgetId {
  return value === 'todo' || value === 'memo';
}
