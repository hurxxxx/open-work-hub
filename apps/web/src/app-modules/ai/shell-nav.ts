import type { AppShellNavResolver } from '@/src/app/shell/navigation-types';

export const aiShellNavResolver: AppShellNavResolver = ({ pathname }) => {
  const workspaceAppMatch = /^\/w\/[^/]+\/([^/?#]+)/.exec(pathname);
  const workspaceAppId = workspaceAppMatch?.[1];
  if (
    workspaceAppId === 'chatbot' ||
    workspaceAppId === 'web-search' ||
    workspaceAppId === 'research-trends' ||
    workspaceAppId === 'standards-monitor'
  ) {
    return workspaceAppId;
  }
  if (pathname === '/qa-assistant') {
    return 'qa-assistant';
  }
  return null;
};
