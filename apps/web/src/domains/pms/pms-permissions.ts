const PROJECT_ROLE_RANK: Record<string, number> = {
  viewer: 0,
  member: 1,
  editor: 1,
  admin: 2,
  owner: 3,
};

export function projectRoleAllows(
  role: string | null | undefined,
  minRole: keyof typeof PROJECT_ROLE_RANK,
): boolean {
  if (!role) {
    return false;
  }

  return (PROJECT_ROLE_RANK[role] ?? -1) >= PROJECT_ROLE_RANK[minRole];
}
