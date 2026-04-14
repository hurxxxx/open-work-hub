const TASK_LIST_ROLE_RANK: Record<string, number> = {
  viewer: 0,
  member: 1,
  editor: 1,
  admin: 2,
  owner: 3,
};

export function taskListRoleAllows(
  role: string | null | undefined,
  minRole: keyof typeof TASK_LIST_ROLE_RANK,
): boolean {
  if (!role) {
    return false;
  }

  return (TASK_LIST_ROLE_RANK[role] ?? -1) >= TASK_LIST_ROLE_RANK[minRole];
}
