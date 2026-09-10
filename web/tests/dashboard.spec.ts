import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'
import type { Dataset } from '../src/data'

const data: Dataset = JSON.parse(readFileSync(new URL('../../data/exports/career.json', import.meta.url), 'utf8'))
const season = data.seasons.find(season => season.label === '2018/19')!
const league = data.competitions.find(competition => competition.name === 'EFL League Two')!
const haaland = data.players.find(player => player.name === 'Erling Braut Haaland')!
const shootout = data.matches.find(match => match.played_on === '2019-02-14')!
const nottsId = data.clubs.find(club => club.name === 'Notts County')!.id

test('overview preserves filters, preseason and mobile navigation', async ({ page, isMobile }, testInfo) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Career overview', exact: true })).toBeVisible()
  await expect(page.getByText('85 recorded matches', { exact: true })).toBeVisible()
  await page.getByRole('checkbox', { name: 'Include preseason' }).click()
  await expect(page.getByText('75 recorded matches', { exact: true })).toBeVisible()
  await expect(page.getByRole('checkbox', { name: 'Include preseason' })).not.toBeChecked()
  await page.getByRole('combobox', { name: 'Competition', exact: true }).selectOption(league.id)
  await expect(page.getByText('46 recorded matches', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('combobox', { name: 'Competition', exact: true })).toHaveValue(league.id)
  await page.getByRole('button', { name: 'Reset filters', exact: true }).click()
  if (isMobile) await page.getByRole('button', { name: 'Open navigation', exact: true }).click()
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Players', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Players', exact: true })).toBeVisible()
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Career overview', exact: true })).toBeVisible()
  await expect(page.locator('.recharts-surface').first()).toBeVisible()
  await expect(page.locator('.evidence-preview img')).toHaveJSProperty('naturalWidth', 1366)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('overview.png'), fullPage: true, animations: 'disabled' })
  expect(errors).toEqual([])
})

test('fixture search, score, player records and source evidence', async ({ page }, testInfo) => {
  await page.goto('/#/matches')
  await page.getByRole('textbox', { name: 'Search fixtures or opponents' }).fill('2019-02-14')
  await expect(page.locator('tbody tr')).toHaveCount(1)
  await page.locator('.fixture-link').click()
  await expect(page.locator('.match-score')).toContainText('4-3 on penalties')
  const count = data.player_matches.filter(row => row.match_id === shootout.id && row.club_id === nottsId).length
  await expect(page.locator('tbody tr')).toHaveCount(count)
  await page.locator('tbody .text-link').first().click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Passing', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Close dialog' }).click()
  await page.locator('.match-meta').getByRole('button', { name: 'View source screenshot' }).first().click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.locator('.source-full')).toHaveJSProperty('naturalWidth', 1366)
  await page.screenshot({ path: testInfo.outputPath('evidence.png'), animations: 'disabled' })
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('player totals and development remain distinct from match data', async ({ page }, testInfo) => {
  await page.goto(`/#/players/${haaland.id}?season=${season.id}`)
  await expect(page.getByRole('heading', { name: haaland.name, exact: true })).toBeVisible()
  await expect(page.locator('.kpi').filter({ hasText: 'Goals' }).locator('strong')).toContainText('23')
  await page.getByRole('tab', { name: 'Season totals' }).click()
  await expect(page.locator('tbody tr')).toHaveCount(6)
  const total = page.locator('tbody tr').filter({ hasText: 'All competitions' })
  await expect(total).toContainText('52')
  await expect(total).toContainText('23')
  await expect(total).toContainText('13')
  await page.getByRole('tab', { name: 'Development' }).click()
  await expect(page.getByRole('heading', { name: 'Recorded overall history' })).toBeVisible()
  await expect(page.locator('tbody').getByText('Season End', { exact: true })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('development.png'), fullPage: true, animations: 'disabled' })
  await page.getByRole('tab', { name: 'Player record' }).click()
  await expect(page.locator('.record-details')).toContainText(haaland.id)
})

