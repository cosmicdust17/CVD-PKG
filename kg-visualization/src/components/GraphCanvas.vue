<script setup lang="ts">
import { EdgeEvent, Graph, GraphEvent, NodeEvent } from '@antv/g6'
import type { GraphOptions, IElementEvent } from '@antv/g6'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { GraphView, Selection } from '../types/graph'
import { toEdges, toNode } from '../utils/graphTransform'

const props = defineProps<{
  view: GraphView
  center: string
  mode: 'explore' | 'overview'
  sequence: number
  selected?: Selection
  highlightColors?: Record<string, string>
  fixedLabelSize?: boolean
}>()
const emit = defineEmits<{
  node: [id: string]
  edge: [id: string]
}>()
const host = ref<HTMLDivElement>()
const busy = ref(false)
const error = ref('')
const tooltip = ref<{ text: string; x: number; y: number }>()
let graph: Graph | undefined
let observer: ResizeObserver | undefined
let nextRender = false
let rendering = false
let lastMode: typeof props.mode | undefined
let lastSequence = -1
let lastNodeIds = new Set<string>()
let lastView: GraphView | undefined
let lastHighlights: typeof props.highlightColors
let lastSelection = ''
let labelZoom = 0
const explorePositions = new Map<string, [number, number]>()
const motion = { duration: 180 }
const nodeStates: NonNullable<GraphOptions['node']>['state'] = {
  active: { lineWidth: 3, stroke: '#168779' },
  selected: { lineWidth: 4, stroke: '#11796e', halo: true, haloStroke: '#60c0b3', haloLineWidth: 8 },
}
const edgeStates: NonNullable<GraphOptions['edge']>['state'] = {
  active: { stroke: '#087467', lineWidth: 3, label: true },
  selected: { stroke: '#087467', lineWidth: 3, label: true },
}

function showTooltip(event: IElementEvent, kind: 'node' | 'edge') {
  const bounds = host.value?.getBoundingClientRect()
  if (!bounds) return
  const node = kind === 'node' ? props.view.nodes.find(n => n.id === event.target.id) : undefined
  const edge = kind === 'edge' ? props.view.edges.find(e => e.id === event.target.id) : undefined
  const text = node ? `${node.name} · ${node.entityType}`
    : edge ? `${edge.label}${edge.directed ? '' : ' · 无向'}` : ''
  if (text) tooltip.value = { text, x: Math.max(12, Math.min(bounds.width - 12, event.clientX - bounds.left)),
    y: Math.max(32, event.clientY - bounds.top - 12) }
}

