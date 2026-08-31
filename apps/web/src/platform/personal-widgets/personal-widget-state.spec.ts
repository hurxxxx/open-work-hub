import { describe, expect, it } from 'vitest';

import {
  DEFAULT_PERSONAL_WIDGET_PREFERENCES,
  countOpenTodos,
  parsePersonalWidgetPreferences,
  personalWidgetStorageKey,
  serializePersonalWidgetPreferences,
  sortPersonalTodos,
} from './personal-widget-state';

describe('personal-widget-state', () => {
  it('namespaces browser preferences by authenticated principal', () => {
    expect(personalWidgetStorageKey('user-a')).not.toBe(
      personalWidgetStorageKey('user-b'),
    );
  });

  it('falls back to collapsed todo preferences for invalid stored values', () => {
    expect(parsePersonalWidgetPreferences(null)).toEqual(
      DEFAULT_PERSONAL_WIDGET_PREFERENCES,
    );
    expect(parsePersonalWidgetPreferences('{')).toEqual(
      DEFAULT_PERSONAL_WIDGET_PREFERENCES,
    );
    expect(
      parsePersonalWidgetPreferences(
        JSON.stringify({ activeWidget: 'memo', mode: 'wide' }),
      ),
    ).toEqual({ activeWidget: 'memo', mode: 'collapsed' });
  });

  it('round-trips valid todo preferences', () => {
    const serialized = serializePersonalWidgetPreferences({
      activeWidget: 'todo',
      mode: 'fullscreen',
    });

    expect(parsePersonalWidgetPreferences(serialized)).toEqual({
      activeWidget: 'todo',
      mode: 'fullscreen',
    });
  });

  it('accepts memo as an active widget', () => {
    expect(
      parsePersonalWidgetPreferences(
        JSON.stringify({ activeWidget: 'memo', mode: 'panel' }),
      ),
    ).toEqual({ activeWidget: 'memo', mode: 'panel' });
  });

  it('falls back from dm because DM uses its own floating panel', () => {
    expect(
      parsePersonalWidgetPreferences(
        JSON.stringify({ activeWidget: 'dm', mode: 'panel' }),
      ),
    ).toEqual({ activeWidget: 'todo', mode: 'panel' });
  });

  it('counts open todos', () => {
    expect(
      countOpenTodos([
        { completed: false },
        { completed: true },
        { completed: false },
      ]),
    ).toBe(2);
  });

  it('sorts incomplete todos before completed ones', () => {
    const sorted = sortPersonalTodos([
      {
        id: 'completed',
        completed: true,
        sortOrder: 1000,
        createdAt: '2026-01-01T00:00:00Z',
      },
      {
        id: 'later',
        completed: false,
        sortOrder: 2000,
        createdAt: '2026-01-03T00:00:00Z',
      },
      {
        id: 'earlier',
        completed: false,
        sortOrder: 1000,
        createdAt: '2026-01-02T00:00:00Z',
      },
    ]);

    expect(sorted.map((item) => item.id)).toEqual([
      'earlier',
      'later',
      'completed',
    ]);
  });
});