test('competitions preserve League Two points and preseason editions', async ({ page }) => {
  await page.goto(`/#/competitions/${league.id}`)
  await expect(page.getByRole('heading', { name: league.name, exact: true })).toBeVisible()
  await expect(page.locator('.kpi').filter({ hasText: 'Points from results' }).locator('strong')).toHaveText('83')
  await page.goto('/#/competitions')
  await expect(page.locator('.competition-card')).toHaveCount(7)
  await expect(page.locator('.competition-card').filter({ hasText: 'Preseason' })).toHaveCount(2)
})

test('verification exposes partial comparisons and the goal warning', async ({ page }) => {
  await page.goto('/#/audit')
  await expect(page.getByRole('heading', { name: 'Verification', exact: true })).toBeVisible()
  await page.getByRole('textbox', { name: 'Search reconciliation records' }).fill('Aaron Ramsdale')
  await expect(page.locator('tbody tr')).toHaveCount(6)
  await expect(page.locator('tbody').getByText('Partial', { exact: true }).first()).toBeVisible()
  await page.locator('tbody .text-link').first().click()
  await expect(page.getByRole('dialog')).toContainText('raw_match_average')
  await page.keyboard.press('Escape')
  await page.getByRole('tab', { name: 'Warnings (1)' }).click()
  await expect(page.locator('.warning-record')).toContainText('Portsmouth')
  await page.getByRole('link', { name: 'Open match' }).click()
  await expect(page.locator('.notice.warning')).toContainText('Credited player goals: 2')
})

test('all exported tables and full UUID records can be inspected', async ({ page }) => {
  await page.goto('/#/data')
  await expect(page.getByRole('combobox', { name: 'Dataset table' })).toBeVisible()
  await expect(page.getByRole('combobox', { name: 'Dataset table' }).locator('option')).toHaveCount(15)
  await page.getByRole('combobox', { name: 'Dataset table' }).selectOption('players')
  await page.getByRole('textbox', { name: 'Search players', exact: true }).fill(haaland.id)
  await expect(page.locator('tbody tr')).toHaveCount(1)
  await page.locator('tbody .text-link').click()
  await expect(page.getByRole('dialog')).toContainText(haaland.id)
  await page.keyboard.press('Escape')
  await page.getByRole('combobox', { name: 'Dataset table' }).selectOption('player_matches')
  await expect(page.locator('.record-count')).toContainText('1,132')
  await expect(page.getByRole('columnheader', { name: 'Goals Conceded Basis' })).toBeAttached()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('career records and screenshot previews are accessible', async ({ page }) => {
  await page.goto('/#/career')
  await expect(page.locator('.transfer-record')).toHaveCount(2)
  await expect(page.locator('.transfer-record').filter({ hasText: 'Calvert-Lewin' })).toContainText('24 months')
  await page.getByRole('tab', { name: 'Honours & events (2)' }).click()
  await expect(page.locator('.event-record')).toHaveCount(2)
  await page.goto('/#/sources')
  await page.getByRole('textbox', { name: 'Search screenshots' }).fill('(1055)')
  await expect(page.locator('.source-tile')).toHaveCount(1)
  await expect(page.locator('.source-tile img')).toHaveJSProperty('naturalWidth', 1366)
  await page.locator('.source-tile').click()
  await expect(page.getByRole('dialog')).toContainText('Screenshot (1055).png')
})

test('download exports actual data and missing data can recover', async ({ page }) => {
  await page.route('**/data/career.json', route => route.fulfill({ status: 503, body: 'Unavailable' }))
  await page.goto('/')
  await expect(page.getByRole('alert')).toContainText('Career export not found')
  await page.unroute('**/data/career.json')
  await page.getByRole('button', { name: 'Retry' }).click()
  await expect(page.getByRole('heading', { name: 'Career overview', exact: true })).toBeVisible()
  const pending = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download complete data', exact: true }).click()
  const download = await pending
  expect(download.suggestedFilename()).toBe('notts-county-career.json')
  expect(await download.failure()).toBeNull()
})