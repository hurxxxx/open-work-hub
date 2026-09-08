import type {
  DmConversationParticipant,
  DmMessageAttachment,
  DmUser,
} from '@open-work-hub/contracts/dm';

const CREATED_AT = '2026-05-20T00:00:00.000Z';

export function dmUserFixture(overrides: Partial<DmUser> = {}): DmUser {
  return {
    id: 'u1',
    email: 'user@example.test',
    full_name: 'Ada Lovelace',
    display_name: '',
    ...overrides,
  };
}

export function dmParticipantFixture(
  user: DmUser,
  role: DmConversationParticipant['role'] = 'member',
): DmConversationParticipant {
  return {
    user,
    role,
    joined_at: CREATED_AT,
    left_at: null,
    muted_at: null,
    last_read_message_id: null,
  };
}

export function dmAttachmentFixture(
  overrides: Partial<DmMessageAttachment> = {},
): DmMessageAttachment {
  return {
    id: 'attachment-1',
    conversation_id: 'c1',
    message_id: null,
    filename: 'screen.png',
    content_type: 'image/png',
    size_bytes: 1024,
    is_image: true,
    created_at: CREATED_AT,
    ...overrides,
  };
}
