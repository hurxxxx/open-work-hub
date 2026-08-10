import type {
  ShareableUserItem,
  WhiteboardSharingResponse,
  WhiteboardUserShareItem,
} from '../api/whiteboard-api';

export interface WhiteboardShareUserRow {
  user: ShareableUserItem;
  currentShare: WhiteboardUserShareItem | null;
  shared: boolean;
}

export interface WhiteboardSharePresenter {
  linkUrl: string;
  userRows: WhiteboardShareUserRow[];
}

export function buildWhiteboardSharePresenter(options: {
  sharing: WhiteboardSharingResponse | null;
  users: ShareableUserItem[];
  origin: string;
}): WhiteboardSharePresenter {
  const { sharing, users, origin } = options;
  const sharesByUserId = new Map(
    (sharing?.users ?? []).map((share) => [share.user_id, share]),
  );

  return {
    linkUrl: sharing?.link_share
      ? `${origin}${sharing.link_share.share_path}`
      : '',
    userRows: users.map((user) => {
      const currentShare = sharesByUserId.get(user.id) ?? null;
      return {
        user,
        currentShare,
        shared: currentShare !== null,
      };
    }),
  };
}
