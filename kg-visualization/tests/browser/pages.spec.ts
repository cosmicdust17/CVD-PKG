import { expect, test } from '@playwright/test'

test.skip(!process.env.HF_PAGES_URL, 'Requires an address serving the Pages production build')

test('Pages loads three source graphs and supports offline routes, expansion and simulation', async ({ page, request, baseURL }) => {
  const failed: string[] = []
  const apiCalls: string[] = []
  page.on('pageerror', error => failed.push(error.stack ?? error.message))
  page.on('response', response => {
    if (response.url().startsWith(baseURL!) && response.status() >= 400) failed.push(response.url())
  })
  page.on('request', req => {
    if (new URL(req.url()).pathname.includes('/api/')) apiCalls.push(req.url())
  })
  const root = new URL(baseURL!)
  for (const [file, expected] of [
    ['primary-prevention', 'D1'], ['cardiovascular-report-2024', 'D2'], ['healthy-lifestyle', 'D3'],
  ]) {
    const response = await request.get(new URL('data/sources/' + file + '.json', root).href)
    expect(response.ok()).toBe(true)
    const data = await response.json()
    expect(data.metadata.document_id).toBe(expected)
    expect(data.entities.length).toBeGreaterThan(0)
  }
  await page.goto(new URL('#graph', root).href)
  await page.reload()
  await expect(page.getByText(/在线演示模式/)).toBeVisible()
  await expect(page.getByRole('heading', { name: '知识图谱探索' })).toBeVisible()
  await expect(page.locator('.graph-surface canvas').first()).toBeVisible()
  await page.getByRole('searchbox', { name: '搜索实体' }).fill('教育程度低')
  await page.getByLabel('搜索结果').getByRole('button', { name: /低教育程度/ }).click()
  await page.getByRole('button', { name: '展开直接关联' }).click()
  await expect(page.getByLabel('当前画布统计')).toContainText('第 2 层')

  await page.goto(new URL('#detective?q=减盐', root).href)
  await expect(page.getByText(/AI 问答和 RAGFlow 文献检索服务未连接/)).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: 'AI 健康知识侦探' })).toBeVisible()
  await page.getByRole('searchbox', { name: '搜索图谱节点' }).fill('高血压')
  await page.getByRole('button', { name: '高血压', exact: true }).click()
  await expect(page.getByLabel('知识图谱', { exact: true }).getByRole('status').last()).not.toContainText('0 条关系')

  await page.goto(new URL('#simulator', root).href)
  await page.reload()
  await expect(page.getByRole('heading', { name: '健康生活方式模拟器' })).toBeVisible()
  await page.locator('#level-diet').fill('90')
  await expect(page.getByLabel('场景比较')).toContainText('90%')
  await expect(page.getByText(/仅调整场景 \d+ 条/)).toBeVisible()
  await page.getByText(/查看关联路径/).click()
  await expect(page.locator('.scenario-paths li').first()).toContainText(/高盐饮食|高钠膳食|高钠饮食/)
  await expect(page.getByText(/AI 解释、RAGFlow 文献检索及风险评分服务未连接/)).toBeVisible()
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.getByRole('heading', { name: '生活方式调节' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390)
  expect(apiCalls).toEqual([])
  expect(failed).toEqual([])
})
