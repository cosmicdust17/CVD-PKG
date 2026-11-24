import { expect, test, type Page } from '@playwright/test'
import type { Graph } from '@antv/g6'

test.skip(!process.env.HF_TEST_API, 'Start the local health API and set HF_TEST_API=1')

async function renderedGraph(page: Page) {
  return page.locator('.graph-surface').evaluate(el => {
    const host = el as HTMLElement & { __vueParentComponent: { exposed: { testGraph: () => Graph } } }
    const graph = host.__vueParentComponent.exposed.testGraph()
    const nodes = graph.getNodeData()
    const edges = graph.getEdgeData()
    const zoom = graph.getZoom()
    const fontSizes = [...nodes, ...edges].map(item => Number(item.style?.labelFontSize) * zoom)
    return { nodes: nodes.length, edges: edges.length, zoom, smallestGraphText: Math.min(...fontSizes),
      first: nodes.length ? graph.getClientByCanvas(graph.getElementPosition(nodes[0].id)) : null }
  })
}

async function captureWorkspace(page: Page, path: string) {
  await page.evaluate(() => window.scrollTo(0, 0))
  const graph = (await page.getByRole('region', { name: '知识图谱' }).boundingBox())!
  await page.screenshot({ path, fullPage: true, animations: 'disabled', clip: {
    x: 0, y: 0, width: page.viewportSize()!.width, height: Math.ceil(graph.y + graph.height + 12),
  } })
}

async function setLevels(page: Page, values: Record<string, number>) {
  await page.evaluate(values => {
    for (const [field, value] of Object.entries(values)) {
      const input = document.getElementById('level-' + field) as HTMLInputElement
      input.value = String(value)
      input.dispatchEvent(new Event('input', { bubbles: true }))
    }
  }, values)
}

