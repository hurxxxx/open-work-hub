import { useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';

import { useAuth as useAuthContext } from './auth-context';
import { AuthLoadingScreen } from './auth-loading-screen';
import { consumePostLogoutHomeRedirect } from './auth-storage';
import { LoginScreen } from './login-screen';

function sanitizeRedirectTarget(state: unknown, fallback = '/'): string {
  if (
    state &&
    typeof state === 'object' &&
    'from' in state &&
    typeof state.from === 'string' &&
    state.from.startsWith('/') &&
    state.from !== '/login'
  ) {
    return state.from;
  }

  return fallback;
}

export function LoginRoute() {
  const auth = useAuthContext();
  const location = useLocation();
  const [redirectToHomeAfterLogout] = useState(() =>
    consumePostLogoutHomeRedirect(),
  );

  if (auth.status === 'bootstrapping') {
    return <AuthLoadingScreen />;
  }

  if (auth.status === 'authenticated') {
    return (
      <Navigate
        replace
        to={
          redirectToHomeAfterLogout
            ? '/'
            : sanitizeRedirectTarget(location.state)
        }
      />
    );
  }

  return <LoginScreen />;
}
