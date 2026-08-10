import { apiFetchJson } from '@/src/platform/api/client';

export interface ReleaseNoteItem {
  id: string;
  release_key: string;
  title: string;
  summary: string;
  body: string;
  published_at: string;
  dismissed_at: string | null;
}

export interface CurrentReleaseNoteResponse {
  item: ReleaseNoteItem | null;
}

export interface ReleaseNotesResponse {
  items: ReleaseNoteItem[];
}

const RELEASE_NOTES_API_PREFIX = '/api/v1/release-notes';

export function getCurrentReleaseNote(
  token: string,
): Promise<CurrentReleaseNoteResponse> {
  return apiFetchJson<CurrentReleaseNoteResponse>(
    `${RELEASE_NOTES_API_PREFIX}/current`,
    token,
  );
}

export function listReleaseNotes(token: string): Promise<ReleaseNotesResponse> {
  return apiFetchJson<ReleaseNotesResponse>(RELEASE_NOTES_API_PREFIX, token);
}

export function dismissReleaseNote(
  token: string,
  releaseNoteId: string,
): Promise<ReleaseNoteItem> {
  return apiFetchJson<ReleaseNoteItem>(
    `${RELEASE_NOTES_API_PREFIX}/${releaseNoteId}/dismiss`,
    token,
    { method: 'POST' },
  );
}
