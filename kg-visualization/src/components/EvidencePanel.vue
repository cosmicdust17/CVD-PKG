<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { Relation } from '../types/graph'
import { resolveEvidence, type GraphIndex } from '../utils/graphFilter'

const props = defineProps<{ index: GraphIndex; ids: string[]; relation?: Relation }>()
const items = computed(() => resolveEvidence(props.index, props.ids))
const openId = ref('')
watch(() => props.ids, () => { openId.value = '' })
const openItem = computed(() => items.value.find(item => item.id === openId.value))
const qualifiers = computed(() => {
  if (!props.relation || !openItem.value) return []
  const id = openItem.value.id
  const values = props.relation.sourceRelations.flatMap(source => {
    if (!source.evidenceIds.includes(id)) return []
    const matched = source.evidenceContexts.filter(context => context.evidenceIds.includes(id))
    return matched.length ? matched.flatMap(context => context.qualifier ? [context.qualifier] : [])
      : source.evidenceContexts.length ? [] : source.qualifiers
  })
  return [...new Set(values)]
})
</script>

<template>
  <section class="detail-section evidence-section">
    <h3>文献证据 <span class="count">{{ items.length }}</span></h3>
    <p v-if="!items.length" class="muted small">暂无可用证据</p>
    <ul v-else class="evidence-list">
      <li v-for="item in items" :key="item.id">
        <button type="button" class="evidence-button" :aria-expanded="openId === item.id"
          @click="openId = openId === item.id ? '' : item.id">
          <span>{{ item.documentName || item.documentId }}</span>
          <small>{{ item.page === null ? '页码缺失' : '第 ' + item.page + ' 页' }}</small>
        </button>
        <div v-if="openItem?.id === item.id" class="evidence-content">
          <p v-if="item.page === null || !item.quote" class="muted small">暂无可用证据（{{ item.page === null && !item.quote ? '缺少页码和引文' : item.page === null ? '缺少页码' : '缺少引文' }}）</p>
          <blockquote v-if="item.quote">{{ item.quote }}</blockquote>
          <div v-if="qualifiers.length" class="qualifiers">
            <h4>适用条件</h4>
            <p v-for="qualifier in qualifiers" :key="qualifier">{{ qualifier }}</p>
          </div>
          <small class="muted">{{ item.originalEvidenceId }}</small>
        </div>
      </li>
    </ul>
  </section>
</template>
