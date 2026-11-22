import { defineConfig } from 'vitest/config';
import path from 'path';

// Kept apart from vite.config.ts so unit tests of pure logic don't load the React / Tailwind plugins.
// Pure logic tests (*.test.ts) run in node; component tests (*.test.tsx) opt into jsdom with a
// `// @vitest-environment jsdom` comment at the top of the file.
export default defineConfig({
  resolve: {
    alias: {
      '@app': path.resolve(__dirname, 'src'),
    },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.{ts,tsx}'],
    setupFiles: ['src/test/setup.ts'],
  },
});
