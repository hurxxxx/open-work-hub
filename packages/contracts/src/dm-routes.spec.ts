import { describe, expect, it } from 'vitest';

import {
  DM_MAX_ATTACHMENT_BYTES,
  DM_ROUTE_ID_MAX_LENGTH,
  dmRoutes,
  isDmAttachmentUploadFileAllowed,
  isDmRouteId,
  normalizeDmLimit,
  resolveDmAttachmentUrl,
} from './dm-routes';

describe('DM route contract helpers', () => {
  it('builds route paths with shared segment and limit policy', () => {
    expect(dmRoutes.conversation('conversation-1')).toBe(
      '/api/v1/dm/conversations/conversation-1',
    );
    expect(dmRoutes.conversationParticipant('c1', 'u2')).toBe(
      '/api/v1/dm/conversations/c1/participants/u2',
    );
    expect(
      dmRoutes.listMessages('c1', {
        limit: 80,
        before: new Date('2026-05-20T01:02:03.000Z'),
      }),
    ).toBe(
      '/api/v1/dm/conversations/c1/messages?limit=80&before=2026-05-20T01%3A02%3A03.000Z',
    );
    expect(dmRoutes.messageAttachments('c1')).toBe(
      '/api/v1/dm/conversations/c1/attachments',
    );
    expect(dmRoutes.attachmentDownload('attachment-1')).toBe(
      '/api/v1/dm/attachments/attachment-1/download',
    );
  });

  it('keeps route IDs as short URL path segments', () => {
    expect(isDmRouteId('a'.repeat(DM_ROUTE_ID_MAX_LENGTH))).toBe(true);
    expect(isDmRouteId('')).toBe(false);
    expect(isDmRouteId('a'.repeat(DM_ROUTE_ID_MAX_LENGTH + 1))).toBe(false);
    expect(isDmRouteId('space id')).toBe(false);
    expect(isDmRouteId('c/1')).toBe(false);
    expect(isDmRouteId('%2e')).toBe(false);
    expect(() => dmRoutes.messages('c/1')).toThrow('DM route id');
  });

  it('normalizes query limits within the API contract range', () => {
    expect(normalizeDmLimit(1)).toBe(1);
    expect(normalizeDmLimit(100)).toBe(100);
    expect(() => normalizeDmLimit(0)).toThrow(RangeError);
    expect(() => normalizeDmLimit(101)).toThrow(RangeError);
    expect(() => normalizeDmLimit(1.5)).toThrow(RangeError);
  });
});

describe('DM attachment policy helpers', () => {
  it('resolves only same-origin DM attachment URLs without fragments', () => {
    expect(
      resolveDmAttachmentUrl(
        '/api/v1/dm/attachments/a/content?expires=1&signature=s',
        'https://workspace.example.test',
      ),
    ).toBe(
      'https://workspace.example.test/api/v1/dm/attachments/a/content?expires=1&signature=s',
    );
    expect(
      resolveDmAttachmentUrl(
        'https://workspace.example.test/api/v1/dm/attachments/a/download',
        'https://workspace.example.test',
      ),
    ).toBe('https://workspace.example.test/api/v1/dm/attachments/a/download');
    expect(
      resolveDmAttachmentUrl(
        'https://cdn.example.test/api/v1/dm/attachments/a/download',
        'https://workspace.example.test',
      ),
    ).toBeNull();
    expect(
      resolveDmAttachmentUrl(
        'https://workspace.example.test/api/v1/dm/attachments/a/edit',
        'https://workspace.example.test',
      ),
    ).toBeNull();
    expect(
      resolveDmAttachmentUrl(
        '/api/v1/dm/attachments/a/preview#fragment',
        'https://workspace.example.test',
      ),
    ).toBeNull();
  });

  it('exposes the attachment upload size contract', () => {
    expect(DM_MAX_ATTACHMENT_BYTES).toBe(50 * 1024 * 1024);
    expect(isDmAttachmentUploadFileAllowed({ size: 0 })).toBe(true);
    expect(
      isDmAttachmentUploadFileAllowed({ size: DM_MAX_ATTACHMENT_BYTES }),
    ).toBe(true);
    expect(
      isDmAttachmentUploadFileAllowed({ size: DM_MAX_ATTACHMENT_BYTES + 1 }),
    ).toBe(false);
    expect(isDmAttachmentUploadFileAllowed({ size: -1 })).toBe(false);
    expect(
      isDmAttachmentUploadFileAllowed({ size: Number.POSITIVE_INFINITY }),
    ).toBe(false);
  });
});
