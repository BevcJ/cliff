import { createClient, type SupabaseClient } from "@supabase/supabase-js";

import type { Database } from "./database.types";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const supabasePublishableKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY as string | undefined;

if (!supabaseUrl || !supabasePublishableKey) {
  throw new Error("Missing VITE_SUPABASE_URL or VITE_SUPABASE_PUBLISHABLE_KEY");
}

const configuredSupabaseUrl: string = supabaseUrl;
const configuredSupabasePublishableKey: string = supabasePublishableKey;

export const supabase = createClient<Database>(configuredSupabaseUrl, configuredSupabasePublishableKey, {
  auth: {
    autoRefreshToken: true,
    detectSessionInUrl: true,
    flowType: "pkce",
    persistSession: true,
  },
});

let passwordSetupClientSequence = 0;

// Each one-time link gets an isolated in-memory session that cannot be replaced
// by persisted sessions, another tab, or a concurrent password link.
export function createPasswordSetupClient(): SupabaseClient<Database> {
  passwordSetupClientSequence += 1;
  return createClient<Database>(configuredSupabaseUrl, configuredSupabasePublishableKey, {
    auth: {
      autoRefreshToken: false,
      detectSessionInUrl: false,
      flowType: "pkce",
      persistSession: false,
      storageKey: `ai-hiring-radar-password-setup-${passwordSetupClientSequence}`,
    },
  });
}
