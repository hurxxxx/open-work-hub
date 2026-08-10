import type { AdminCommunityChannelInput } from './admin-api';

export type CommunityChannelDraft = {
  active: boolean;
  description: string;
  readOnly: boolean;
  forceAnonymous: boolean;
  adminOnlyContent: boolean;
  key: string;
  name: string;
  position: string;
  templateBody: string;
  templateTitle: string;
};

export const COMMUNITY_CHANNEL_KEY_PATTERN = /^[a-z0-9][a-z0-9-]*$/;

export function sanitizeCommunityChannelKeyInput(value: string): string {
  return value
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9-]+/g, '-')
    .replace(/-{2,}/g, '-')
    .slice(0, 64);
}

export function normalizeCommunityChannelKey(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .replace(/-{2,}/g, '-')
    .slice(0, 64)
    .replace(/-+$/g, '');
}

export function buildCommunityChannelPayload(
  draft: CommunityChannelDraft,
): AdminCommunityChannelInput | null {
  const name = draft.name.trim();
  const key = normalizeCommunityChannelKey(draft.key || name);
  const position = Number.parseInt(draft.position, 10);
  if (
    !COMMUNITY_CHANNEL_KEY_PATTERN.test(key) ||
    !name ||
    !Number.isFinite(position) ||
    position < 0
  ) {
    return null;
  }
  return {
    active: draft.active,
    adminOnlyContent: draft.adminOnlyContent,
    description: draft.description.trim(),
    forceAnonymous: draft.forceAnonymous,
    key,
    name,
    position,
    readOnly: draft.readOnly,
    templateBody: draft.templateBody.trim(),
    templateTitle: draft.templateTitle.trim(),
  };
}
