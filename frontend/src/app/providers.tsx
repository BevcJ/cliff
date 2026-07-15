import { QueryClientProvider } from "@tanstack/react-query";

import { AuthProvider } from "../features/auth/auth-provider";
import { queryClient } from "../lib/query-client";

export function AppProviders({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>{children}</AuthProvider>
    </QueryClientProvider>
  );
}
