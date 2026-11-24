import type { KnowledgeGraph } from '../types/graph'

function stringList(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(item => typeof item === 'string')
}

export function readGraph(value: unknown): KnowledgeGraph {
  const graph = value as KnowledgeGraph | null
  if (!graph?.metadata || typeof graph.metadata.name !== 'string'
    || ![graph.nodes, graph.edges, graph.documents, graph.evidence].every(Array.isArray)) {
    throw new Error('JSON 缺少图谱所需字段')
  }
  const nodeIds = new Set(graph.nodes.map(node => node?.id))
  const evidenceIds = new Set(graph.evidence.map(item => item?.id))
  const documentIds = new Set(graph.documents.map(doc => doc?.id))
  const itemIds = new Set([...nodeIds, ...evidenceIds, ...graph.edges.map(edge => edge?.id)])
  if (itemIds.size !== graph.nodes.length + graph.edges.length + graph.evidence.length
    || documentIds.size !== graph.documents.length) {
    throw new Error('JSON 包含重复 ID')
  }
  if (graph.nodes.some(node => !node || !node.id || typeof node.name !== 'string'
    || typeof node.entityType !== 'string' || !stringList(node.aliases))
    || graph.edges.some(edge => !edge || !edge.id || !nodeIds.has(edge.source) || !nodeIds.has(edge.target)
      || typeof edge.label !== 'string' || typeof edge.relationType !== 'string'
      || typeof edge.directed !== 'boolean' || !Array.isArray(edge.sourceRelations))
    || graph.documents.some(doc => !doc || !doc.id)
    || graph.evidence.some(item => !item || !item.id || !documentIds.has(item.documentId))
    || [...graph.nodes, ...graph.edges].some(item =>
      !stringList(item.sourceDocumentIds) || item.sourceDocumentIds.some(id => !documentIds.has(id))
      || !stringList(item.evidenceIds) || item.evidenceIds.some(id => !evidenceIds.has(id)))) {
    throw new Error('JSON 包含无效记录或悬空引用')
  }
  return graph
}
