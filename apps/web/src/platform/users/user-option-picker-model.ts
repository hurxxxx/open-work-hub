export type UserOptionLike = {
  id: string;
  display_name?: string | null;
  department?: string | null;
  full_name?: string | null;
  job_title?: string | null;
  email: string;
  primary_org_unit?: { name?: string | null } | null;
  primary_org_unit_name?: string | null;
};

export function userOptionDisplayName(user: UserOptionLike): string {
  return user.full_name || user.display_name || user.email || user.id;
}

export function userOptionDepartmentName(user: UserOptionLike): string | null {
  return (
    user.department ||
    user.primary_org_unit_name ||
    user.primary_org_unit?.name ||
    null
  );
}

export function userOptionNameWithDepartment(user: UserOptionLike): string {
  const name = userOptionDisplayName(user);
  const department = userOptionDepartmentName(user);
  return department ? `${name} - ${department}` : name;
}

export function userOptionMetaParts(user: UserOptionLike): string[] {
  return [userOptionDepartmentName(user), user.email].filter(
    (part): part is string => Boolean(part),
  );
}

export function userOptionAvatarInitials(user: UserOptionLike): string {
  const label = userOptionDisplayName(user);
  return Array.from(label.trim())[0]?.toUpperCase() ?? '?';
}

const USER_OPTION_AVATAR_COLORS = [
  'bg-rose-500',
  'bg-pink-500',
  'bg-fuchsia-500',
  'bg-purple-500',
  'bg-violet-500',
  'bg-indigo-500',
  'bg-blue-500',
  'bg-sky-500',
  'bg-cyan-500',
  'bg-teal-500',
  'bg-emerald-500',
  'bg-green-500',
  'bg-amber-500',
  'bg-orange-500',
] as const;

export function userOptionAvatarColorClass(seed: string): string {
  let hash = 0;
  for (let index = 0; index < seed.length; index += 1) {
    hash = (hash * 31 + seed.charCodeAt(index)) >>> 0;
  }
  return USER_OPTION_AVATAR_COLORS[hash % USER_OPTION_AVATAR_COLORS.length];
}

export function userOptionMatchesQuery(
  user: UserOptionLike,
  query: string,
): boolean {
  const normalizedQuery = query.trim().toLowerCase();
  if (!normalizedQuery) return true;

  const department = userOptionDepartmentName(user)?.toLowerCase() ?? '';
  const displayName = user.display_name?.toLowerCase() ?? '';
  const jobTitle = user.job_title?.toLowerCase() ?? '';
  const name = user.full_name?.toLowerCase() ?? '';
  const email = user.email.toLowerCase();
  return (
    name.includes(normalizedQuery) ||
    displayName.includes(normalizedQuery) ||
    email.includes(normalizedQuery) ||
    department.includes(normalizedQuery) ||
    jobTitle.includes(normalizedQuery)
  );
}

export function selectUserOptionsForPicker<T extends UserOptionLike>({
  users,
  query,
  currentUserId,
  excludeIds,
  limit = Number.POSITIVE_INFINITY,
}: {
  users: readonly T[];
  query: string;
  currentUserId?: string | null;
  excludeIds?: ReadonlySet<string>;
  limit?: number;
}): T[] {
  if (limit <= 0) {
    return [];
  }

  const selected: T[] = [];
  let currentUser: T | null = null;

  for (const user of users) {
    if (excludeIds?.has(user.id)) {
      continue;
    }

    if (currentUserId && user.id === currentUserId) {
      currentUser = user;
      continue;
    }

    if (!userOptionMatchesQuery(user, query)) {
      continue;
    }

    selected.push(user);
    if (selected.length >= limit && !currentUserId) {
      break;
    }
  }

  const withCurrentUser = currentUser
    ? [currentUser, ...selected.filter((user) => user.id !== currentUser.id)]
    : selected;
  return withCurrentUser.slice(0, limit);
}