test('continuous sliders update, merge requests and restore exact saved positions', async ({ page }, testInfo) => {
  const calls: { body: { explain: boolean; lifestyle: object; compare_with: object }; time: number }[] = []
  page.on('request', request => {
    if (request.url().endsWith('/api/simulator/evaluate')) calls.push({ body: request.postDataJSON(), time: Date.now() })
  })
  await page.goto('/#simulator')
  const controls = page.getByRole('region', { name: '条件设置' })
  const compare = page.getByRole('region', { name: '场景比较' })
  const graph = page.getByRole('region', { name: '知识图谱' })
  const salt = controls.getByRole('slider', { name: '盐摄入程度' })
  await expect(controls.getByRole('slider')).toHaveCount(4)
  for (const slider of await controls.getByRole('slider').all()) await expect(slider).toHaveValue('50')
  await expect(controls.locator('select')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '开始模拟' })).toHaveCount(0)

  await salt.scrollIntoViewIfNeeded()
  const track = (await salt.boundingBox())!
  const y = track.y + track.height / 2
  await page.mouse.move(track.x + track.width / 2, y)
  await page.mouse.down()
  await page.mouse.move(track.x + 10 + (track.width - 20) * .78, y, { steps: 12 })
  await page.mouse.up()
  const dragged = Number(await salt.inputValue())
  expect(dragged).toBeGreaterThan(75)
  expect(dragged).toBeLessThan(81)
  await setLevels(page, { diet: 78, exercise: 23, sleep: 81, smoking: 30 })
  const changedAt = Date.now()
  const saltRow = compare.getByRole('row', { name: /饮食/ })
  await expect(saltRow.getByText('78%', { exact: true })).toBeVisible()
  await expect(saltRow.getByText('50%', { exact: true })).toBeVisible()
  expect(calls).toHaveLength(0)

  await expect(graph.getByText(/仅调整场景.*条/)).toBeVisible()
  await expect(page.getByRole('heading', { name: '文献中的预防方向' })).toBeVisible()
  await expect(page.getByText(/所选变化为/)).toBeVisible({ timeout: 25_000 })
  expect(calls.map(call => call.body)).toEqual([false, true].map(explain => ({
    explain, lifestyle: {}, compare_with: { diet: 'high', exercise: 'inactive', sleep: 'regular', smoking: 'current' },
  })))
  expect(calls[0].time - changedAt).toBeGreaterThanOrEqual(300)
  expect(calls[1].time - changedAt).toBeGreaterThanOrEqual(875)

  const [left, right, bottom] = await Promise.all([controls.boundingBox(), compare.boundingBox(), graph.boundingBox()])
  expect(right!.width).toBeGreaterThan(left!.width)
  expect(bottom!.y).toBeGreaterThan(Math.max(left!.y + left!.height, right!.y + right!.height))
  expect(bottom!.width).toBeGreaterThan(left!.width + right!.width)
  expect((await graph.locator('.health-canvas').boundingBox())!.height).toBeGreaterThanOrEqual(600)
  await expect.poll(async () => (await renderedGraph(page)).smallestGraphText).toBeGreaterThanOrEqual(10.999)
  await captureWorkspace(page, testInfo.outputPath('simulator-continuous-desktop.png'))

  const simulatorAnswer = page.locator('.simulator-page .ai-markdown')
  await expect(simulatorAnswer.getByRole('heading', { name: '场景对比' })).toBeVisible()
  const simulatorEvidence = page.getByRole('complementary', { name: '知识依据' })
  await expect(simulatorEvidence.locator('details[open]')).toHaveCount(0)
  await simulatorAnswer.getByRole('button', { name: /查看文献/ }).first().click()
  await expect(simulatorEvidence.locator('details[open] blockquote')).toBeVisible()
  await page.locator('.health-explanation').screenshot({ path: testInfo.outputPath('simulator-ai-markdown.png') })

  const zoom = (await renderedGraph(page)).zoom
  await graph.getByRole('button', { name: '缩小' }).click()
  await expect.poll(async () => (await renderedGraph(page)).zoom).toBeLessThan(zoom)
  const zoomed = (await renderedGraph(page)).zoom
  await salt.press('ArrowLeft')
  await expect(salt).toHaveAttribute('aria-valuetext', '77%，盐摄入偏多')
  await expect(saltRow.getByText('77%', { exact: true })).toBeVisible()
  await page.waitForTimeout(1100)
  expect(calls).toHaveLength(2)
  expect((await renderedGraph(page)).zoom).toBe(zoomed)

  await page.getByText('历史场景', { exact: true }).click()
  await page.getByLabel('场景名称').fill('连续滑块测试')
  await page.getByRole('button', { name: '保存场景' }).click()
  await expect(page.getByText('已保存场景。')).toBeVisible()
  await page.reload()
  await expect(salt).toHaveValue('50')
  await page.getByText('历史场景', { exact: true }).click()
  await page.getByRole('button', { name: '连续滑块测试', exact: true }).click()
  await expect(salt).toHaveValue('77')
  await expect(controls.getByRole('slider', { name: '日常活动程度' })).toHaveValue('23')

  const browser = await page.evaluate(() => JSON.parse(localStorage.getItem('hfkg:browser')!))
  const legacy = await page.request.post('/api/simulator/history', {
    headers: { 'X-HF-Browser-ID': browser },
    data: { title: '旧枚举记录', lifestyle: { diet: 'high' }, compare_with: { diet: 'reduced', sleep: 'irregular' } },
  })
  expect(legacy.status()).toBe(201)
  await page.reload()
  await page.getByText('历史场景', { exact: true }).click()
  await page.getByRole('button', { name: '旧枚举记录', exact: true }).click()
  await expect(salt).toHaveValue('0')
  await expect(controls.getByRole('slider', { name: '作息规律程度' })).toHaveValue('0')
  await expect(saltRow.getByText('50%', { exact: true })).toBeVisible()
  await expect(graph.getByText(/仅调整场景.*条/)).toBeVisible()
  await graph.getByRole('button', { name: '全图概览' }).click()
  await expect.poll(async () => (await renderedGraph(page)).nodes).toBeGreaterThan(100)
  await graph.getByRole('button', { name: '重置', exact: true }).click()
  await graph.getByRole('searchbox').fill('冠心病')
  await graph.getByRole('button', { name: '冠心病', exact: true }).click()
  await expect(graph.locator('.health-graph-detail')).toContainText('冠心病')

  await page.getByRole('link', { name: '为什么减少盐摄入有助于血压管理？' }).click()
  await expect(page.getByRole('heading', { name: 'AI 健康知识侦探' })).toBeVisible()
  const detectiveAnswer = page.locator('.conversation .ai-markdown').last()
  const detectiveEvidence = page.getByRole('complementary', { name: '知识依据' })
  await expect(detectiveAnswer.getByRole('heading').first()).toBeVisible({ timeout: 25_000 })
  await expect(detectiveEvidence.locator('details[open]')).toHaveCount(0)
  const citation = detectiveAnswer.getByRole('button', { name: /查看文献/ }).first()
  await expect(citation).toBeVisible()
  const number = await citation.getAttribute('data-citation')
  await citation.click()
  const citedCard = detectiveEvidence.locator('details[open]')
  await expect(citedCard.locator('.source-reference')).toHaveText('[' + number + ']')
  await expect(citedCard.getByText(/原始证据标识/)).toBeVisible()
  await page.getByText('历史对话', { exact: true }).click()
  await expect(page.locator('.conversation-history-item time')).toBeVisible()
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: testInfo.outputPath('detective-ai-markdown.png'), fullPage: true })

  await page.getByRole('link', { name: '试试生活方式模拟' }).click({ timeout: 25_000 })
  await expect(salt).toBeFocused()
  await expect(salt).toHaveValue('50')
  await salt.press('End')
  await page.getByRole('button', { name: '重置条件' }).click()
  for (const slider of await controls.getByRole('slider').all()) await expect(slider).toHaveValue('50')
  await page.setViewportSize({ width: 900, height: 850 })
  expect((await compare.boundingBox())!.x).toBeGreaterThan((await controls.boundingBox())!.x)
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(900)
})

