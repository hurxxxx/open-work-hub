import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { useTranslation } from 'react-i18next';
import {
  AUTH_REALTIME_EVENT_TYPES,
  isAuthAccessChangedRealtimeEvent,
} from '@open-work-hub/contracts/auth';

import type { AuthUser } from '@/src/platform/auth/auth-api';
import { useShellRealtime } from './shell-realtime-context';

type AccessRefreshInputs = {
  accessProjectionKey: string;
  refreshApps: () => Promise<unknown>;
  refreshUser: () => Promise<AuthUser>;
  refreshWorkspace: () => Promise<unknown>;
  workspaceSlug: string | null;
};

type AccessRefreshState =
  | { status: 'idle'; error: null }
  | { status: 'refreshing'; error: null }
  | { status: 'error'; error: string };

const INITIAL_STATE: AccessRefreshState = { status: 'idle', error: null };

function belongsToWorkspace(user: AuthUser, workspaceSlug: string): boolean {
  return user.workspaces.some((workspace) => workspace.slug === workspaceSlug);
}

export function AccessRefreshBoundary({
  children,
  ...inputs
}: AccessRefreshInputs & { children: ReactNode }) {
  const { t } = useTranslation('shell');
  const { addEventListener, reconnectSeq } = useShellRealtime();
  const inputsRef = useRef(inputs);
  inputsRef.current = inputs;
  const translateRef = useRef(t);
  translateRef.current = t;
  const mountedRef = useRef(true);
  const dirtyRef = useRef(false);
  const runningRef = useRef<Promise<void> | null>(null);
  const retryButtonRef = useRef<HTMLButtonElement>(null);
  const [state, setState] = useState<AccessRefreshState>(INITIAL_STATE);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const requestRefresh = useCallback(() => {
    dirtyRef.current = true;
    if (runningRef.current) {
      return runningRef.current;
    }

    const run = async () => {
      if (mountedRef.current) {
        setState({ status: 'refreshing', error: null });
      }
      try {
        while (dirtyRef.current) {
          dirtyRef.current = false;
          const user = await inputsRef.current.refreshUser();
          await inputsRef.current.refreshApps();
          const latestInputs = inputsRef.current;
          if (
            latestInputs.workspaceSlug &&
            belongsToWorkspace(user, latestInputs.workspaceSlug)
          ) {
            await latestInputs.refreshWorkspace();
          }
        }
        if (mountedRef.current) {
          setState(INITIAL_STATE);
        }
      } catch (caughtError) {
        dirtyRef.current = false;
        if (mountedRef.current) {
          setState({
            status: 'error',
            error:
              caughtError instanceof Error
                ? caughtError.message
                : translateRef.current('accessRefresh.failedDescription'),
          });
        }
      } finally {
        runningRef.current = null;
      }
    };

    runningRef.current = run();
    return runningRef.current;
  }, []);

  useEffect(() => {
    return addEventListener(
      AUTH_REALTIME_EVENT_TYPES.accessChanged,
      (event) => {
        if (isAuthAccessChangedRealtimeEvent(event)) {
          void requestRefresh();
        }
      },
    );
  }, [addEventListener, requestRefresh]);

  useEffect(() => {
    if (reconnectSeq > 0) {
      void requestRefresh();
    }
  }, [reconnectSeq, requestRefresh]);

  useEffect(() => {
    if (state.status === 'error') {
      retryButtonRef.current?.focus();
    }
  }, [state.status]);

  const masksChildren = state.status !== 'idle';

  return (
    <>
      <div
        aria-hidden={masksChildren || undefined}
        className={masksChildren ? 'hidden' : 'contents'}
        inert={masksChildren || undefined}
        key={inputs.accessProjectionKey}
      >
        {children}
      </div>
      {state.status === 'refreshing' ? (
        <div
          aria-live="polite"
          className="flex h-screen items-center justify-center bg-app-bg p-6 text-app-ink"
          role="status"
        >
          <p className="app-text-body">{t('accessRefresh.loading')}</p>
        </div>
      ) : null}
      {state.status === 'error' ? (
        <div
          className="flex h-screen items-center justify-center bg-app-bg p-6 text-app-ink"
          role="alert"
        >
          <div className="w-full max-w-lg rounded-2xl border border-app-border bg-app-surface p-6">
            <h1 className="app-text-title-lg">
              {t('accessRefresh.failedTitle')}
            </h1>
            <p className="app-text-body mt-2 text-app-ink/60">
              {state.error || t('accessRefresh.failedDescription')}
            </p>
            <button
              className="app-text-body-sm mt-5 rounded-xl bg-app-accent px-4 py-2.5 font-semibold text-app-accent-fg"
              onClick={() => void requestRefresh()}
              ref={retryButtonRef}
              type="button"
            >
              {t('accessRefresh.retry')}
            </button>
          </div>
        </div>
      ) : null}
    </>
  );
}
