import { beforeEach, describe, expect, it } from 'vitest';

import { i18n } from './i18n';

describe('i18n dynamic messages', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('ko-KR');
  });

  it('interpolates runtime values without leaking template tokens', async () => {
    await i18n.changeLanguage('en-US');

    const englishSearchLabel = i18n.t('apps:ai.search.openResult', {
      title: 'Quarterly spec',
    });
    const englishActionPrompt = i18n.t(
      'apps:meeting.insightChat.actionPrompt',
      {
        label: 'Send supplier memo',
        meetingTitle: 'Weekly Review',
      },
    );

    expect(englishSearchLabel).toBe('Open result: Quarterly spec');
    expect(englishActionPrompt).toContain('Weekly Review');
    expect(englishActionPrompt).toContain('Send supplier memo');
    expect(`${englishSearchLabel} ${englishActionPrompt}`).not.toContain('{{');

    await i18n.changeLanguage('ko-KR');

    const koreanSearchLabel = i18n.t('apps:ai.search.openResult', {
      title: '분기 규격서',
    });
    const koreanActionPrompt = i18n.t('apps:meeting.insightChat.actionPrompt', {
      label: '공급사 메모 발송',
      meetingTitle: '주간 리뷰',
    });

    expect(koreanSearchLabel).toBe('결과 열기: 분기 규격서');
    expect(koreanActionPrompt).toContain('주간 리뷰');
    expect(koreanActionPrompt).toContain('공급사 메모 발송');
    expect(`${koreanSearchLabel} ${koreanActionPrompt}`).not.toContain('{{');
  });

  it('applies English plural forms and Korean count messages', async () => {
    await i18n.changeLanguage('en-US');

    expect(i18n.t('apps:docs.documentCount', { count: 1 })).toBe('1 document');
    expect(i18n.t('apps:docs.documentCount', { count: 2 })).toBe('2 documents');
    expect(i18n.t('apps:learning.lessonCount', { count: 1 })).toBe('1 lesson');
    expect(i18n.t('apps:learning.lessonCount', { count: 3 })).toBe('3 lessons');

    await i18n.changeLanguage('ko-KR');

    expect(i18n.t('apps:docs.documentCount', { count: 1 })).toBe('1개 문서');
    expect(i18n.t('apps:docs.documentCount', { count: 2 })).toBe('2개 문서');
    expect(i18n.t('apps:learning.lessonCount', { count: 1 })).toBe('1개 레슨');
    expect(i18n.t('apps:learning.lessonCount', { count: 3 })).toBe('3개 레슨');
  });
});
