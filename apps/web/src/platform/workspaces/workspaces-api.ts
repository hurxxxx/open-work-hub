import { useEffect, useState } from 'react';

import { ApiRequestError, apiFetchJson } from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';

export type WorkspaceBootstrapWorkspace = ApiSchema<'WorkspaceBootstrapWorkspaceResponse'>;

export type WorkspaceBootstrapNavItem = ApiSchema<'WorkspaceBootstrapNavItemResponse'> & {
  coming_soon?: boolean | null;
};

export type WorkspaceBootstrapApp = Omit<
  ApiSchema<'WorkspaceBootstrapAppResponse'>,
  'nav_items'
> & {
  nav_items: WorkspaceBootstrapNavItem[];
};

export type WorkspaceBootstrapResponse = Omit<
  ApiSchema<'WorkspaceBootstrapResponse'>,
  'apps' | 'nav' | 'workspace'
> & {
  workspace: WorkspaceBootstrapWorkspace;
  apps: WorkspaceBootstrapApp[];
  nav: WorkspaceBootstrapNavItem[];
  /**
   * Workspace app ids the chatbot has registered tools for, intersected with
   * this workspace's entitlements. Drives the chat scope picker — adding a
   * new MCP-bridged domain on the backend automatically extends this list,
   * so no frontend code change is needed to expose it.
   */
  chatbot_app_ids?: string[];
};

export async function getWorkspaceBootstrap(
  token: string,
  workspaceSlug: string,
): Promise<WorkspaceBootstrapResponse> {
  try {
    return await apiFetchJson<WorkspaceBootstrapResponse>(
      `/api/v1/workspaces/${encodeURIComponent(workspaceSlug)}/bootstrap`,
      token,
    );
  } catch (caughtError) {
    if (caughtError instanceof ApiRequestError) {
      throw new Error(
        caughtError.message || `워크스페이스 bootstrap 요청에 실패했습니다. (${caughtError.status})`,
      );
    }
    throw caughtError;
  }
}

export function useWorkspaceBootstrap(
  token: string | null,
  workspaceSlug: string | null | undefined,
) {
  const [data, setData] = useState<WorkspaceBootstrapResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!token || !workspaceSlug) {
      setData(null);
      setError(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    getWorkspaceBootstrap(token, workspaceSlug)
      .then((next) => {
        if (cancelled) {
          return;
        }
        setData(next);
        setError(null);
      })
      .catch((caughtError: unknown) => {
        if (cancelled) {
          return;
        }
        setData(null);
        setError(
          caughtError instanceof Error
            ? caughtError.message
            : '워크스페이스 bootstrap을 불러오지 못했습니다.',
        );
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [token, workspaceSlug]);

  return {
    data,
    error,
    loading,
  };
}
