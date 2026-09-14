import { useCallback, useSyncExternalStore, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

import type { AppSidebarConfig } from '@/src/app/shell/sidebar-types';

type SidebarHost = { element: HTMLDivElement; onNavigate?: () => void };
// Only DOM destinations live here. The route retains its controller and the
// list has one React owner, including when the mobile menu opens.
const hosts = new Map<HTMLDivElement, SidebarHost>();
const listeners = new Set<() => void>();
let currentHost: SidebarHost | null = null;
function publishHosts() {
  const available = [...hosts.values()];
  currentHost =
    available.find((host) => host.onNavigate) ?? available[0] ?? null;
  listeners.forEach((listener) => listener());
}
function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
function ChatbotSidebarHost({ onNavigate }: { onNavigate?: () => void }) {
  const attach = useCallback(
    (element: HTMLDivElement | null) => {
      if (!element) return;
      hosts.set(element, { element, onNavigate });
      publishHosts();
      return () => {
        hosts.delete(element);
        publishHosts();
      };
    },
    [onNavigate],
  );
  return <div ref={attach} data-chatbot-sidebar-host />;
}

export function ChatbotSidebarPortal({
  children,
}: {
  children: (onNavigate?: () => void) => ReactNode;
}) {
  const host = useSyncExternalStore(
    subscribe,
    () => currentHost,
    () => null,
  );
  return host ? createPortal(children(host.onNavigate), host.element) : null;
}

export const chatbotSidebarConfig: AppSidebarConfig = {
  beforeCategories: ({ canReadApp, onNavigate }) =>
    canReadApp ? <ChatbotSidebarHost onNavigate={onNavigate} /> : null,
};
