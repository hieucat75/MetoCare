import { defineConfig } from '@playwright/test'

/**
 * Playwright config for the doctor + admin portal screenshot capture.
 *
 * The backend is fully MOCKED at the network layer (see e2e/fixtures.ts) — no
 * live API is required. A local Next dev server is booted on port 3099 and the
 * same specs run under two viewport projects (mobile 390x844 / desktop
 * 1440x900) to produce the responsive shots.
 *
 * Run:  npx playwright test         (both viewports)
 *       npx playwright test --project=mobile
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 90_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:3199',
    actionTimeout: 20_000,
    navigationTimeout: 60_000,
  },
  projects: [
    {
      name: 'mobile',
      use: { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 },
    },
    {
      name: 'desktop',
      use: { viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 },
    },
  ],
  webServer: {
    // A dedicated port (3199) so capture never collides with a dev server the
    // developer may already be running on the default 3099. `npm run dev` hard-
    // codes 3099, so we invoke next directly with the isolated port.
    command: 'npx next dev --turbo --port 3199',
    url: 'http://localhost:3199',
    timeout: 120_000,
    reuseExistingServer: !process.env.CI,
  },
})
