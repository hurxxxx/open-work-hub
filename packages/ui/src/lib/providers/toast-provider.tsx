import * as ToastPrimitive from '@radix-ui/react-toast';
import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';

import { cn } from '../utils/cn';

type ToastTone = 'info' | 'success' | 'error';

type ToastRecord = {
  id: string;
  title: string;
  description?: string;
  tone: ToastTone;
};

type ToastApi = {
  info: (title: string, description?: string) => void;
  success: (title: string, description?: string) => void;
  error: (title: string, description?: string) => void;
};

const ToastContext = createContext<ToastApi | null>(null);

function toneClass(tone: ToastTone) {
  switch (tone) {
    case 'success':
      return 'border-transparent bg-[color-mix(in_oklab,var(--ui-color-success)_12%,white)] text-[var(--ui-color-success)]';
    case 'error':
      return 'border-transparent bg-[color-mix(in_oklab,var(--ui-color-danger)_14%,white)] text-[var(--ui-color-danger)]';
    default:
      return 'border-[var(--ui-color-border)] bg-[var(--ui-color-surface-raised)] text-[var(--ui-color-ink)]';
  }
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastRecord[]>([]);

  const api = useMemo<ToastApi>(() => {
    const push = (tone: ToastTone, title: string, description?: string) => {
      setToasts((current) => [
        ...current,
        {
          id: `${tone}-${Date.now()}-${current.length}`,
          title,
          description,
          tone,
        },
      ]);
    };

    return {
      info: (title, description) => push('info', title, description),
      success: (title, description) => push('success', title, description),
      error: (title, description) => push('error', title, description),
    };
  }, []);

  return (
    <ToastContext.Provider value={api}>
      <ToastPrimitive.Provider swipeDirection="right">
        {children}
        {toasts.map((toast) => (
          <ToastPrimitive.Root
            key={toast.id}
            className={cn(
              'grid gap-1 rounded-[var(--ui-radius-md)] border px-4 py-3 shadow-[var(--ui-shadow-lg)]',
              toneClass(toast.tone),
            )}
            duration={2800}
            onOpenChange={(open) => {
              if (!open) {
                setToasts((current) => current.filter((item) => item.id !== toast.id));
              }
            }}
            open
          >
            <ToastPrimitive.Title className="text-sm font-semibold">
              {toast.title}
            </ToastPrimitive.Title>
            {toast.description ? (
              <ToastPrimitive.Description className="text-sm">
                {toast.description}
              </ToastPrimitive.Description>
            ) : null}
          </ToastPrimitive.Root>
        ))}
      </ToastPrimitive.Provider>
    </ToastContext.Provider>
  );
}

export function ToastViewport() {
  return (
    <ToastPrimitive.Viewport className="fixed bottom-4 right-4 z-[var(--ui-z-toast)] grid w-[min(360px,calc(100vw-2rem))] gap-2 outline-none" />
  );
}

export function useToast() {
  const context = useContext(ToastContext);

  if (!context) {
    throw new Error('useToast must be used within ToastProvider');
  }

  return context;
}
