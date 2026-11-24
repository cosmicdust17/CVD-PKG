<script setup lang="ts">
import { computed } from 'vue'
import type { Entity, Filters, GraphView, Relation } from '../types/graph'
import { matchingRelations, otherEnd, type GraphIndex } from '../utils/graphFilter'
import { colorFor } from '../utils/graphTransform'
import EvidencePanel from './EvidencePanel.vue'

const props = defineProps<{
  index: GraphIndex
  view: GraphView
  filters: Filters
  center: string
  mode: 'explore' | 'overview'
  node?: Entity
  edge?: Relation
  expanded: boolean
}>()
const emit = defineEmits<{ expand: [id: string]; collapse: [id: string]; edge: [id: string] }>()
const selected = computed(() => props.node ?? props.edge)
const related = computed(() => {
  if (!props.node) return []
  const id = props.node.id
  const edges = props.mode === 'explore'
    ? matchingRelations(props.index, id, props.center, props.filters)
    : props.view.edges.filter(edge => edge.source === id || edge.target === id)
  return edges.map(edge => ({ edge, node: props.index.nodes.get(otherEnd(edge, id))! }))
})
const layer = computed(() => props.node ? props.view.levels.get(props.node.id) : undefined)
</script>

<template>
  <aside class="card detail" aria-label="图谱详情">
    <div class="panel-heading">
      <h2>{{ edge ? '关系详情' : '实体详情' }}</h2>
    </div>
    <div v-if="selected" class="detail-body">
      <div v-if="node" class="entity-summary">
        <div class="entity-meta">
          <span class="entity-type"><i class="type-dot" :style="{ background: colorFor(node.entityType).fill }"/>{{ node.entityType }}</span>
          <small v-if="layer !== undefined" class="muted">第 {{ layer + 1 }} 层</small>
        </div>
        <h3 class="entity-title">{{ node.name }}</h3>
        <p class="muted small">别名 <span class="alias-list">{{ node.aliases.join('、') || '暂无' }}</span></p>
        <button v-if="mode === 'explore' && (expanded || related.length)" type="button"
          class="button detail-action" @click="expanded ? emit('collapse', node.id) : emit('expand', node.id)">
          {{ expanded ? '收起下一层' : '展开直接关联' }}
        </button>
      </div>
      <div v-else-if="edge" class="entity-summary">
        <div class="entity-meta"><span class="entity-type">{{ edge.directed ? '有向关系' : '无向关系' }}</span></div>
        <h3 class="entity-title">{{ edge.relationType }}</h3>
        <div class="edge-summary">
          <span>{{ index.nodes.get(edge.source)?.name }}</span>
          <span class="edge-direction" :aria-label="edge.directed ? '指向' : '关联'">{{ edge.directed ? '→' : '↔' }}</span>
          <span>{{ index.nodes.get(edge.target)?.name }}</span>
        </div>
      </div>
      <section class="detail-section">
        <h3>来源文献 <span class="count">{{ selected.sourceDocumentIds.length }}</span></h3>
        <ul class="sources">
          <li v-for="id in selected.sourceDocumentIds" :key="id">
            <span class="source-id">{{ id }}</span><span>{{ index.documents.get(id)?.name || id }}</span>
          </li>
        </ul>
      </section>
      <section v-if="node" class="detail-section">
        <h3>直接关联 <span class="count">{{ related.length }}</span></h3>
        <p v-if="!related.length" class="muted small">当前条件下无直接关联</p>
        <ul v-else class="related-list">
          <li v-for="item in related" :key="item.edge.id">
            <button type="button" class="related-button" @click="emit('edge', item.edge.id)">
              <span>{{ item.node.name }}</span>
              <small>{{ !item.edge.directed ? '↔' : item.edge.source === node.id ? '→' : '←' }} {{ item.edge.label }}</small>
            </button>
          </li>
        </ul>
      </section>
      <EvidencePanel :key="selected.id" :index="index" :ids="selected.evidenceIds" :relation="edge"/>
    </div>
    <div v-else class="detail-body muted empty-detail">选择画布上的实体或关系，查看来源文献和证据。</div>
  </aside>
</template>
