import { useEffect, useState } from 'react';


export interface WorkspaceBootstrapWorkspace {
  id: string;
  slug: string;
  name: string;
  role: string;
}

export interface WorkspaceBootstrapNavItem {
  id: string;
  app_id: string;
  title: string;
  category: string;
  icon_key: string;
  link_app_id?: string | null;
  path_suffix?: string | null;
  absolute_path?: string | null;
  coming_soon?: boolean | null;
}

export interface WorkspaceBootstrapApp {
  app_id: string;
  title: string;
  route_base: string;
  icon_key: string;
  enabled: boolean;
  nav_items: WorkspaceBootstrapNavItem[];
}

export interface WorkspaceBootstrapResponse {
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
}

export async function getWorkspaceBootstrap(
  token: string,
  workspaceSlug: string,
): Promise<WorkspaceBootstrapResponse> {
  const response = await fetch(
    `/api/v1/workspaces/${encodeURIComponent(workspaceSlug)}/bootstrap`,
    {
      cache: 'no-store',
      headers: {
        Accept: 'application/json',
        Authorization: `Bearer ${token}`,
      },
    },
  );

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = (
      payload
      && typeof payload === 'object'
      && 'detail' in payload
      && typeof payload.detail === 'string'
    )
      ? payload.detail
      : `워크스페이스 bootstrap 요청에 실패했습니다. (${response.status})`;
    throw new Error(detail);
  }

  return payload as WorkspaceBootstrapResponse;
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
