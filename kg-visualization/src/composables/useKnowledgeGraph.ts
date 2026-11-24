import { computed, onMounted, onUnmounted, ref, shallowRef } from 'vue'
import type { KnowledgeGraph, Selection } from '../types/graph'
import { explore, indexGraph, overview } from '../utils/graphFilter'
import { readGraph } from '../utils/readGraph'

export function useKnowledgeGraph() {
  const index = shallowRef(indexGraph({ nodes: [], edges: [], documents: [], evidence: [] }))
  const metadata = shallowRef<KnowledgeGraph['metadata']>()
  const center = ref('')
  const expanded = shallowRef(new Set<string>())
  const filters = ref({ entity: '', relation: '' })
  const mode = ref<'explore' | 'overview'>('explore')
  const selection = ref<Selection>()
  const loading = ref(true)
  const error = ref('')
  const resetSequence = ref(0)
  const abort = new AbortController()

  function start(id: string) {
    if (!index.value.nodes.has(id)) return
    center.value = id
    expanded.value = new Set()
    selection.value = { kind: 'node', id }
    mode.value = 'explore'
    resetSequence.value += 1
  }

  function reset() {
    filters.value = { entity: '', relation: '' }
    const root = index.value.ranked.find(node => node.name === '冠心病'
      && node.entityType === '心血管疾病' && (index.value.adjacent.get(node.id)?.length ?? 0) > 0)
      ?? index.value.ranked[0]
    if (root) start(root.id)
  }

  onMounted(async () => {
    try {
      const response = await fetch(import.meta.env.BASE_URL + 'data/graph-data.json', { signal: abort.signal })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = readGraph(await response.json())
      index.value = indexGraph(data)
      metadata.value = { ...data.metadata, entityCount: data.nodes.length,
        relationCount: data.edges.length, documentCount: data.documents.length }
      reset()
    } catch (cause) {
      if (!abort.signal.aborted) error.value = `无法读取图谱数据（${String(cause)}）`
    } finally {
      if (!abort.signal.aborted) loading.value = false
    }
  })
  onUnmounted(() => abort.abort())

  const overviewView = computed(() => overview(index.value, filters.value))
  const overviewTooLarge = computed(() =>
    overviewView.value.nodes.length > 600 || overviewView.value.edges.length > 1400,
  )
  const view = computed(() => {
    if (mode.value === 'explore') return explore(index.value, center.value, expanded.value, filters.value)
    if (overviewTooLarge.value) return { nodes: [], edges: [], levels: new Map(), parents: new Map() }
    return overviewView.value
  })
  const current = computed(() => {
    const value = selection.value
    if (value?.kind === 'node' && view.value.nodes.some(node => node.id === value.id)) {
      return { node: index.value.nodes.get(value.id), edge: undefined }
    }
    if (value?.kind === 'edge' && view.value.edges.some(edge => edge.id === value.id)) {
      return { node: undefined, edge: index.value.edges.get(value.id) }
    }
    return {}
  })
  const layer = computed(() => view.value.levels.size ? [...view.value.levels.values()].reduce((max, level) => Math.max(max, level), 0) + 1 : 0)

  function selectNode(id: string) {
    selection.value = { kind: 'node', id }
    if (mode.value === 'explore' && !expanded.value.has(id)) {
      expanded.value = new Set([...expanded.value, id])
    }
  }

  function collapse(id: string) {
    const remaining = new Set(expanded.value)
    remaining.delete(id)
    const reachable = explore(index.value, center.value, remaining, { entity: '', relation: '' }).levels
    expanded.value = new Set([...remaining].filter(nodeId => reachable.has(nodeId)))
  }

  function setMode(value: typeof mode.value) {
    mode.value = value
    selection.value = value === 'explore' && center.value
      ? { kind: 'node', id: center.value } : undefined
  }

  return { index, metadata, center, expanded, filters, mode, selection, loading, error, resetSequence,
    view, current, layer, overviewTooLarge, start, reset, selectNode, collapse, setMode }
}
