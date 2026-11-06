import { chromium } from 'playwright-core'
import { resolve } from 'node:path'

const browser = await chromium.launch({
  executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  headless: true,
  args: ['--no-sandbox', '--disable-gpu', '--disable-gpu-sandbox', '--disable-software-rasterizer'],
})

const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 })
const pageErrors = []
page.on('pageerror', (error) => pageErrors.push(error.message))

try {
  await page.goto(process.env.UI_URL || 'http://127.0.0.1:5178/', { waitUntil: 'networkidle' })
  await page.getByRole('button', { name: '载入演示样本' }).click()
  await page.getByRole('button', { name: '生成检查项' }).click()
  await page.getByRole('heading', { name: '检查清单' }).waitFor()
  const checkCount = await page.locator('.check-card').count()
  if (checkCount !== 10) throw new Error(`检查项数量错误：${checkCount}`)
  await page.getByRole('button', { name: '确认并开始审核' }).click()
  await page.getByRole('heading', { name: '审核结果' }).waitFor()
  await page.locator('.finding-row').filter({ hasText: 'R04' }).click()
  await page.getByText('投标总报价为150万元。', { exact: true }).waitFor()
  const [report] = await Promise.all([
    page.waitForEvent('popup'),
    page.getByRole('link', { name: '打开可打印报告' }).click(),
  ])
  await report.waitForLoadState()
  if (await report.locator('article').count() !== 10) throw new Error('报告缺少检查项')
  await report.screenshot({ path: resolve('../tmp/ui-report.png'), fullPage: true })
  await report.close()
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('link', { name: '下载结构化结果' }).click(),
  ])
  if (!download.suggestedFilename().endsWith('.json')) throw new Error('结构化报告下载失败')
  if (pageErrors.length) throw new Error(`页面错误：${pageErrors.join('; ')}`)
  await page.screenshot({ path: resolve('../tmp/ui-results.png'), fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)
  if (overflow) throw new Error('移动端页面出现横向溢出')
  await page.screenshot({ path: resolve('../tmp/ui-mobile.png'), fullPage: true })
  console.log(`界面流程通过：${checkCount} 条检查项，结果页已显示报价冲突。`)
} finally {
  await browser.close()
}
