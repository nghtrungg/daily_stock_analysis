import { Settings } from 'lucide-react';
import { UtilityPage } from '../../components/utility-page';
import { SignOutButton } from '../../features/auth/sign-out-button';
import { requireUser } from '../../lib/auth/require-user';

export default async function SettingsPage() {
  await requireUser();

  return (
    <UtilityPage
      activePath="/settings"
      eyebrow="Application preferences"
      title="Settings"
      description="Your data is protected by your account session and row-level security. Market data remains visibly unavailable until a trusted quote source is connected."
      marker={<Settings size={28} strokeWidth={1.5} />}
      emptyTitle="Secure portfolio workspace"
      emptyCopy="Your ledger and watchlist are stored privately. Quote freshness and language controls will arrive in later slices."
      action={<SignOutButton />}
    />
  );
}
