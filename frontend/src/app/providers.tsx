import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
const client = new QueryClient({
  defaultOptions: { queries: { retry: 1 }, mutations: { retry: false } },
});
export function AppProviders({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
