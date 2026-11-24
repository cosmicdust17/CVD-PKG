import type { Entity, Relation } from '../types/graph'

export const staticDemo = import.meta.env.MODE === 'pages'

export interface HealthGraph {
  nodes: Entity[]
  edges: Relation[]
  paths: { nodes: string[]; edges: string[] }[]
  matched_entities: string[]
  missing_entities: string[]
}

export const emptyHealthGraph: HealthGraph = {
  nodes: [], edges: [], paths: [], matched_entities: [], missing_entities: [],
}

export interface Source {
  citation_number?: number
  id: string
  title: string
  document_id: string | null
  document_name: string | null
  page: number | null
  quote: string
  source: string
  chunk_id: string
  relevance: number | null
  node_ids: string[]
  edge_ids: string[]
}

export const factors = { diet: '饮食 · 盐摄入', exercise: '运动与久坐', sleep: '睡眠与作息', smoking: '吸烟' }
export type Factor = keyof typeof factors
export type Lifestyle = Partial<Record<Factor, string>>
export type Context = { previous_question?: string; entity_ids?: string[]; path_edge_ids?: string[] }

export interface ChatReply {
  conversation_id: string
  answer: string
  answer_markdown?: string
  graph: HealthGraph
  evidence: Source[]
  evidence_status: string
  agent_trace: { agent: string; status: string; detail?: string }[]
  suggested_questions: string[]
  topics: Factor[]
}

interface Scenario {
  lifestyle: Lifestyle
  graph: HealthGraph
  related_diseases: string[]
  risk_factors: string[]
}

export interface Simulation {
  scenario_id: string
  baseline: Scenario
  modified: Scenario
  graph: HealthGraph
  changes: { factor: Factor; before: string | null; after: string | null }[]
  removed_edge_ids: string[]
  added_edge_ids: string[]
  recommendations: { factor: Factor; title: string; evidence_id: string }[]
  evidence: Source[]
  evidence_status: string
  explanation: string
  answer_markdown?: string
  focus: { factor: Factor; question: string; entity_ids: string[] }[]
  limitations: string[]
}

export interface HistoryItem { id: string; created_at: string; title: string; lifestyle: Lifestyle; compare_with?: Lifestyle }
export interface RiskResult {
  model: string
  model_year: number
  package_version: string
  region: string
  population: string
  result_percent: number
  unit: string
  outcome: string
  limitations: string[]
  citation: string
}

export function stored<T>(key: string, fallback: T): T {
  try { return JSON.parse(localStorage.getItem(key) ?? 'null') ?? fallback }
  catch { return fallback }
}

export function saveLocal(key: string, value: unknown) {
  try { localStorage.setItem(key, JSON.stringify(value)) } catch { /* volatile browser session */ }
}

let browserId = stored('hfkg:browser', '')
export function sourceUrl(source: Source) {
  if (!source.document_id) return undefined
  return '/api/knowledge-evidence/documents/' + encodeURIComponent(source.document_id)
    + (source.page ? '#page=' + source.page : '')
}

export async function api<T>(path: string, data?: object, method = data ? 'POST' : 'GET'): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (data) headers['Content-Type'] = 'application/json'
  if (path.startsWith('simulator/history')) {
    if (!browserId) {
      browserId = crypto.randomUUID()
      saveLocal('hfkg:browser', browserId)
    }
    headers['X-HF-Browser-ID'] = browserId
  }
  let response
  try {
    response = await fetch('/api/' + path, {
      headers, method, body: data ? JSON.stringify(data) : undefined,
    })
  } catch {
    throw new Error('无法连接 HF-KG 服务。请确认本地后端已启动。')
  }
  if (response.status === 204) return undefined as T
  const payload = await response.json().catch(() => null)
  if (!response.ok || payload === null) {
    if (typeof payload?.detail === 'string') throw new Error(payload.detail)
    if (Array.isArray(payload?.detail)) {
      throw new Error('请检查所填字段：' + payload.detail.map((item: { loc: string[] }) => item.loc.at(-1)).join('、'))
    }
    throw new Error('HF-KG 服务暂不可用。请确认本地后端已启动。')
  }
  return payload as T
}
