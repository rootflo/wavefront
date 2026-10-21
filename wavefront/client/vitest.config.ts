import { defineConfig } from 'vitest/config';
import path from 'path';

// Kept apart from vite.config.ts so unit tests of pure logic don't load the React / Tailwind plugins
export default defineConfig({
  resolve: {
    alias: {
      '@app': path.resolve(__dirname, 'src'),
    },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
});
