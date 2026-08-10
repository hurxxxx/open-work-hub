import { apiFetchJson } from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';

export type PersonalTodoItem = ApiSchema<'PersonalTodoItemOut'>;
export type PersonalTodoListResponse = ApiSchema<'PersonalTodoListResponse'>;
export type PersonalMemo = ApiSchema<'PersonalMemoOut'>;

export function listPersonalTodos(
  token: string,
  includeCompleted = true,
): Promise<PersonalTodoListResponse> {
  const query = new URLSearchParams({
    include_completed: includeCompleted ? 'true' : 'false',
  });
  return apiFetchJson<PersonalTodoListResponse>(
    `/api/v1/personal-widgets/todos?${query.toString()}`,
    token,
  );
}

export function createPersonalTodo(
  token: string,
  title: string,
): Promise<PersonalTodoItem> {
  return apiFetchJson<PersonalTodoItem>(
    '/api/v1/personal-widgets/todos',
    token,
    {
      body: JSON.stringify({ title }),
      method: 'POST',
    },
  );
}

export function updatePersonalTodo(
  token: string,
  todoId: string,
  payload: { completed?: boolean; title?: string },
): Promise<PersonalTodoItem> {
  return apiFetchJson<PersonalTodoItem>(
    `/api/v1/personal-widgets/todos/${encodeURIComponent(todoId)}`,
    token,
    {
      body: JSON.stringify(payload),
      method: 'PATCH',
    },
  );
}

export function deletePersonalTodo(token: string, todoId: string): Promise<void> {
  return apiFetchJson<void>(
    `/api/v1/personal-widgets/todos/${encodeURIComponent(todoId)}`,
    token,
    { method: 'DELETE' },
  );
}

export function getPersonalMemo(token: string): Promise<PersonalMemo> {
  return apiFetchJson<PersonalMemo>('/api/v1/personal-widgets/memo', token);
}

export function savePersonalMemo(
  token: string,
  body: string,
): Promise<PersonalMemo> {
  return apiFetchJson<PersonalMemo>(
    '/api/v1/personal-widgets/memo',
    token,
    {
      body: JSON.stringify({ body }),
      method: 'PUT',
    },
  );
}
