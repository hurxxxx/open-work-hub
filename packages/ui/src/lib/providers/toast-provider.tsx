import * as ToastPrimitive from '@radix-ui/react-toast';
import { createContext, use, useMemo, useState, type ReactNode } from 'react';
import { X } from 'lucide-react';

import { cn } from '../utils/cn';
import {
  appendToastRecord,
  createToastRecord,
  dismissToastRecord,
  toastToneClass,
  type ToastRecord,
  type ToastTone,
} from './toast-state';

type ToastApi = {
  info: (title: string, description?: string) => void;
  success: (title: string, description?: string) => void;
  error: (title: string, description?: string) => void;
};

const ToastContext = createContext<ToastApi | null>(null);

export function ToastProvider({
  children,
  closeLabel,
}: {
  children: ReactNode;
  closeLabel: string;
}) {
  const [toasts, setToasts] = useState<ToastRecord[]>([]);

  const api = useMemo<ToastApi>(() => {
    const push = (tone: ToastTone, title: string, description?: string) => {
      setToasts((current) =>
        appendToastRecord(
          current,
          createToastRecord({
            description,
            id: `${tone}-${Date.now()}-${current.length}`,
            title,
            tone,
          }),
        ),
      );
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
              'relative grid gap-1 rounded-[var(--ui-radius-md)] border py-3 pl-4 pr-10 shadow-[var(--ui-shadow-lg)]',
              toastToneClass(toast.tone),
            )}
            duration={2800}
            onOpenChange={(open) => {
              if (!open) {
                setToasts((current) => dismissToastRecord(current, toast.id));
              }
            }}
            open
          >
            <ToastPrimitive.Title className="text-[length:var(--ui-text-body-sm)] font-semibold">
              {toast.title}
            </ToastPrimitive.Title>
            {toast.description ? (
              <ToastPrimitive.Description className="text-[length:var(--ui-text-body-sm)]">
                {toast.description}
              </ToastPrimitive.Description>
            ) : null}
            <ToastPrimitive.Close
              aria-label={closeLabel}
              className="absolute right-2 top-2 inline-flex size-7 items-center justify-center rounded-[var(--ui-radius-sm)] text-current/60 transition-colors hover:bg-black/5 hover:text-current focus:outline-none focus:ring-2 focus:ring-current/25 dark:hover:bg-white/10"
              title={closeLabel}
            >
              <X aria-hidden="true" size={15} strokeWidth={2.2} />
            </ToastPrimitive.Close>
          </ToastPrimitive.Root>
        ))}
      </ToastPrimitive.Provider>
    </ToastContext.Provider>
  );
}

export function ToastViewport() {
  return (
    <ToastPrimitive.Viewport className="fixed top-4 right-4 z-[var(--ui-z-toast)] grid w-[min(360px,calc(100vw-2rem))] gap-2 outline-none" />
  );
}

export function useToast() {
  const context = use(ToastContext);

  if (!context) {
    throw new Error('useToast must be used within ToastProvider');
  }

  return context;
}
