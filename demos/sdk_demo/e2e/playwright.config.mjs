import { defineConfig } from '@playwright/test';

// Servers are started by hand (see docs/test/WEB.md); no webServer block.
export default defineConfig({
  testDir: '.',
  testMatch: /.*\.spec\.mjs/,
  workers: 1,
  timeout: 60_000,
  use: {
    baseURL: 'http://localhost:8078',
    viewport: { width: 1280, height: 800 },
  },
});
