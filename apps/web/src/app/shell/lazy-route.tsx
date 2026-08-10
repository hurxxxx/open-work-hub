import { Button } from '@open-alm/ui';
import {
  Component,
  Suspense,
  type ErrorInfo,
  type ReactElement,
  type ReactNode,
} from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation } from 'react-router-dom';
import { maybeReloadForStaleAssetLoadError } from '@/src/platform/deployment/stale-asset-reload';
import { LazyRouteFallback } from './lazy-route-fallback';

interface LazyRouteErrorBoundaryProps {
  children: ReactNode;
  recoverFromError?: (error: unknown) => boolean;
  resetKey?: string;
}

interface LazyRouteErrorBoundaryState {
  error: unknown | null;
}

function LazyRouteLoadErrorFallback() {
  const { t } = useTranslation('common');

  return (
    <div
      role="alert"
      className="flex h-full min-h-32 flex-col items-center justify-center gap-3 px-4 text-center"
    >
      <p className="text-sm text-app-ink/70">{t('feedback.routeLoadFailed')}</p>
      <Button onClick={() => window.location.reload()}>
        {t('actions.reload')}
      </Button>
    </div>
  );
}

class LazyRouteErrorBoundaryImpl extends Component<
  LazyRouteErrorBoundaryProps & {
    recoverFromError: (error: unknown) => boolean;
  },
  LazyRouteErrorBoundaryState
> {
  state: LazyRouteErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: unknown): LazyRouteErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: unknown, _errorInfo: ErrorInfo) {
    this.props.recoverFromError(error);
  }

  componentDidUpdate(
    previousProps: LazyRouteErrorBoundaryProps & {
      recoverFromError: (error: unknown) => boolean;
    },
  ) {
    if (
      this.state.error !== null &&
      previousProps.resetKey !== this.props.resetKey
    ) {
      this.setState({ error: null });
    }
  }

  render() {
    if (this.state.error !== null) {
      return <LazyRouteLoadErrorFallback />;
    }
    return this.props.children;
  }
}

export function LazyRouteErrorBoundary({
  children,
  recoverFromError = maybeReloadForStaleAssetLoadError,
  resetKey,
}: LazyRouteErrorBoundaryProps) {
  return (
    <LazyRouteErrorBoundaryImpl
      recoverFromError={recoverFromError}
      resetKey={resetKey}
    >
      {children}
    </LazyRouteErrorBoundaryImpl>
  );
}

function LocationAwareLazyRouteErrorBoundary({
  children,
}: {
  children: ReactNode;
}) {
  const location = useLocation();
  return (
    <LazyRouteErrorBoundary resetKey={location.key}>
      {children}
    </LazyRouteErrorBoundary>
  );
}

export function lazyRoute(element: ReactElement): ReactElement {
  return (
    <LocationAwareLazyRouteErrorBoundary key={element.key}>
      <Suspense fallback={<LazyRouteFallback />}>{element}</Suspense>
    </LocationAwareLazyRouteErrorBoundary>
  );
}
