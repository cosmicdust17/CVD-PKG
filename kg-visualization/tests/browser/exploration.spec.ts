import { expect, test, type Page } from '@playwright/test'
import type { Graph } from '@antv/g6'
import { readFileSync } from 'node:fs'
import type { KnowledgeGraph } from '../../src/types/graph'

const data: KnowledgeGraph = JSON.parse(readFileSync(new URL('../../public/data/graph-data.json', import.meta.url), 'utf8'))

const byName = (name: string) => data.nodes.find(node => node.name === name)!
const root = byName('冠心病')
const searchRoot = byName('低教育程度')
const child = byName('心血管病')

async function graphInfo(page: Page, id: string) {
  return page.locator('.graph-surface').evaluate((el, id) => {
    const host = el as HTMLElement & {
      __vueParentComponent: { exposed: { testGraph: () => Graph } }
    }
    const graph = host.__vueParentComponent.exposed.testGraph()
    const point = graph.hasNode(id) ? graph.getElementPosition(id) : null
    return {
      point,
      viewportPoint: point && graph.getClientByCanvas(point),
      nodes: graph.getNodeData().map(n => n.id),
      edges: graph.getEdgeData().map(e => e.id),
      zoom: graph.getZoom(),
    }
  }, id)
}

async function clickNode(page: Page, id: string) {
  await expect.poll(async () => (await graphInfo(page, id)).nodes.includes(id)).toBe(true)
  await page.waitForTimeout(200)
  const [x, y] = (await graphInfo(page, id)).viewportPoint!
  await page.mouse.click(x, y)
}

