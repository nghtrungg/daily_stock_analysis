import { createBrowserClient } from '@supabase/ssr';
import { getSupabasePublicEnvironment } from './env';

let browserClient: ReturnType<typeof createBrowserClient> | undefined;

export function createSupabaseBrowserClient() {
  if (!browserClient) {
    const { url, publishableKey } = getSupabasePublicEnvironment();
    browserClient = createBrowserClient(url, publishableKey);
  }

  return browserClient;
}
