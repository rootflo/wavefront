import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react-swc';
import tailwindcss from '@tailwindcss/vite';
import { federation } from '@module-federation/vite';
import path from 'path';
import pkg from './package.json';

/**
 * Libraries the console and every remote extension must share a single copy of:
 * React (hooks break across copies), the router and query client (remotes use
 * the console's), zustand, and the UI kit (one theme, one set of portals).
 * `@wavefront/ui/` is a prefix share, covering every `@wavefront/ui/<component>`.
 */
const singleton = (requiredVersion?: string) => ({ singleton: true, requiredVersion });
const deps = pkg.dependencies as Record<string, string>;
const shared = {
  react: singleton(deps['react']),
  'react/jsx-runtime': singleton(deps['react']),
  'react-dom': singleton(deps['react-dom']),
  'react-router': singleton(deps['react-router']),
  '@tanstack/react-query': singleton(deps['@tanstack/react-query']),
  zustand: singleton(deps['zustand']),
  '@wavefront/ui/': singleton(),
};

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    // Module federation host. Remotes are not listed here: the console asks the
    // API which to load at runtime (src/extensions), so with none configured it
    // loads nothing and runs as before.
    federation({
      name: 'wavefront_console',
      remotes: {},
      shared,
      dts: false,
    }),
  ],
  resolve: {
    alias: {
      '@app': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
  },
  build: {
    // The federation runtime relies on top-level await.
    target: 'esnext',
  },
});
