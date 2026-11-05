import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, renderHook, type RenderOptions } from '@testing-library/react';
import React from 'react';

/** A fresh client per test, with retries off so failures surface immediately. */
export const createTestQueryClient = () =>
  new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });

const wrapperFor =
  (client: QueryClient) =>
  ({ children }: { children: React.ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;

/** Renders inside a QueryClientProvider; returns the client so tests can inspect the cache. */
export const renderWithClient = (ui: React.ReactElement, options?: RenderOptions) => {
  const client = createTestQueryClient();
  return { client, ...render(ui, { wrapper: wrapperFor(client), ...options }) };
};

export const renderHookWithClient = <T,>(hook: () => T) => {
  const client = createTestQueryClient();
  return { client, ...renderHook(hook, { wrapper: wrapperFor(client) }) };
};
