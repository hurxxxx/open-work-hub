import { describe, expect, it } from 'vitest';

import {
  DM_THREAD_NAVIGATION_INITIAL_STATE,
  dmThreadBottomScrollSnapshot,
  dmThreadScrollSnapshot,
  navigateDmThreadHistoryBack,
  navigateDmThreadHistoryForward,
  omitDmThreadRecordValue,
  pruneDmThreadRecordValues,
  pruneDmThreadNavigationHistory,
  setDmThreadRecordValue,
} from './dm-conversation-session-model';

describe('dm conversation session model', () => {
  it('moves backward and forward through selected thread history', () => {
    const selectedC2 = {
      back: ['c1'],
      forward: [],
    };
    const selectedC3 = {
      back: ['c1', 'c2'],
      forward: [],
    };

    const back = navigateDmThreadHistoryBack(selectedC3, 'c3');
    const forward = navigateDmThreadHistoryForward(back.history, back.threadId);

    expect(selectedC2.back).toEqual(['c1']);
    expect(back).toEqual({
      history: { back: ['c1'], forward: ['c3'] },
      threadId: 'c2',
    });
    expect(forward).toEqual({
      history: { back: ['c1', 'c2'], forward: [] },
      threadId: 'c3',
    });
  });

  it('prunes deleted threads from navigation history', () => {
    expect(
      pruneDmThreadNavigationHistory(
        {
          back: ['c1', 'deleted', 'c2'],
          forward: ['deleted', 'c3'],
        },
        new Set(['c1', 'c2', 'c3']),
      ),
    ).toEqual({
      back: ['c1', 'c2'],
      forward: ['c3'],
    });
  });

  it('captures bottom scroll state with a small threshold', () => {
    expect(
      dmThreadScrollSnapshot({
        clientHeight: 400,
        scrollHeight: 1000,
        scrollTop: 540,
      }).atBottom,
    ).toBe(true);
    expect(
      dmThreadScrollSnapshot({
        clientHeight: 400,
        scrollHeight: 1000,
        scrollTop: 300,
      }).atBottom,
    ).toBe(false);
  });

  it('creates an explicit bottom scroll snapshot for user-sent messages', () => {
    expect(
      dmThreadBottomScrollSnapshot({
        clientHeight: 400,
        scrollHeight: 900,
      }),
    ).toEqual({
      atBottom: true,
      clientHeight: 400,
      scrollHeight: 900,
      scrollTop: 900,
    });
  });

  it('keeps record values most-recent first and removes a thread value', () => {
    const record = setDmThreadRecordValue(
      setDmThreadRecordValue({ c1: 'old' }, 'c2', 'newer'),
      'c1',
      'latest',
    );

    expect(Object.keys(record)).toEqual(['c1', 'c2']);
    expect(record).toEqual({ c1: 'latest', c2: 'newer' });
    expect(omitDmThreadRecordValue(record, 'c1')).toEqual({ c2: 'newer' });
    expect(pruneDmThreadRecordValues(record, new Set(['c1']))).toEqual({
      c1: 'latest',
    });
    expect(DM_THREAD_NAVIGATION_INITIAL_STATE).toEqual({
      back: [],
      forward: [],
    });
  });
});
