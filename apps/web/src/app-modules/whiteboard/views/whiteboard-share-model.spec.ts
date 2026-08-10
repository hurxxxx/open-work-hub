import { describe, expect, it } from 'vitest';

import type {
  ShareableUserItem,
  WhiteboardSharingResponse,
} from '../api/whiteboard-api';
import { buildWhiteboardSharePresenter } from './whiteboard-share-model';

function user(id: string, fullName: string): ShareableUserItem {
  return {
    id,
    email: `${id}@open-work-hub.local`,
    full_name: fullName,
  } as ShareableUserItem;
}

function sharing(): WhiteboardSharingResponse {
  return {
    link_share: {
      access_level: 'read',
      share_path: '/whiteboard/shared/share-token',
    },
    users: [
      {
        access_level: 'edit',
        user_id: 'user-2',
      },
    ],
  } as WhiteboardSharingResponse;
}

describe('whiteboard share model', () => {
  it('builds a same-origin link url and stable user rows', () => {
    const presenter = buildWhiteboardSharePresenter({
      origin: 'https://app.open-work-hub.local',
      sharing: sharing(),
      users: [user('user-1', 'Ada Lovelace'), user('user-2', 'Grace Hopper')],
    });

    expect(presenter.linkUrl).toBe(
      'https://app.open-work-hub.local/whiteboard/shared/share-token',
    );
    expect(presenter.userRows.map((row) => row.user.id)).toEqual([
      'user-1',
      'user-2',
    ]);
    expect(presenter.userRows[0]).toMatchObject({
      currentShare: null,
      shared: false,
    });
    expect(presenter.userRows[1]).toMatchObject({
      currentShare: { access_level: 'edit', user_id: 'user-2' },
      shared: true,
    });
  });

  it('returns empty sharing state before the response loads', () => {
    const presenter = buildWhiteboardSharePresenter({
      origin: 'https://app.open-work-hub.local',
      sharing: null,
      users: [user('user-1', 'Ada Lovelace')],
    });

    expect(presenter.linkUrl).toBe('');
    expect(presenter.userRows).toEqual([
      {
        user: user('user-1', 'Ada Lovelace'),
        currentShare: null,
        shared: false,
      },
    ]);
  });
});
