import { redirect } from 'next/navigation';
import { createSupabaseServerClient } from '../supabase/server';

export async function requireUser() {
  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase.auth.getClaims();
  const claims = data?.claims;

  if (error || !claims?.sub) {
    redirect('/login');
  }

  return claims;
}
