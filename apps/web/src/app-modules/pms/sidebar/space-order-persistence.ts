import {
  getDocsItemPrimaryTargetSortOrder,
  updateDocTarget,
  type DocsHubItem,
} from '@/src/app-modules/docs/public-api';

import { reorderPmsTaskLists, type PmsTaskList } from '../api/pms-api';
import {
  isSpaceOrderDoc,
  type SpaceOrderSavePayload,
} from './space-order-editor-model';

export type SpaceOrderListChange = Pick<
  SpaceOrderSavePayload['lists'][number],
  'id' | 'folder_id' | 'sort_order'
>;

export type SpaceOrderDocChange = Pick<
  SpaceOrderSavePayload['docs'][number],
  'id' | 'sort_order'
>;

export interface SpaceOrderChanges {
  listChanges: SpaceOrderListChange[];
  docChanges: SpaceOrderDocChange[];
}

export function buildSpaceOrderChanges({
  spaceId,
  currentDocs,
  currentLists,
  payload,
}: {
  spaceId: string;
  currentDocs: DocsHubItem[];
  currentLists: PmsTaskList[];
  payload: SpaceOrderSavePayload;
}): SpaceOrderChanges {
  const currentListMap = new Map(
    currentLists
      .filter((list) => !list.archived)
      .map((list) => [list.id, list]),
  );
  const currentDocMap = new Map(
    currentDocs
      .filter((doc) => isSpaceOrderDoc(doc, spaceId))
      .map((doc) => [doc.id, doc]),
  );

  return {
    listChanges: payload.lists.flatMap((item) => {
      const current = currentListMap.get(item.id);
      if (
        !current ||
        ((current.folder_id ?? null) === item.folder_id &&
          current.sort_order === item.sort_order)
      ) {
        return [];
      }
      return [
        {
          id: item.id,
          folder_id: item.folder_id,
          sort_order: item.sort_order,
        },
      ];
    }),
    docChanges: payload.docs.flatMap((item) => {
      const current = currentDocMap.get(item.id);
      if (
        !current ||
        getDocsItemPrimaryTargetSortOrder(current) === item.sort_order
      ) {
        return [];
      }
      return [{ id: item.id, sort_order: item.sort_order }];
    }),
  };
}

export async function persistSpaceOrderChanges({
  changes,
  spaceId,
  token,
}: {
  changes: SpaceOrderChanges;
  spaceId: string;
  token: string;
}): Promise<void> {
  const { docChanges, listChanges } = changes;
  await Promise.all([
    listChanges.length > 0
      ? reorderPmsTaskLists(token, spaceId, { items: listChanges })
      : Promise.resolve(),
    docChanges.length > 0
      ? Promise.all(
          docChanges.map((item) =>
            updateDocTarget(token, item.id, {
              app: 'pms',
              type: 'space',
              id: spaceId,
              sort_order: item.sort_order,
            }),
          ),
        ).then(() => undefined)
      : Promise.resolve(),
  ]);
}