async function update() {
  if (!graph || !host.value) return
  const activeGraph = graph
  const { view, mode, sequence, center, selected, highlightColors } = props
  const changed = view !== lastView || mode !== lastMode || sequence !== lastSequence || highlightColors !== lastHighlights
  if (changed) {
    const previousCount = lastNodeIds.size
    const reset = sequence !== lastSequence
    const switched = mode !== lastMode
    const hostCenter: [number, number] = [host.value.clientWidth / 2, host.value.clientHeight / 2]
    const viewportCenter = lastMode ? activeGraph.getCanvasByViewport(hostCenter) : hostCenter
    if (!reset && lastMode === 'explore') {
      for (const id of lastNodeIds) {
        const [x, y] = activeGraph.getElementPosition(id)
        explorePositions.set(id, [x, y])
      }
    }
    if (reset) explorePositions.clear()
    // Spread the initial scenario subgraph across a landscape canvas.
    const scenarioAspect = Math.min(1.8, Math.max(0.65, hostCenter[0] / hostCenter[1]))
    const spreadScenario = props.fixedLabelSize && reset && mode === 'explore' && view.nodes.length > 1
    const positions = mode === 'explore' ? new Map(explorePositions) : new Map<string, [number, number]>()
    const anchors = new Set(positions.keys())
    const added = view.nodes.filter(node => !positions.has(node.id))
    const siblings = new Map<string, string[]>()
    for (const node of added) {
      const parent = view.parents.get(node.id) ?? ''
      const group = siblings.get(parent) ?? []
      group.push(node.id)
      siblings.set(parent, group)
    }
    const canvasCenter: [number, number] = [viewportCenter[0], viewportCenter[1]]
    const compact = mode === 'overview' && view.nodes.length > 70
    const nodes = view.nodes.map((node, index) => {
      const parent = view.parents.get(node.id) ?? ''
      if (!positions.has(node.id)) {
        const [x, y] = positions.get(parent) ?? canvasCenter
        const group = siblings.get(parent)!
        const slot = group.indexOf(node.id)
        const angle = mode === 'overview' ? slot * 2.399963 : (slot / group.length) * Math.PI * 2 - Math.PI / 2
        const radius = node.id === center && mode === 'explore' ? 0
          : mode === 'overview' ? 65 * Math.sqrt(slot + 1) : Math.max(210, (group.length * 132) / (2 * Math.PI))
        if (spreadScenario) {
          const spiral = index * 2.399963
          const distance = 85 * Math.sqrt(index)
          positions.set(node.id, [hostCenter[0] + Math.cos(spiral) * distance * scenarioAspect, hostCenter[1] + Math.sin(spiral) * distance])
        } else {
          positions.set(node.id, [x + Math.cos(angle) * radius, y + Math.sin(angle) * radius])
        }
      }
      const data = toNode(node, positions.get(node.id)!, node.id === center && mode === 'explore', compact)
      const color = highlightColors?.[node.id]
      if (color) data.style = { ...data.style, stroke: color, lineWidth: 4 }
      return data
    })
    const edges = toEdges(view.edges, mode === 'explore' || view.edges.length <= 70)
    for (const edge of edges) {
      const color = edge.id ? highlightColors?.[edge.id] : undefined
      if (color) edge.style = { ...edge.style, stroke: color, lineWidth: 3 }
    }
    activeGraph.setData({ nodes, edges })
    const relax = view.nodes.length > 1 && added.length > 0
    if (relax) {
      activeGraph.setLayout({
        type: 'force', preLayout: true, animation: false,
        iterations: mode === 'overview' ? 90 : 24,
        center: canvasCenter, preventOverlap: true, nodeSpacing: compact ? 30 : 20, linkDistance: 225,
        gravity: compact ? 2 : 10, collideStrength: compact ? 3 : 1,
        getMass: (node: { id: string }) =>
          anchors.has(node.id) || (mode === 'explore' && node.id === center) ? 1000000 : 1,
      })
      await activeGraph.render()
    } else {
      await activeGraph.draw()
    }
    if (activeGraph.destroyed) return
    if (nodes.length && (reset || switched || mode === 'overview' || previousCount <= 1)) {
      if (nodes.length === 1) {
        await activeGraph.zoomTo(1, false)
        if (activeGraph.destroyed) return
        await activeGraph.fitCenter(false)
      } else {
        await activeGraph.fitView({ when: 'always' }, false)
        if (activeGraph.destroyed) return
        if (mode === 'explore' && activeGraph.getZoom() > 1) {
          await activeGraph.zoomTo(1, false)
          if (activeGraph.destroyed) return
          await activeGraph.fitCenter(false)
        }
      }
    }
    lastNodeIds = new Set(nodes.map(node => node.id))
    lastMode = mode
    lastView = view
    lastSequence = sequence
    lastHighlights = highlightColors
  }
  if (activeGraph.destroyed) return
  const zoom = activeGraph.getZoom()
  if (props.fixedLabelSize && (changed || labelZoom !== zoom)) {
    // G6 stores font sizes in graph units. Keep text legible in viewport pixels.
    labelZoom = zoom
    activeGraph.updateData({
      nodes: view.nodes.map(({ id }) => ({ id, style: { labelFontSize: 12 / zoom } })),
      edges: view.edges.map(({ id, source, target }) => ({ id, source, target, style: { labelFontSize: 11 / zoom } })),
    })
    await activeGraph.draw()
  }
  if (activeGraph.destroyed) return
  const currentId = selected?.id ?? ''
  if (lastSelection !== currentId || currentId) {
    const states: Record<string, string[]> = {}
    if (lastSelection && (activeGraph.hasNode(lastSelection) || activeGraph.hasEdge(lastSelection))) {
      states[lastSelection] = []
    }
    if (currentId && (activeGraph.hasNode(currentId) || activeGraph.hasEdge(currentId))) {
      states[currentId] = ['selected']
    }
    if (Object.keys(states).length) await activeGraph.setElementState(states, false)
    lastSelection = currentId
  }
}

