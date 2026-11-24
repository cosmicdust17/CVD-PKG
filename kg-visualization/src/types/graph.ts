export interface DocumentSource {
  id: string
  name: string | null
}

export interface Evidence {
  id: string
  documentId: string
  documentName: string | null
  page: number | null
  quote: string | null
  originalEvidenceId: string
}

interface SourceRecord {
  id: string
  documentId: string
  evidenceIds: string[]
}

interface Provenance {
  id: string
  sourceDocumentIds: string[]
  evidenceIds: string[]
}

export interface Entity extends Provenance {
  name: string
  entityType: string
  aliases: string[]
  sourceEntityIds: string[]
  sourceEntities: (SourceRecord & { name: string })[]
}

export interface Relation extends Provenance {
  source: string
  target: string
  relationType: string
  label: string
  directed: boolean
  sourceRelationIds: string[]
  sourceRelations: (SourceRecord & {
    qualifiers: string[]
    evidenceContexts: { evidenceIds: string[]; qualifier: string | null }[]
  })[]
}

export interface KnowledgeGraph {
  metadata: { name: string; documentCount: number; entityCount: number; relationCount: number }
  documents: DocumentSource[]
  nodes: Entity[]
  edges: Relation[]
  evidence: Evidence[]
}

export interface GraphView {
  nodes: Entity[]
  edges: Relation[]
  levels: Map<string, number>
  parents: Map<string, string>
}

export interface Filters {
  entity: string
  relation: string
}

export type Selection = { kind: 'node' | 'edge'; id: string }
