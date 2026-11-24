import type { Entity, Filters, GraphView, KnowledgeGraph, Relation } from '../types/graph'

export function indexGraph(data: Pick<KnowledgeGraph, 'nodes' | 'edges' | 'documents' | 'evidence'>) {
  const nodes = new Map(data.nodes.map(node => [node.id, node]))
  const edges = new Map(data.edges.map(edge => [edge.id, edge]))
  const documents = new Map(data.documents.map(doc => [doc.id, doc]))
  const evidence = new Map(data.evidence.map(item => [item.id, item]))
  const adjacent = new Map<string, Relation[]>(data.nodes.map(node => [node.id, []]))

  for (const edge of data.edges) {
    adjacent.get(edge.source)?.push(edge)
    if (edge.source !== edge.target) adjacent.get(edge.target)?.push(edge)
  }

  const ranked = [...data.nodes].sort((a, b) =>
    adjacent.get(b.id)!.length - adjacent.get(a.id)!.length || a.name.localeCompare(b.name, 'zh-CN'),
  )
  const entityTypes = [...new Set(data.nodes.map(node => node.entityType))]
  const relationTypes = [...new Set(data.edges.map(edge => edge.relationType))]
  return { nodes, edges, documents, evidence, adjacent, ranked, entityTypes, relationTypes }
}

export type GraphIndex = ReturnType<typeof indexGraph>

export function otherEnd(edge: Relation, id: string) {
  return edge.source === id ? edge.target : edge.source
}

export function matchingRelations(index: GraphIndex, id: string, center: string, filters: Filters) {
  return (index.adjacent.get(id) ?? []).filter(edge => {
    const other = otherEnd(edge, id)
    return (!filters.relation || edge.relationType === filters.relation)
      && (!filters.entity || other === center || index.nodes.get(other)?.entityType === filters.entity)
  })
}

export function explore(
  index: GraphIndex, center: string, expanded: ReadonlySet<string>, filters: Filters,
): GraphView {
  const root = index.nodes.get(center)
  const nodes = root ? [root] : []
  const edges = new Map<string, Relation>()
  const levels = new Map(root ? [[center, 0]] : [])
  const parents = new Map<string, string>()
  for (const node of nodes) {
    if (!expanded.has(node.id)) continue
    for (const edge of matchingRelations(index, node.id, center, filters)) {
      edges.set(edge.id, edge)
      const id = otherEnd(edge, node.id)
      if (levels.has(id)) continue
      levels.set(id, levels.get(node.id)! + 1)
      parents.set(id, node.id)
      nodes.push(index.nodes.get(id)!)
    }
  }
  return { nodes, edges: [...edges.values()], levels, parents }
}

export function overview(index: GraphIndex, filters: Filters): GraphView {
  const eligible = [...index.nodes.values()].filter(node => !filters.entity || node.entityType === filters.entity)
  const ids = new Set(eligible.map(node => node.id))
  const edges = [...index.edges.values()].filter(edge => ids.has(edge.source) && ids.has(edge.target)
    && (!filters.relation || edge.relationType === filters.relation))
  const connected = new Set(edges.flatMap(edge => [edge.source, edge.target]))
  const nodes = filters.relation ? eligible.filter(node => connected.has(node.id)) : eligible
  return { nodes, edges, levels: new Map(), parents: new Map() }
}

const normalize = (value: string) => value.normalize('NFKC').trim().replace(/\s+/g, ' ').toLowerCase()

export function searchEntities(ranked: Entity[], input: string, type: string) {
  const query = normalize(input)
  if (!query) return []
  const matches = ranked.filter(node => (!type || node.entityType === type)
    && [node.name, ...node.aliases].some(text => normalize(text).includes(query)))
  return matches.sort((a, b) => Number(normalize(b.name) === query) - Number(normalize(a.name) === query))
}

export function resolveEvidence(index: GraphIndex, ids: string[]) {
  return [...new Set(ids)].flatMap(id => {
    const item = index.evidence.get(id)
    return item ? [item] : []
  })
}
