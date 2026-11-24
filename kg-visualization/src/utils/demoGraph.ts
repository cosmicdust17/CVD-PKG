import { otherEnd, type GraphIndex } from './graphFilter'
import type { Factor, HealthGraph, Lifestyle, Simulation } from './healthApi'

export function localPaths(index: GraphIndex, roots: string[], depth: number, outgoing = false): HealthGraph {
  const paths: HealthGraph['paths'] = []
  const edgeIds = new Set<string>()
  const nodeIds = new Set(roots)
  for (const root of roots) {
    const queue = [{ nodes: [root], edges: [] as string[] }]
    const visited = new Set([root])
    for (const path of queue) {
      if (path.edges.length >= depth) continue
      const end = path.nodes.at(-1)!
      for (const edge of index.adjacent.get(end) ?? []) {
        if (outgoing && edge.directed && edge.source !== end) continue
        const next = otherEnd(edge, end)
        if (path.nodes.includes(next)) continue
        const nextPath = { nodes: [...path.nodes, next], edges: [...path.edges, edge.id] }
        if (!edgeIds.has(edge.id)) paths.push(nextPath)
        edgeIds.add(edge.id)
        nodeIds.add(next)
        if (!visited.has(next)) {
          visited.add(next)
          queue.push(nextPath)
        }
      }
    }
  }
  return {
    nodes: [...nodeIds].map(id => index.nodes.get(id)!),
    edges: [...edgeIds].map(id => index.edges.get(id)!),
    paths, matched_entities: roots, missing_entities: [],
  }
}

const exposures = {
  diet: { value: 'high', names: ['高盐饮食', '高钠膳食', '高钠饮食'] },
  exercise: { value: 'inactive', names: ['久坐行为'] },
  sleep: { value: 'irregular', names: ['睡眠不足或睡眠模式紊乱'] },
  smoking: { value: 'current', names: ['吸烟'] },
} satisfies Record<Factor, { value: string; names: string[] }>

export function demoScenario(index: GraphIndex, lifestyle: Lifestyle): Pick<Simulation,
  'baseline' | 'modified' | 'graph' | 'removed_edge_ids' | 'added_edge_ids' | 'recommendations' | 'focus' | 'limitations'> {
  const names = Object.entries(exposures).flatMap(([factor, exposure]) =>
    lifestyle[factor as Factor] === exposure.value ? exposure.names : [])
  const roots = index.ranked.filter(node => [node.name, ...node.aliases].some(name => names.includes(name))).map(node => node.id)
  const graph = localPaths(index, roots, 2, true)
  const related = (type: string) => graph.nodes.filter(node => node.entityType === type).map(node => node.name)
  return {
    baseline: { lifestyle: {}, graph: localPaths(index, [], 2), related_diseases: [], risk_factors: [] },
    modified: { lifestyle, graph, related_diseases: related('心血管疾病'), risk_factors: related('危险因素') },
    graph, removed_edge_ids: [], added_edge_ids: graph.edges.map(edge => edge.id),
    recommendations: [], focus: [],
    limitations: ['路径来自已发布图谱。可探索的关系随所选暴露变化。滑块位置仅表示场景设置。'],
  }
}
