import { test, type Page } from '@playwright/test'
import path from 'path'
import { mockPortal } from './fixtures'

// ---------------------------------------------------------------------------
// Portal screenshot capture. Runs under both viewport projects (mobile 390x844
// / desktop 1440x900), so each spec yields a `<name>-<project>.png` pair. The
// backend is fully mocked (see fixtures.ts) — pages render populated.
// ---------------------------------------------------------------------------

const SHOTS_DIR = path.resolve(__dirname, '../../docs/screenshots')

async function capture(page: Page, slug: string, projectName: string) {
  await page.screenshot({
    path: path.join(SHOTS_DIR, `${slug}-${projectName}.png`),
    fullPage: true,
  })
}

async function settle(page: Page) {
  // The portal shells always render the "Tổng quan" nav label once mounted.
  await page.getByText('Tổng quan').first().waitFor({ state: 'visible' })
  // Let async data + fonts paint before the shot.
  await page.waitForTimeout(1200)
}

test.describe('Doctor portal', () => {
  test('doctor dashboard', async ({ page }, testInfo) => {
    await mockPortal(page, 'doctor')
    await page.goto('/doctor/dashboard', { waitUntil: 'domcontentloaded' })
    await settle(page)
    await capture(page, 'doctor-dashboard', testInfo.project.name)
  })

  test('doctor consultation workspace', async ({ page }, testInfo) => {
    await mockPortal(page, 'doctor')
    await page.goto('/doctor/consultations/c-1001', { waitUntil: 'domcontentloaded' })
    await settle(page)
    await capture(page, 'doctor-consultation-workspace', testInfo.project.name)
  })
})

test.describe('Admin portal', () => {
  test('admin overview', async ({ page }, testInfo) => {
    await mockPortal(page, 'internal_admin')
    await page.goto('/admin/dashboard', { waitUntil: 'domcontentloaded' })
    await settle(page)
    await capture(page, 'admin-overview', testInfo.project.name)
  })

  test('admin consultation monitoring', async ({ page }, testInfo) => {
    await mockPortal(page, 'internal_admin')
    await page.goto('/admin/consultations', { waitUntil: 'domcontentloaded' })
    await settle(page)
    await capture(page, 'admin-consultations', testInfo.project.name)
  })
})
