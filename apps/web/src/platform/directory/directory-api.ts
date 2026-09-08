import { apiFetchJson } from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';
export type DirectoryPerson = ApiSchema<'CompanyDirectoryPersonResponse'>;
export type DirectoryGroup = ApiSchema<'GroupResponse'>;
export type DirectoryKind = 'people' | 'groups';
export type DirectoryOption = {
  id: string;
  display_name: string;
  email: string;
};

export async function listDirectoryOptions(
  token: string,
  kind: DirectoryKind,
  {
    query = '',
    page = 1,
    ids,
    signal,
  }: {
    query?: string;
    page?: number;
    ids?: readonly string[];
    signal?: AbortSignal;
  } = {},
): Promise<{ items: DirectoryOption[]; total: number }> {
  const params = new URLSearchParams({
    q: query,
    page: String(page),
    page_size: ids ? '200' : '50',
  });
  ids?.forEach((id) => params.append('ids', id));
  if (kind === 'people') {
    const response = await apiFetchJson<
      ApiSchema<'CompanyDirectoryPeopleResponse'>
    >(`/api/v1/directory/people?${params}`, token, { signal });
    return {
      items: response.items.map((person) => ({
        id: person.id,
        display_name: person.display_name,
        email: '',
      })),
      total: response.total,
    };
  }
  const response = await apiFetchJson<ApiSchema<'GroupListResponse'>>(
    `/api/v1/directory/groups?${params}`,
    token,
    { signal },
  );
  return {
    items: response.items.map((group) => ({
      id: group.id,
      display_name: group.name,
      email: '',
    })),
    total: response.total,
  };
}
