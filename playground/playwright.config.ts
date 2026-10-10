import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 150_000,
  use: { baseURL: 'http://localhost:4173' },
  webServer: {
    command: process.env.IMMUKNOW_SITE ? 'uv run python -m playground.scripts.serve-site' : 'npm run preview -- --host localhost --port 4173',
    cwd: process.env.IMMUKNOW_SITE ? '..' : '.',
    url: 'http://localhost:4173/ImmuKnow/playground/proof.html',
    reuseExistingServer: false,
  },
});
