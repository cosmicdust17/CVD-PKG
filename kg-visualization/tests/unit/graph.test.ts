import { describe, expect, it } from 'vitest'
import data from '../../public/data/graph-data.json'
import type { Filters } from '../../src/types/graph'
import { explore, indexGraph, otherEnd, overview, resolveEvidence, searchEntities } from '../../src/utils/graphFilter'
import { toEdges } from '../../src/utils/graphTransform'
import { readGraph } from '../../src/utils/readGraph'

const index = indexGraph(data)
const filters: Filters = { entity: '', relation: '' }
const byName = (name: string) => data.nodes.find(node => node.name === name)!
const root = byName('低教育程度')
const child = byName('心血管病')

describe('多层探索', () => {
  it('初始仅有中心，继续展开时只添加实际一度关系且没有重复项', () => {
    expect(explore(index, root.id, new Set(), filters).nodes).toEqual([root])
    const first = explore(index, root.id, new Set([root.id]), filters)
    expect(first.edges).toEqual(index.adjacent.get(root.id))
    expect(first.levels.get(child.id)).toBe(1)
    const expanded = new Set([root.id, child.id])
    const second = explore(index, root.id, expanded, filters)
    expect([...second.levels.values()]).toContain(2)
    expect(new Set(second.nodes.map(n => n.id)).size).toBe(second.nodes.length)
    expect(new Set(second.edges.map(e => e.id)).size).toBe(second.edges.length)
    const branch = second.nodes.find(node => second.levels.get(node.id) === 2
      && index.adjacent.get(node.id)?.some(edge => !second.levels.has(otherEnd(edge, node.id))))!
    expanded.add(branch.id)
    expect([...explore(index, root.id, expanded, filters).levels.values()]).toContain(3)
    expect(explore(index, root.id, new Set([child.id]), filters).nodes).toEqual([root])
  })

  it('筛选时保留中心，并只探索满足两个条件的关联', () => {
    const view = explore(index, root.id, new Set([root.id]), { entity: '心血管疾病', relation: '增加风险' })
    expect(view.nodes.map(n => n.id)).toEqual([root.id, child.id])
    expect(view.edges).toHaveLength(1)
    expect(view.edges[0].relationType).toBe('增加风险')
    expect(overview(index, filters).edges).toHaveLength(data.metadata.relationCount)
  })

  it('按原始别名搜索，并保留多文献关系的证据与方向', () => {
    expect(searchEntities(index.ranked, '教育程度低', '')).toContainEqual(root)
    expect(searchEntities(index.ranked, '教育程度低', '人群')).toEqual([])
    const edge = data.edges.find(edge => edge.sourceDocumentIds.length > 1)!
    const evidence = resolveEvidence(index, [...edge.evidenceIds, edge.evidenceIds[0], 'missing'])
    expect(evidence).toHaveLength(edge.evidenceIds.length)
    expect(new Set(evidence.map(ev => ev.documentId))).toEqual(new Set(edge.sourceDocumentIds))
    expect(evidence.every(ev => ev.page && ev.quote)).toBe(true)
    const related = data.edges.find(e => !e.directed)!
    const converted = toEdges([edge, related], true)
    expect(converted.map(e => [e.source, e.target, e.style?.endArrow])).toEqual(
      [edge, related].map(e => [e.source, e.target, e.directed]),
    )
  })
})

describe('读取图谱 JSON', () => {
  it('接受有效和空图谱，并在加载时拦截悬空边和重复 ID', () => {
    expect(readGraph(data)).toBe(data)
    expect(readGraph({ ...data, nodes: [], edges: [], documents: [], evidence: [] }).nodes).toEqual([])
    expect(() => readGraph({ ...data, nodes: [] })).toThrow('悬空引用')
    expect(() => readGraph({ ...data, nodes: [...data.nodes, data.nodes[0]] })).toThrow('重复 ID')
  })
})