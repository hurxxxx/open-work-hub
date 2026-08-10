import { apiFetchJson } from '@/src/platform/api/client';

export type UsageEventPayload = {
  app_id: string;
  event_type: 'app.open' | 'content.view' | 'content.create' | 'content.register' | 'search.query';
  workspace_id?: string | null;
  content_kind?: string | null;
  content_id?: string | null;
  content_title?: string | null;
  route_path?: string | null;
  source?: string | null;
  metadata?: Record<string, unknown> | null;
  dedupe_minutes?: number;
};

export async function recordUsageEvent(
  token: string,
  payload: UsageEventPayload,
): Promise<void> {
  await apiFetchJson<{ ok: boolean }>('/api/v1/usage/events', token, {
    body: JSON.stringify(payload),
    method: 'POST',
  });
}
