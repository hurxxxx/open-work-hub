import { useCallback, useEffect, useMemo } from 'react';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { i18n } from '@/src/platform/i18n';
import { linkMedia, uploadMedia, resolveMediaUrls } from './media-api';
import { createMediaUrlResolutionSession } from './media-url-resolution-session';

export type MediaResourceType = 'task' | 'docs_native_page';

export interface MediaLinkTarget {
  resourceType: MediaResourceType;
  resourceId: string;
}

export function useMediaUpload() {
  const { token } = useAuth();
  const urlResolutionSession = useMemo(
    () => createMediaUrlResolutionSession({ resolveMediaUrls }),
    [token],
  );

  useEffect(() => () => urlResolutionSession.dispose(), [urlResolutionSession]);

  const uploadFile = useCallback(
    async (file: File): Promise<string> => {
      if (!token) throw new Error(i18n.t('auth:errors.noActiveSession'));
      const result = await uploadMedia(token, file);
      return result.url; // "media:{id}"
    },
    [token],
  );

  const createLinkedUploadFile = useCallback(
    (target: MediaLinkTarget | null | undefined) => {
      if (!token) return undefined;
      return async (file: File): Promise<string> => {
        const result = await uploadMedia(token, file);
        if (target?.resourceId) {
          await linkMedia(
            token,
            [result.id],
            target.resourceType,
            target.resourceId,
          ).catch(() => undefined);
        }
        return result.url;
      };
    },
    [token],
  );

  const resolveFileUrl = useCallback(
    (url: string): Promise<string> => {
      if (!token) return Promise.resolve(url);
      return urlResolutionSession.resolveFileUrl({ token, url });
    },
    [token, urlResolutionSession],
  );

  return {
    uploadFile: token ? uploadFile : undefined,
    createLinkedUploadFile: token ? createLinkedUploadFile : undefined,
    resolveFileUrl: token ? resolveFileUrl : undefined,
  };
}
