import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';

import { useAuth as useAuthContext } from './auth-context';
import { PasswordChangeRequired } from './password-change-required';
import { AuthLoadingScreen } from './auth-loading-screen';

export function RequireAuth({ children }: { children: ReactNode }) {
  const auth = useAuthContext();
  const location = useLocation();

  if (auth.status === 'bootstrapping') {
    return <AuthLoadingScreen />;
  }

  if (auth.status !== 'authenticated') {
    return (
      <Navigate
        replace
        state={{
          from: `${location.pathname}${location.search}${location.hash}`,
        }}
        to="/login"
      />
    );
  }

  if (auth.user?.must_change_password) {
    return <PasswordChangeRequired key={auth.user.id} user={auth.user} />;
  }

  return children;
}