test('late graph and AI replies cannot replace the current scenario', async ({ page }) => {
  let release!: () => void
  const delayed = new Promise<void>(resolve => { release = resolve })
  const held: boolean[] = []
  const delivered: boolean[] = []
  await page.route('**/api/simulator/evaluate', async route => {
    const body = route.request().postDataJSON()
    if (body.compare_with.diet === 'high') {
      held.push(body.explain)
      const response = await route.fetch()
      await delayed
      await route.fulfill({ response })
      delivered.push(body.explain)
    } else {
      await route.continue()
    }
  })
  try {
    await page.goto('/#simulator')
    await setLevels(page, { diet: 76 })
    await expect.poll(() => held.length).toBe(2)
    await setLevels(page, { diet: 50, sleep: 18 })
    const answer = page.locator('.simulator-page .health-answer')
    await expect(answer).toContainText('睡眠不足或作息不规律', { timeout: 25_000 })
    const result = page.getByRole('region', { name: '场景比较' })
    await expect(result.getByText('查看关联路径', { exact: false })).toBeVisible()
    const knowledge = await result.locator('.scenario-findings').innerText()
    const graph = await renderedGraph(page)
    release()
    await expect.poll(() => delivered.length).toBe(2)
    expect(await result.locator('.scenario-findings').innerText()).toBe(knowledge)
    expect((await renderedGraph(page)).nodes).toBe(graph.nodes)
    await expect(answer).toContainText('睡眠不足或作息不规律')
    await expect(answer).not.toContainText('高盐饮食')
  } finally {
    release()
  }
})