test('真实画布逐层探索、搜索、证据和概览', async ({ page }, testInfo) => {
  const errors: string[] = []
  page.on('pageerror', err => errors.push(err.message))
  page.on('console', msg => {
    if (msg.type() === 'error') errors.push(msg.text())
  })
  await page.goto('/')
  const counts = page.getByLabel('当前画布统计')
  const graph = page.getByLabel('图谱画布')
  const detail = page.getByLabel('图谱详情')
  await expect(counts).toContainText('1 节点')
  await expect(detail.getByRole('heading', { name: root.name, exact: true })).toBeVisible()
  await expect.poll(async () => (await graphInfo(page, root.id)).nodes.length).toBe(1)
  await page.screenshot({ path: testInfo.outputPath('initial.png') })
  await clickNode(page, root.id)
  await expect(counts).toContainText('第 2 层')
  await expect.poll(async () => (await graphInfo(page, root.id)).edges.length).toBeGreaterThan(1)
  await page.waitForTimeout(200)
  await page.screenshot({ path: testInfo.outputPath('expanded.png') })
  const initial = await graphInfo(page, root.id)
  const next = data.edges.flatMap(edge => {
    const nextId = edge.source === root.id ? edge.target : edge.target === root.id ? edge.source : ''
    return nextId && data.edges.some(e =>
      (e.source === nextId && !initial.nodes.includes(e.target)) ||
      (e.target === nextId && !initial.nodes.includes(e.source))) ? [nextId] : []
  })[0]
  await clickNode(page, next)
  await expect(counts).toContainText('第 3 层')
  const expanded = await graphInfo(page, root.id)
  expect(new Set(expanded.nodes).size).toBe(expanded.nodes.length)
  expect(new Set(expanded.edges).size).toBe(expanded.edges.length)
  expect(Math.hypot(expanded.point![0] - initial.point![0], expanded.point![1] - initial.point![1])).toBeLessThan(2)
  await detail.getByRole('button', { name: '收起下一层' }).click()
  await expect(counts).toContainText('第 2 层')
  await detail.getByRole('button', { name: '展开直接关联' }).click()
  await expect(counts).toContainText('第 3 层')

  const search = page.getByRole('searchbox', { name: '搜索实体' })
  await search.fill('教育程度低')
  await page.getByLabel('搜索结果').getByRole('button', { name: /低教育程度/ }).click()
  await expect(counts).toContainText('1 节点')
  await expect(detail.getByRole('heading', { name: '低教育程度' })).toBeVisible()
  await page.getByLabel('实体类型', { exact: true }).selectOption('心血管疾病')
  await page.getByLabel('关系类型', { exact: true }).selectOption('增加风险')
  await clickNode(page, searchRoot.id)
  await expect(counts).toContainText('2 节点')
  await expect(counts).toContainText('1 关系')
  await expect.poll(async () => (await graphInfo(page, child.id)).edges.length).toBe(1)
  await page.waitForTimeout(220)
  const [sx, sy] = (await graphInfo(page, searchRoot.id)).viewportPoint!
  const [tx, ty] = (await graphInfo(page, child.id)).viewportPoint!
  await page.screenshot({ path: testInfo.outputPath('filtered.png') })
  const edgeTarget = await page.locator('.graph-surface').evaluate(el => {
    const host = el as HTMLElement & {
      __vueParentComponent: { exposed: { testGraph: () => Graph } }
    }
    const graph = host.__vueParentComponent.exposed.testGraph()
    const id = graph.getEdgeData()[0].id!
    const bounds = graph.getElementRenderBounds(id)
    return graph.getClientByCanvas(bounds.center)
  })
  await page.mouse.move(edgeTarget[0], edgeTarget[1])
  await expect(graph.getByText('增加风险', { exact: true })).toBeVisible()
  await page.mouse.click(edgeTarget[0], edgeTarget[1])
  await expect(detail.getByRole('heading', { name: '关系详情' })).toBeVisible()
  await detail.getByRole('button', { name: /中国心血管病一级预防指南/ }).click()
  await expect(detail.locator('blockquote')).toBeVisible()
  await expect(detail.getByText(/第 \d+ 页/)).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('evidence.png') })

  const beforeDrag = await graphInfo(page, child.id)
  await page.mouse.move(...beforeDrag.viewportPoint!.slice(0, 2) as [number, number])
  await page.mouse.down()
  await page.waitForTimeout(125)
  await page.mouse.move(beforeDrag.viewportPoint![0] + 40, beforeDrag.viewportPoint![1] + 30, { steps: 8 })
  await page.mouse.up()
  await expect.poll(async () => (await graphInfo(page, child.id)).point![0]).toBeGreaterThan(beforeDrag.point![0] + 10)
  const box = (await page.locator('.graph-host').boundingBox())!
  const beforePan = await graphInfo(page, child.id)
  await page.mouse.move(box.x + 28, box.y + 36)
  await page.mouse.down()
  await page.waitForTimeout(125)
  await page.mouse.move(box.x + 70, box.y + 66, { steps: 8 })
  await page.mouse.up()
  await expect.poll(async () => (await graphInfo(page, child.id)).viewportPoint![0])
    .toBeGreaterThan(beforePan.viewportPoint![0] + 10)
  const initialZoom = (await graphInfo(page, child.id)).zoom
  await page.getByRole('button', { name: '放大' }).click()
  await expect.poll(async () => (await graphInfo(page, child.id)).zoom).toBeGreaterThan(initialZoom)
  const buttonZoom = (await graphInfo(page, child.id)).zoom
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.wheel(0, 300)
  await expect.poll(async () => (await graphInfo(page, child.id)).zoom).toBeLessThan(buttonZoom)
  await page.getByRole('button', { name: '适配画布' }).click()

  await page.getByRole('button', { name: '重置探索' }).click()
  await expect(counts).toContainText('1 节点')
  await detail.getByRole('button', { name: '展开直接关联' }).click()
  await expect(counts).toContainText('第 2 层')
  await expect.poll(async () => (await graphInfo(page, root.id)).nodes.length).toBeGreaterThan(1)
  const explorerNodes = (await graphInfo(page, root.id)).nodes.sort()
  await page.getByRole('button', { name: '全图概览' }).click()
  await expect(counts).toContainText(data.metadata.entityCount + ' 节点')
  await expect.poll(async () => (await graphInfo(page, root.id)).edges.length).toBe(data.metadata.relationCount)
  await expect(page.locator('.graph-surface')).toHaveAttribute('aria-busy', 'false')
  await page.screenshot({ path: testInfo.outputPath('overview.png') })
  await page.getByRole('button', { name: '逐层探索' }).click()
  await expect(counts).toContainText('第 2 层')
  await expect.poll(async () => (await graphInfo(page, root.id)).nodes.sort()).toEqual(explorerNodes)
  await page.setViewportSize({ width: 320, height: 844 })
  await expect.poll(async () => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320)
  expect(errors).toEqual([])
})
