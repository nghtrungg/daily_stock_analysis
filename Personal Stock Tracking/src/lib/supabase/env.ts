export type SupabasePublicEnvironment = {
  url: string;
  publishableKey: string;
};

export function getSupabasePublicEnvironment(): SupabasePublicEnvironment {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const publishableKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;

  if (!url || !publishableKey) {
    throw new Error('Supabase public configuration is missing.');
  }

  return { url, publishableKey };
}