test('history restores rich answers while citations, HTML and missing pages stay safe', async ({ page }) => {
  await page.addInitScript(() => {
    const reply = {
      answer: '历史正文。',
      graph: { nodes: [], edges: [], paths: [], matched_entities: [], missing_entities: [] },
      evidence: [{
        id: 'stable:chunk', source: 'RAGFlow', document_name: '测试文献', page: null,
        quote: '参考原\n文 \n。下一段\n\n段落二。', chunk_id: 'chunk-test', relevance: null, node_ids: [], edge_ids: [],
      }],
      agent_trace: [], suggested_questions: [], topics: [],
    }
    const old = { id: 'old', title: '旧问题', turns: [{ question: '旧问题',
      reply: { ...reply, answer: '相关原文如下。\n\n「参考原文。下一段」[1]' } }] }
    const current = { id: 'new', title: '排版测试', updatedAt: '2026-11-24T05:25:00.000Z', turns: [{
      question: '排版测试', reply: { ...reply, answer_markdown:
        '## 分析结论\n\n这是 **重点**。[1] [99]\n\n- 一条建议\n\n| 条目 | 内容 |\n| --- | --- |\n| A | B |\n\n'
        + '\x60\x60\x60\n例子\n\x60\x60\x60\n\n<img src="https://example.invalid/example.jpg"> [不安全链接](javascript:alert%281%29)',
      },
    }] }
    localStorage.setItem('hfkg:conversations', JSON.stringify([current, old]))
  })
  await page.goto('/#detective')
  const answer = page.locator('.ai-markdown')
  await expect(answer.getByRole('heading', { name: '分析结论' })).toBeVisible()
  await expect(answer.locator('strong')).toHaveText('重点')
  await expect(answer.getByRole('listitem')).toHaveText('一条建议')
  await expect(answer.getByRole('table')).toBeVisible()
  await expect(answer.locator('pre code')).toContainText('例子')
  await expect(answer.locator('img, [href^="javascript:"]')).toHaveCount(0)
  await expect(answer.locator('[data-citation="99"]')).toHaveCount(0)
  const evidence = page.getByRole('complementary', { name: '知识依据' })
  await expect(evidence.locator('details[open]')).toHaveCount(0)
  await answer.getByRole('button', { name: '查看文献 1' }).click()
  await expect(evidence.locator('blockquote')).toHaveText('参考原文。下一段\n\n段落二。')
  await expect(evidence.getByText(/PDF 第/)).toHaveCount(0)
  await page.getByText('历史对话', { exact: true }).click()
  const history = page.locator('.conversation-history')
  await expect(history.getByText('更新时间未记录')).toBeVisible()
  await expect(history.getByText(/参考原文/)).toHaveCount(0)
  await history.getByRole('button', { name: /旧问题/ }).click()
  await expect(answer.getByRole('button', { name: '查看文献 1' })).toBeVisible()
  await expect(answer.getByText(/参考原文/)).toHaveCount(0)
})

test.describe('mobile touch', () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })

  test('touch drag, stacked layout and minimum text size', async ({ page, context }, testInfo) => {
    await page.goto('/#simulator')
    const slider = page.getByRole('slider', { name: '盐摄入程度' })
    await expect(slider).toHaveValue('50')
    await slider.scrollIntoViewIfNeeded()
    const track = (await slider.boundingBox())!
    const cdp = await context.newCDPSession(page)
    const touch = { x: track.x + track.width / 2, y: track.y + track.height / 2 }
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [touch] })
    for (let i = 1; i <= 8; i++) {
      await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove',
        touchPoints: [{ ...touch, x: touch.x + (track.width - 20) * .27 * i / 8 }] })
    }
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
    const level = Number(await slider.inputValue())
    expect(level).toBeGreaterThan(74)
    expect(level).toBeLessThan(80)
    await expect(page.getByRole('region', { name: '场景比较' }).getByText(level + '%', { exact: true })).toBeVisible()
    await expect.poll(async () => (await renderedGraph(page)).edges).toBeGreaterThan(0)
    const [controls, compare, graph] = await Promise.all(
      ['条件设置', '场景比较', '知识图谱'].map(name => page.getByRole('region', { name }).boundingBox()),
    )
    expect(compare!.y).toBeGreaterThan(controls!.y + controls!.height)
    expect(graph!.y).toBeGreaterThan(compare!.y + compare!.height)
    await expect.poll(async () => (await renderedGraph(page)).smallestGraphText).toBeGreaterThanOrEqual(10.999)
    await captureWorkspace(page, testInfo.outputPath('simulator-continuous-mobile.png'))
    for (const width of [390, 320]) {
      await page.setViewportSize({ width, height: 844 })
      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width)
    }
    const sizes = await page.locator('body').evaluate(el => [...el.querySelectorAll<HTMLElement>('*')]
      .filter(node => node.getClientRects().length && (node.matches('input, select, button') ||
        [...node.childNodes].some(child => child.nodeType === Node.TEXT_NODE && child.textContent?.trim())))
      .map(node => parseFloat(getComputedStyle(node).fontSize)))
    expect(Math.min(...sizes)).toBeGreaterThanOrEqual(11)
  })
})
