<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import HealthDetective from './components/HealthDetective.vue'
import HealthSimulator from './components/HealthSimulator.vue'
import './health.css'
import GraphCanvas from './components/GraphCanvas.vue'
import GraphToolbar from './components/GraphToolbar.vue'
import GraphLegend from './components/GraphLegend.vue'
import EntityDetail from './components/EntityDetail.vue'
import { staticDemo } from './utils/healthApi'
import { useKnowledgeGraph } from './composables/useKnowledgeGraph'

const { index, metadata, center, expanded, filters, mode, selection, view, current,
  loading, error, resetSequence, layer, overviewTooLarge, start, reset, selectNode, collapse, setMode } = useKnowledgeGraph()
const canvas = ref<InstanceType<typeof GraphCanvas>>()
const locationHash = ref(window.location.hash.slice(1))
const [page, launch] = [computed(() => locationHash.value.split('?')[0]),
  computed(() => new URLSearchParams(locationHash.value.split('?')[1]))]
const updateLocation = () => { locationHash.value = window.location.hash.slice(1) }
onMounted(() => window.addEventListener('hashchange', updateLocation))
onUnmounted(() => window.removeEventListener('hashchange', updateLocation))

function selectEdge(id: string) {
  if (!view.value.edges.some(edge => edge.id === id) && current.value.node) {
    selectNode(current.value.node.id)
  }
  selection.value = { kind: 'edge', id }
}
</script>

<template>
  <header class="site-header">
    <div class="site-inner">
      <div class="brand-mark" aria-hidden="true"><i/><i/><i/></div>
      <span>心血管疾病预防知识图谱</span>
      <nav class="health-nav" aria-label="主导航">
        <a href="#graph" :aria-current="page !== 'detective' && page !== 'simulator' ? 'page' : undefined">知识图谱探索</a>
        <a href="#detective" :aria-current="page === 'detective' ? 'page' : undefined">AI 健康知识侦探</a>
        <a href="#simulator" :aria-current="page === 'simulator' ? 'page' : undefined">健康生活方式模拟器</a>
      </nav>
    </div>
  </header>
  <div v-if="staticDemo" class="page">
    <p class="card notice">在线演示模式 · 图谱探索和场景对比在浏览器中运行。AI 问答、文献检索和风险评分需连接本地后端。</p>
  </div>
  <HealthDetective v-if="page === 'detective'" :key="locationHash" :index="index" :launch="launch"/>
  <HealthSimulator v-else-if="page === 'simulator'" :key="locationHash" :index="index" :launch="launch"/>
  <main v-else class="page">
    <div class="intro">
      <div>
        <h1>知识图谱探索</h1>
        <p>探索心血管疾病、危险因素与健康指标之间的知识关联。</p>
      </div>
      <dl v-if="metadata" class="totals" aria-label="数据总览">
        <div><dt>实体</dt><dd>{{ metadata.entityCount }}</dd></div>
        <div><dt>关系</dt><dd>{{ metadata.relationCount }}</dd></div>
        <div><dt>来源文献</dt><dd>{{ metadata.documentCount }}</dd></div>
      </dl>
    </div>
    <div v-if="loading || error" class="card notice" :role="error ? 'alert' : 'status'">{{ error || '正在读取三份文献的图谱数据…' }}</div>
    <div v-else-if="!index.ranked.length" class="card notice" role="status">图谱数据中暂无可探索的实体。</div>
    <div v-else class="workspace">
      <GraphToolbar v-model="filters" :index="index" :center="center" @start="start" @reset="reset"/>
      <section class="card graph-card" aria-label="图谱画布">
        <div class="canvas-toolbar">
          <div class="mode-switch" aria-label="图谱模式">
            <button type="button" :aria-pressed="mode === 'explore'" @click="setMode('explore')">逐层探索</button>
            <button type="button" :aria-pressed="mode === 'overview'" @click="setMode('overview')">全图概览</button>
          </div>
          <div class="canvas-controls" aria-label="画布操作">
            <button type="button" class="icon-button" title="缩小" aria-label="缩小" @click="canvas?.zoom(0.8)">−</button>
            <button type="button" class="icon-button" title="放大" aria-label="放大" @click="canvas?.zoom(1.25)">+</button>
            <button type="button" class="button fit-button" @click="canvas?.fit()">适配画布</button>
          </div>
        </div>
        <div class="canvas-wrapper">
          <GraphCanvas ref="canvas" :view="view" :center="center" :mode="mode" :sequence="resetSequence"
            :selected="current.node || current.edge ? selection : undefined" @node="selectNode" @edge="selectEdge"/>
          <div v-if="mode === 'overview' && overviewTooLarge" class="canvas-message" role="status">
            当前图谱超过概览容量，请按实体或关系类型缩小范围。
          </div>
          <div v-else-if="!view.nodes.length" class="canvas-message" role="status">当前筛选条件下暂无结果。</div>
          <div v-else-if="mode === 'explore' && view.nodes.length === 1" class="canvas-help">
            {{ expanded.has(center) ? '当前条件下无其他关联实体' : '点击实体，展开直接关联' }}
          </div>
        </div>
        <div class="canvas-footer">
          <GraphLegend :types="index.entityTypes" :undirected="[...index.edges.values()].some(edge => !edge.directed)"/>
          <div class="live-counts" aria-live="polite" aria-label="当前画布统计">
            <span>{{ view.nodes.length }} 节点</span><span>{{ view.edges.length }} 关系</span>
            <span v-if="mode === 'explore'">第 {{ layer }} 层</span>
          </div>
        </div>
      </section>
      <EntityDetail :index="index" :view="view" :filters="filters" :center="center" :mode="mode"
        :node="current.node" :edge="current.edge" :expanded="!!current.node && expanded.has(current.node.id)"
        @expand="selectNode" @collapse="collapse" @edge="selectEdge"/>
    </div>
  </main>
</template>
