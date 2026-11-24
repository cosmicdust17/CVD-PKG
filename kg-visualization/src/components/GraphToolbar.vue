<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Filters } from '../types/graph'
import { searchEntities, type GraphIndex } from '../utils/graphFilter'
import { colorFor } from '../utils/graphTransform'

const props = defineProps<{ index: GraphIndex; center: string }>()
const filters = defineModel<Filters>({ required: true })
const emit = defineEmits<{ start: [id: string]; reset: [] }>()
const query = ref('')
const matches = computed(() => searchEntities(props.index.ranked, query.value, filters.value.entity))
const recommendations = computed(() => props.index.ranked.filter(node =>
  !filters.value.entity || node.entityType === filters.value.entity).slice(0, 5))

function choose(id: string) {
  query.value = ''
  emit('start', id)
}
</script>

<template>
  <aside class="card sidebar" aria-label="图谱筛选">
    <div class="panel-heading">
      <h2>探索工具</h2>
    </div>
    <div class="sidebar-body">
      <label class="field">
        <span>搜索实体</span>
        <input v-model="query" type="search" placeholder="输入名称或别名"
          @keydown.enter.prevent="matches[0] && choose(matches[0].id)">
      </label>
      <div v-if="query.trim()" class="search-results" aria-label="搜索结果">
        <p v-if="!matches.length" class="muted small">未找到匹配实体</p>
        <button v-for="node in matches" :key="node.id" type="button" class="search-result" @click="choose(node.id)">
          <span>{{ node.name }}</span><small>{{ node.entityType }}</small>
        </button>
      </div>
      <div class="field">
        <label for="kg-entity-type">实体类型</label>
        <select id="kg-entity-type" :value="filters.entity" @change="filters = { ...filters, entity: ($event.target as HTMLSelectElement).value }">
          <option value="">全部实体类型</option>
          <option v-for="type in index.entityTypes" :key="type">{{ type }}</option>
        </select>
      </div>
      <div class="field">
        <label for="kg-relation-type">关系类型</label>
        <select id="kg-relation-type" :value="filters.relation" @change="filters = { ...filters, relation: ($event.target as HTMLSelectElement).value }">
          <option value="">全部关系类型</option>
          <option v-for="type in index.relationTypes" :key="type">{{ type }}</option>
        </select>
      </div>
      <div class="recommendations">
        <h3>推荐探索入口</h3>
        <button v-for="node in recommendations" :key="node.id" type="button" class="recommendation"
          :aria-current="node.id === center ? 'true' : undefined" @click="choose(node.id)">
          <span class="type-dot" :style="{ background: colorFor(node.entityType).fill }"/>
          <span class="recommendation-name">{{ node.name }}</span>
          <small>{{ index.adjacent.get(node.id)?.length ?? 0 }} 条</small>
        </button>
      </div>
      <button type="button" class="button reset-button" @click="query = ''; emit('reset')" :disabled="!index.ranked.length">
        重置探索
      </button>
    </div>
  </aside>
</template>
