import { describe, expect, it } from 'vitest';

import {
  selectUserOptionsForPicker,
  userOptionDepartmentName,
  userOptionDisplayName,
  userOptionAvatarInitials,
  userOptionNameWithDepartment,
  userOptionMetaParts,
  type UserOptionLike,
} from './user-option-picker-model';

function user(overrides: Partial<UserOptionLike>): UserOptionLike {
  return {
    id: 'user-1',
    full_name: 'Ada Lovelace',
    email: 'ada@example.test',
    ...overrides,
  };
}

describe('user option picker model', () => {
  it('matches trimmed case-insensitive query against name and email', () => {
    const users = [
      user({ id: 'ada', full_name: 'Ada Lovelace', email: 'ada@example.test' }),
      user({ id: 'grace', full_name: 'Grace Hopper', email: 'navy@example.test' }),
      user({ id: 'alan', full_name: 'Alan Turing', email: 'alan@example.test' }),
    ];

    expect(
      selectUserOptionsForPicker({
        users,
        query: '  HOPPER ',
      }).map((candidate) => candidate.id),
    ).toEqual(['grace']);

    expect(
      selectUserOptionsForPicker({
        users,
        query: 'EXAMPLE',
        limit: 2,
      }).map((candidate) => candidate.id),
    ).toEqual(['ada', 'grace']);
  });

  it('matches department, display name, and job title fields', () => {
    const users = [
      user({
        id: 'dept',
        full_name: 'Kim Mina',
        primary_org_unit_name: 'AI Platform',
      }),
      user({
        id: 'display',
        display_name: 'Mason',
        full_name: 'Lee Minseok',
      }),
      user({
        id: 'job',
        full_name: 'Park Hana',
        job_title: 'Product Owner',
      }),
    ];

    expect(
      selectUserOptionsForPicker({ users, query: 'platform' }).map(
        (candidate) => candidate.id,
      ),
    ).toEqual(['dept']);
    expect(
      selectUserOptionsForPicker({ users, query: 'mason' }).map(
        (candidate) => candidate.id,
      ),
    ).toEqual(['display']);
    expect(
      selectUserOptionsForPicker({ users, query: 'owner' }).map(
        (candidate) => candidate.id,
      ),
    ).toEqual(['job']);
  });

  it('excludes before applying the limit and preserves input order', () => {
    const users = [
      user({ id: 'excluded', full_name: 'Excluded User' }),
      user({ id: 'first', full_name: 'First User' }),
      user({ id: 'second', full_name: 'Second User' }),
    ];

    expect(
      selectUserOptionsForPicker({
        users,
        query: '',
        excludeIds: new Set(['excluded']),
        limit: 2,
      }).map((candidate) => candidate.id),
    ).toEqual(['first', 'second']);
  });

  it('pins the current user first when selectable', () => {
    const users = [
      user({ id: 'first', full_name: 'First User' }),
      user({ id: 'self', full_name: 'Current User' }),
      user({ id: 'second', full_name: 'Second User' }),
    ];

    expect(
      selectUserOptionsForPicker({
        users,
        query: 'second',
        currentUserId: 'self',
        limit: 2,
      }).map((candidate) => candidate.id),
    ).toEqual(['self', 'second']);

    expect(
      selectUserOptionsForPicker({
        users,
        query: '',
        currentUserId: 'self',
        excludeIds: new Set(['self']),
      }).map((candidate) => candidate.id),
    ).toEqual(['first', 'second']);
  });

  it('falls back to email when a name is missing', () => {
    expect(
      selectUserOptionsForPicker({
        users: [
          user({ id: 'missing-name', full_name: null, email: 'team@example.test' }),
        ],
        query: 'team@',
      }).map((candidate) => candidate.id),
    ).toEqual(['missing-name']);
  });

  it('returns no candidates for a non-positive limit', () => {
    expect(
      selectUserOptionsForPicker({
        users: [user({ id: 'ada' })],
        query: '',
        limit: 0,
      }),
    ).toEqual([]);
  });

  it('formats display and meta labels for picker rows', () => {
    const candidate = user({
      id: 'dept',
      full_name: null,
      display_name: 'Display Name',
      primary_org_unit_name: 'Design Ops',
      email: 'design@example.test',
    });

    expect(userOptionDisplayName(candidate)).toBe('Display Name');
    expect(userOptionNameWithDepartment(candidate)).toBe(
      'Display Name - Design Ops',
    );
    expect(userOptionDepartmentName(candidate)).toBe('Design Ops');
    expect(userOptionMetaParts(candidate)).toEqual([
      'Design Ops',
      'design@example.test',
    ]);
  });

  it('uses a single leading character for compact avatars', () => {
    expect(userOptionAvatarInitials(user({ full_name: '허건우' }))).toBe('허');
    expect(userOptionAvatarInitials(user({ full_name: 'Ada Lovelace' }))).toBe('A');
  });
});