async function schedule() {
  nextRender = true
  if (rendering || !graph) return
  rendering = true
  try {
    while (nextRender && graph) {
      nextRender = false
      error.value = ''
      busy.value = props.mode === 'overview' && lastView !== props.view && props.view.nodes.length > 0
      if (busy.value) await new Promise(resolve => setTimeout(resolve, 24))
      await update()
    }
  } catch (cause) {
    if (graph) {
      console.error(cause)
      error.value = '图谱绘制失败，请重置探索后重试。'
    }
  } finally {
    busy.value = false
    rendering = false
  }
}

onMounted(() => {
  if (!host.value) return
  graph = new Graph({
    container: host.value, width: host.value.clientWidth, height: host.value.clientHeight,
    padding: 38, zoomRange: [0.08, 2.5], animation: { duration: 160 },
    node: { state: nodeStates, animation: { enter: 'fade', exit: false } },
    edge: { state: edgeStates, animation: { enter: 'fade', exit: false } },
    behaviors: ['drag-canvas', 'zoom-canvas', 'drag-element',
      { type: 'hover-activate', state: 'active' },
    ],
  })
  if (props.fixedLabelSize) {
    graph.on(GraphEvent.AFTER_TRANSFORM, () => {
      if (graph && lastView && labelZoom !== graph.getZoom()) void schedule()
    })
  }
  graph.on(NodeEvent.CLICK, (event: IElementEvent) => emit('node', event.target.id))
  graph.on(EdgeEvent.CLICK, (event: IElementEvent) => emit('edge', event.target.id))
  graph.on(NodeEvent.POINTER_ENTER, (event: IElementEvent) => showTooltip(event, 'node'))
  graph.on(EdgeEvent.POINTER_ENTER, (event: IElementEvent) => showTooltip(event, 'edge'))
  graph.on(NodeEvent.POINTER_LEAVE, () => { tooltip.value = undefined })
  graph.on(EdgeEvent.POINTER_LEAVE, () => { tooltip.value = undefined })
  observer = new ResizeObserver(entries => {
    const { width, height } = entries[0].contentRect
    if (graph && width > 0 && height > 0) graph.resize(width, height)
  })
  observer.observe(host.value)
  void schedule()
})

watch(() => [props.view, props.mode, props.sequence, props.selected, props.highlightColors], () => {
  tooltip.value = undefined
  void schedule()
}, { flush: 'post' })

onBeforeUnmount(() => {
  observer?.disconnect()
  const activeGraph = graph
  graph = undefined
  activeGraph?.destroy()
})

defineExpose({
  fit: () => {
    if (graph && !busy.value && lastNodeIds.size) {
      if (lastNodeIds.size === 1) {
        void graph.zoomTo(1, false).then(() => graph?.fitCenter(motion))
      } else void graph.fitView({ when: 'always' }, motion)
    }
  },
  zoom: (factor: number) => {
    if (graph && !busy.value) void graph.zoomTo(Math.min(2.5, Math.max(0.08, graph.getZoom() * factor)), false)
  },
  ...(import.meta.env.MODE === 'test' ? { testGraph: () => graph } : {}),
})
</script>

<template>
  <div class="graph-surface" :aria-busy="busy">
    <div ref="host" class="graph-host" aria-label="可交互的心血管疾病知识图谱" />
    <div v-if="tooltip" class="graph-tooltip" :style="{ left: tooltip.x + 'px', top: tooltip.y + 'px' }">
      {{ tooltip.text }}
    </div>
    <div v-if="busy || error" class="canvas-message" :role="error ? 'alert' : 'status'">
      {{ error || '正在排布全图…' }}
    </div>
  </div>
</template>
