'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { createSupabaseBrowserClient } from '../../lib/supabase/client';

export function SignOutButton() {
  const [isPending, setIsPending] = useState(false);
  const router = useRouter();

  async function signOut() {
    setIsPending(true);
    await createSupabaseBrowserClient().auth.signOut();
    router.replace('/login');
    router.refresh();
  }

  return <button className="button button--secondary" disabled={isPending} onClick={() => void signOut()} type="button">{isPending ? 'Đang đăng xuất…' : 'Đăng xuất'}</button>;
}
