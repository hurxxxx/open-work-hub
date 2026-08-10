import { useAuth } from './auth-provider';
import { ProfilePageContent } from './ProfilePageContent';
import type { SettingsSection } from './settings-page-model';

export function ProfilePage({ initialTab }: { initialTab: SettingsSection }) {
  const auth = useAuth();
  const user = auth.user;

  if (!user) return null;

  return (
    <ProfilePageContent
      key={`${user.id}:${initialTab}`}
      auth={auth}
      initialTab={initialTab}
      user={user}
    />
  );
}
