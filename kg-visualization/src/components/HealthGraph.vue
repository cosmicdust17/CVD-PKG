<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import GraphCanvas from './GraphCanvas.vue'
import type { GraphView, Selection } from '../types/graph'
import type { indexGraph } from '../utils/graphFilter'
import { localPaths } from '../utils/demoGraph'
import { api, emptyHealthGraph, staticDemo, type HealthGraph, type Source } from '../utils/healthApi'

const props = defineProps<{
  graph: HealthGraph
  index: ReturnType<typeof indexGraph>
  highlighted?: Source
  removed?: string[]
  added?: string[]
  fixedLabelSize?: boolean
}>()
const canvas = ref<InstanceType<typeof GraphCanvas>>()
const mode = ref<'explore' | 'overview'>('explore')
const selected = ref<Selection>()
const extra = ref<HealthGraph>(emptyHealthGraph)
const sequence = ref(0)
const search = ref('')
const error = ref('')
const busy = ref(false)

watch(() => props.graph, () => {
  selected.value = undefined
  extra.value = emptyHealthGraph
  mode.value = 'explore'
  error.value = ''
  busy.value = false
  sequence.value++
})

const candidates = computed(() => {
  const key = search.value.trim().toLowerCase()
  return key ? props.index.ranked.filter(n => [n.name, ...n.aliases].some(s => s.toLowerCase().includes(key))).slice(0, 6) : []
})

const view = computed<GraphView>(() => {
  const levels = new Map<string, number>()
  const parents = new Map<string, string>()
  if (mode.value === 'overview') {
    return { nodes: [...props.index.nodes.values()], edges: [...props.index.edges.values()], levels, parents }
  }
  const nodes = [...new Map([...props.graph.nodes, ...extra.value.nodes].map(n => [n.id, n])).values()]
  const edges = [...new Map([...props.graph.edges, ...extra.value.edges].map(e => [e.id, e])).values()]
  for (const path of [...props.graph.paths, ...extra.value.paths]) {
    path.nodes.forEach((node, i) => {
      if (!levels.has(node) || levels.get(node)! > i) {
        levels.set(node, i)
        if (i) parents.set(node, path.nodes[i - 1])
        else parents.delete(node)
      }
    })
  }
  return { nodes, edges, levels, parents }
})

const styles = computed(() => Object.fromEntries([
  ...props.graph.paths.slice(0, 3).flatMap(path => path.edges.map(id => [id, '#2d877c'])),
  ...(props.removed ?? []).map(id => [id, '#b36628']),
  ...(props.added ?? []).map(id => [id, '#087467']),
  ...(props.highlighted?.edge_ids ?? []).map(id => [id, '#774aa5']),
  ...(props.highlighted?.node_ids ?? []).map(id => [id, '#774aa5']),
]))
const detail = computed(() => {
  const active = selected.value
  if (active?.kind === 'node') {
    const node = props.index.nodes.get(active.id)
    if (node) return { label: node.name, type: node.entityType, ids: node.sourceEntityIds, qualifiers: [] }
  }
  if (active?.kind === 'edge') {
    const edge = props.index.edges.get(active.id)
    if (edge) return { label: [props.index.nodes.get(edge.source)?.name, edge.label,
      props.index.nodes.get(edge.target)?.name].join(' · '), type: edge.directed ? '有向关系' : '无向关系',
      ids: edge.sourceRelationIds, qualifiers: [...new Set(edge.sourceRelations.flatMap(row => row.qualifiers))] }
  }
})

watch(() => props.highlighted, source => {
  if (!source) return
  const edge = source.edge_ids.find(id => view.value.edges.some(row => row.id === id))
  const node = source.node_ids.find(id => view.value.nodes.some(row => row.id === id))
  selected.value = edge ? { kind: 'edge', id: edge } : node ? { kind: 'node', id: node } : undefined
})

function reset() {
  selected.value = undefined
  extra.value = emptyHealthGraph
  mode.value = 'explore'
  search.value = ''
  error.value = ''
  busy.value = false
  sequence.value++
}

async function selectNode(id: string, forceExpand = false) {
  selected.value = { kind: 'node', id }
  search.value = ''
  if (forceExpand) mode.value = 'explore'
  if (mode.value === 'overview') return
  const request = ++sequence.value
  busy.value = true
  error.value = ''
  try {
    const result = staticDemo ? localPaths(props.index, [id], 1)
      : await api<HealthGraph>('knowledge-graph/query', { entities: [id], max_depth: 1 })
    if (sequence.value !== request) return
    extra.value = {
      ...result, nodes: [...extra.value.nodes, ...result.nodes], edges: [...extra.value.edges, ...result.edges],
      paths: [...extra.value.paths, ...result.paths],
    }
  } catch (cause) {
    if (sequence.value === request) error.value = String(cause)
  } finally {
    if (sequence.value === request) busy.value = false
  }
}
</script>

<template>
  <section class="card health-panel health-graph" aria-label="知识图谱">
    <h2>知识图谱</h2>
    <slot/>
    <div class="health-actions">
      <div class="mode-switch">
        <button type="button" :aria-pressed="mode === 'explore'" @click="mode = 'explore'">关联子图</button>
        <button type="button" :aria-pressed="mode === 'overview'" @click="mode = 'overview'">全图概览</button>
      </div>
      <button type="button" class="button" @click="canvas?.zoom(0.8)" aria-label="缩小">−</button>
      <button type="button" class="button" @click="canvas?.zoom(1.25)" aria-label="放大">+</button>
      <button type="button" class="button" @click="canvas?.fit()">适配</button>
      <button type="button" class="button" @click="reset">重置</button>
    </div>
    <label class="health-field">搜索图谱节点<input v-model="search" placeholder="例如 高血压" type="search"></label>
    <div v-if="search" class="health-actions">
      <button v-for="node in candidates" :key="node.id" type="button" class="button" @click="selectNode(node.id, true)">{{ node.name }}</button>
      <span v-if="!candidates.length" class="muted">未找到节点</span>
    </div>
    <div class="canvas-wrapper health-canvas">
      <GraphCanvas ref="canvas" :view="view" :center="graph.matched_entities[0] ?? ''" :mode="mode"
        :sequence="sequence" :selected="selected" :highlight-colors="styles" :fixed-label-size="fixedLabelSize"
        @node="id => selectNode(id)" @edge="id => selected = { kind: 'edge', id }"/>
      <p v-if="!view.nodes.length" class="canvas-message" role="status">当前场景或问题没有匹配的图谱节点。</p>
    </div>
    <p class="muted" role="status">
      {{ view.nodes.length }} 个节点 · {{ view.edges.length }} 条关系
      <span v-if="busy"> · 正在查询关联节点</span>
    </p>
    <p v-if="removed?.length || added?.length" class="graph-key">
      <span v-if="removed?.length" class="removed-key">仅原始场景 {{ removed.length }} 条</span>
      <span v-if="added?.length" class="added-key">仅调整场景 {{ added.length }} 条</span>
    </p>
    <p v-if="error" role="alert">{{ error }}</p>
    <div v-if="detail" class="health-graph-detail">
      <strong>{{ detail.label }}</strong><p>{{ detail.type }} · {{ detail.ids.join('、') }}</p>
      <p v-for="q in detail.qualifiers" :key="q">{{ q }}</p>
    </div>
  </section>
</template>
