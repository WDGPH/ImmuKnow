import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 150_000,
  use: { baseURL: 'http://localhost:4173' },
  webServer: {
    command: 'npm run preview -- --host localhost --port 4173',
    url: 'http://localhost:4173/ImmuKnow/playground/proof.html',
    reuseExistingServer: false,
  },
});
