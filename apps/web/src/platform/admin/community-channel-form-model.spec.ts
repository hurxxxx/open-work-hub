import { describe, expect, it } from 'vitest';

import {
  buildCommunityChannelPayload,
  normalizeCommunityChannelKey,
  sanitizeCommunityChannelKeyInput,
} from './community-channel-form-model';

describe('community channel form model', () => {
  it('normalizes display-like keys into stable channel slugs', () => {
    expect(normalizeCommunityChannelKey('Q&A')).toBe('q-a');
    expect(normalizeCommunityChannelKey(' Team  News! ')).toBe('team-news');
    expect(normalizeCommunityChannelKey('release---notes')).toBe(
      'release-notes',
    );
  });

  it('keeps editable hyphen states while typing channel keys', () => {
    expect(sanitizeCommunityChannelKeyInput('release-')).toBe('release-');
    expect(sanitizeCommunityChannelKeyInput('Q&A-')).toBe('q-a-');
    expect(sanitizeCommunityChannelKeyInput('release---notes')).toBe(
      'release-notes',
    );
  });

  it('builds API payloads with normalized keys', () => {
    expect(
      buildCommunityChannelPayload({
        active: true,
        adminOnlyContent: false,
        description: '',
        forceAnonymous: true,
        key: 'Q&A',
        name: 'Q&A',
        position: '2',
        readOnly: true,
        templateBody: '  Body template  ',
        templateTitle: '  Title template  ',
      }),
    ).toEqual({
      active: true,
      adminOnlyContent: false,
      description: '',
      forceAnonymous: true,
      key: 'q-a',
      name: 'Q&A',
      position: 2,
      readOnly: true,
      templateBody: 'Body template',
      templateTitle: 'Title template',
    });
  });

  it('rejects drafts that cannot produce a valid stable key', () => {
    expect(
      buildCommunityChannelPayload({
        active: true,
        adminOnlyContent: false,
        description: '',
        forceAnonymous: false,
        key: '',
        name: '공지사항',
        position: '2',
        readOnly: false,
        templateBody: '',
        templateTitle: '',
      }),
    ).toBeNull();
  });
});
