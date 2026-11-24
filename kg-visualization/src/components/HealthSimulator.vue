<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, shallowRef, watch } from 'vue'
import type { indexGraph } from '../utils/graphFilter'
import { api, emptyHealthGraph, factors, saveLocal, staticDemo, stored, type Factor, type HistoryItem,
  type Lifestyle, type Simulation, type Source } from '../utils/healthApi'
import { describeLevel, levelControls, lifestyleFactors, mapLevels, referenceLevels, restoreLevels,
  type Levels } from '../utils/lifestyleLevels'
import { demoScenario } from '../utils/demoGraph'
import HealthEvidence from './HealthEvidence.vue'
import HealthGraph from './HealthGraph.vue'
import HealthRisk from './HealthRisk.vue'
import MarkdownRenderer from './MarkdownRenderer.vue'

const props = defineProps<{ index: ReturnType<typeof indexGraph>; launch: URLSearchParams }>()
const graphDelay = 400
const explanationDelay = 1000
const historyStorage = 'hfkg:simulator-levels'
const levels = ref<Levels>({ ...referenceLevels })
const currentScenario = computed(() => mapLevels(levels.value))
const scenarioKey = computed(() => JSON.stringify(currentScenario.value))
const neutral = computed(() => scenarioKey.value === '{}')
const graphResults = new Map<string, Promise<Simulation>>()
const explanations = new Map<string, Promise<Simulation>>()
const displayed = shallowRef<{ key: string; data: Simulation }>()
const explained = shallowRef<{ key: string; data: Simulation }>()
const apiResult = computed(() => displayed.value?.key === scenarioKey.value ? displayed.value.data : undefined)
const result = computed(() => staticDemo && !neutral.value ? demoScenario(props.index, currentScenario.value) : apiResult.value)
const explanation = computed(() => explained.value?.key === scenarioKey.value ? explained.value.data : undefined)
const evidence = computed(() => explanation.value ?? apiResult.value)
const graphError = ref('')
const explanationError = ref('')
const busy = computed(() => !neutral.value && !result.value && !graphError.value)
const explaining = computed(() => !neutral.value && !explanation.value && !explanationError.value)
const history = ref<HistoryItem[]>([])
const highlight = ref<Source>()
const evidencePanel = ref<InstanceType<typeof HealthEvidence>>()
const scenarioName = ref('')
const historyError = ref('')
const status = ref('')
let graphTimer: ReturnType<typeof setTimeout>
let explanationTimer: ReturnType<typeof setTimeout>
let mounted = true
let restoreRevision = 0

function setLevel(factor: Factor, event: Event) {
  const { valueAsNumber } = event.target as HTMLInputElement
  levels.value = { ...levels.value, [factor]: valueAsNumber }
}

function resetConditions() {
  levels.value = { ...referenceLevels }
}

const edgeLabels = computed(() => {
  const data = result.value
  if (!data) return []
  const names = new Map(data.graph.nodes.map(node => [node.id, node.name]))
  const relations = new Map(data.graph.edges.map(edge => [edge.id, edge]))
  return data.graph.paths.slice(0, 8).map(path => path.edges.map(id => {
    const edge = relations.get(id)!
    return names.get(edge.source) + (edge.directed ? ' → ' : ' ↔ ') + names.get(edge.target) + '（' + edge.label + '）'
  }).join('；'))
})

function getSimulation(key: string, scenario: Lifestyle, explain: boolean) {
  const cache = explain ? explanations : graphResults
  const previous = cache.get(key)
  if (previous) return previous
  const request = api<Simulation>('simulator/evaluate', { lifestyle: {}, compare_with: scenario, explain })
    .catch(error => {
      cache.delete(key)
      throw error
    })
  cache.set(key, request)
  return request
}

async function updateSimulation(key: string, scenario: Lifestyle, explain: boolean) {
  const error = explain ? explanationError : graphError
  try {
    const data = await getSimulation(key, scenario, explain)
    if (!mounted || scenarioKey.value !== key) return
    if (explain) {
      explained.value = { key, data }
      return
    }
    const previous = displayed.value?.data
    const sameGraph = previous && JSON.stringify(previous.graph) === JSON.stringify(data.graph)
    if (sameGraph) {
      data.graph = previous.graph
      if (data.added_edge_ids.join() === previous.added_edge_ids.join()) data.added_edge_ids = previous.added_edge_ids
      if (data.removed_edge_ids.join() === previous.removed_edge_ids.join()) data.removed_edge_ids = previous.removed_edge_ids
    }
    displayed.value = { key, data }
  } catch (cause) {
    if (mounted && scenarioKey.value === key) error.value = String(cause)
  }
}

watch(levels, () => {
  clearTimeout(graphTimer)
  clearTimeout(explanationTimer)
  if (staticDemo) return
  if (neutral.value) {
    displayed.value = undefined
    highlight.value = undefined
    return
  }
  const key = scenarioKey.value
  const scenario = currentScenario.value
  if (displayed.value?.key !== key) {
    highlight.value = undefined
    graphError.value = ''
    graphTimer = setTimeout(() => void updateSimulation(key, scenario, false), graphDelay)
  }
  if (explained.value?.key !== key) {
    explanationError.value = ''
    explanationTimer = setTimeout(() => void updateSimulation(key, scenario, true), explanationDelay)
  }
})

async function loadHistory() {
  history.value = await api<HistoryItem[]>('simulator/history')
}

async function saveScenario() {
  if (neutral.value) return
  historyError.value = ''
  status.value = ''
  const snapshot = { ...levels.value }
  try {
    const saved = await api<HistoryItem>('simulator/history', {
      lifestyle: {}, compare_with: mapLevels(snapshot), title: scenarioName.value.trim() || '生活方式场景',
    })
    saveLocal(historyStorage, { ...stored<Record<string, Levels>>(historyStorage, {}), [saved.id]: snapshot })
    scenarioName.value = ''
    await loadHistory()
    status.value = '已保存场景。'
  } catch (cause) { historyError.value = String(cause) }
}

async function restore(id: string) {
  const revision = ++restoreRevision
  const previous = levels.value
  historyError.value = ''
  status.value = ''
  try {
    const saved = await api<HistoryItem>('simulator/history/' + id)
    if (revision !== restoreRevision || levels.value !== previous) return
    const snapshots = stored<Record<string, Levels>>(historyStorage, {})
    levels.value = restoreLevels(saved.compare_with ?? saved.lifestyle, snapshots[id])
    status.value = '已加载为当前场景。'
  } catch (cause) { historyError.value = String(cause) }
}

async function deleteScenario(id: string) {
  historyError.value = ''
  status.value = ''
  try {
    await api<void>('simulator/history/' + id, undefined, 'DELETE')
    const snapshots = stored<Record<string, Levels>>(historyStorage, {})
    delete snapshots[id]
    saveLocal(historyStorage, snapshots)
    await loadHistory()
  } catch (cause) { historyError.value = String(cause) }
}

function detectiveLink(focus: Simulation['focus'][number]) {
  const params = new URLSearchParams({ q: focus.question })
  for (const node of focus.entity_ids) params.append('entity', node)
  const paths = result.value?.graph.paths.filter(p => p.nodes.some(n => focus.entity_ids.includes(n))) ?? []
  for (const edge of [...new Set(paths.flatMap(path => path.edges))].slice(0, 12)) params.append('edge', edge)
  return '#detective?' + params
}

function showSource(id: string) {
  highlight.value = evidence.value?.evidence.find(item => item.id === id)
  if (highlight.value) void evidencePanel.value?.openSource(id)
}

onMounted(() => {
  const topic = props.launch.getAll('factor').find(factor => Object.hasOwn(factors, factor))
  if (topic) document.getElementById('level-' + topic)?.focus({ preventScroll: true })
  if (!staticDemo) void loadHistory().catch(cause => { historyError.value = String(cause) })
})

onUnmounted(() => {
  mounted = false
  clearTimeout(graphTimer)
  clearTimeout(explanationTimer)
})
</script>

<template>
  <main class="page health-page simulator-page">
    <header class="intro">
      <div><h1>健康生活方式模拟器</h1><p>探索不同生活习惯与心血管健康之间的联系。</p></div>
      <a class="button simulator-detective-link" href="#detective">进入 AI 健康知识侦探 <span aria-hidden="true">↗</span></a>
    </header>
    <div class="health-workspace simulator-layout">
      <section class="card health-panel simulator-controls" aria-label="条件设置">
        <h2>生活方式调节</h2>
        <p id="level-guide" class="muted">50% 是本次模拟的中性参考。百分比表示滑块位置，用于探索生活方式情景。</p>
        <div class="scenario-form">
          <fieldset v-for="key in lifestyleFactors" :key="key" class="scenario-factor">
            <legend>{{ factors[key] }}</legend>
            <label :for="'level-' + key" class="scenario-goal">{{ levelControls[key].goal }}</label>
            <div :id="'ends-' + key" class="scenario-endpoints">
              <span>{{ levelControls[key].ends[0] }}</span><span>{{ levelControls[key].ends[1] }}</span>
            </div>
            <input :id="'level-' + key" class="scenario-slider" type="range" min="0" max="100" step="1"
              :value="levels[key]" :aria-describedby="'ends-' + key + ' level-guide'"
              :aria-valuetext="levels[key] + '%，' + describeLevel(key, levels[key])"
              :style="{ '--slider-progress': levels[key] + '%' }" @input="setLevel(key, $event)">
            <div class="scenario-reading">
              <strong>{{ levels[key] }}%</strong><span>{{ describeLevel(key, levels[key]) }}</span>
            </div>
          </fieldset>
          <div class="health-actions scenario-submit">
            <button class="button" type="button" @click="resetConditions">重置条件</button>
          </div>
        </div>
        <p v-if="staticDemo" class="muted">历史场景保存服务未连接。</p>
        <details v-else>
          <summary>历史场景</summary>
          <form class="health-form" @submit.prevent="saveScenario">
            <label class="health-field">场景名称<input v-model="scenarioName" maxlength="150" placeholder="生活方式场景"></label>
            <button class="button" :disabled="neutral">保存场景</button>
          </form>
          <ul class="history-list">
            <li v-for="item in history" :key="item.id" class="health-actions">
              <button type="button" class="plain-action" @click="restore(item.id)">{{ item.title }}</button>
              <button type="button" class="button" :aria-label="'删除 ' + item.title" @click="deleteScenario(item.id)">删除</button>
            </li>
          </ul>
          <p v-if="historyError" role="alert">{{ historyError }}</p>
          <p v-if="status" class="muted" role="status">{{ status }}</p>
        </details>
      </section>
      <section class="card health-panel scenario-comparison" aria-label="场景比较">
        <div class="scenario-comparison-header">
          <h2>场景对比</h2>
          <p v-if="neutral" class="muted">移动滑块后，场景对比和关联知识会自动更新。</p>
          <p v-else-if="busy" class="muted" role="status">正在更新当前场景的关联知识和图谱…</p>
          <p v-else-if="graphError" role="alert">{{ graphError }}</p>
        </div>
        <table class="scenario-table">
          <colgroup><col class="scenario-factor-column"><col class="scenario-before-column"><col></colgroup>
          <thead><tr><th scope="col">生活方式</th><th scope="col">原始场景</th><th scope="col">当前场景</th></tr></thead>
          <tbody>
            <tr v-for="key in lifestyleFactors" :key="key">
              <th scope="row">{{ factors[key] }}</th>
              <td>{{ referenceLevels[key] }}%</td>
              <td :class="{ 'scenario-changed': levels[key] !== referenceLevels[key] }">
                <div class="scenario-table-value"><strong>{{ levels[key] }}%</strong><span>{{ describeLevel(key, levels[key]) }}</span></div>
              </td>
            </tr>
          </tbody>
        </table>
        <template v-if="result">
          <div class="scenario-findings">
            <section class="health-stack">
              <h3>危险因素</h3>
              <dl>
                <div><dt>原始</dt><dd>{{ result.baseline.risk_factors.join('、') || '无适用路径' }}</dd></div>
                <div><dt>当前</dt><dd>{{ result.modified.risk_factors.join('、') || '无适用路径' }}</dd></div>
              </dl>
            </section>
            <section class="health-stack">
              <h3>关联疾病</h3>
              <dl>
                <div><dt>原始</dt><dd>{{ result.baseline.related_diseases.join('、') || '无适用路径' }}</dd></div>
                <div><dt>当前</dt><dd>{{ result.modified.related_diseases.join('、') || '无适用路径' }}</dd></div>
              </dl>
            </section>
            <section v-if="!staticDemo" class="health-stack scenario-prevention">
              <h3>文献中的预防方向</h3>
              <button v-for="item in result.recommendations" :key="item.factor" class="plain-action" type="button"
                @click="showSource(item.evidence_id)">{{ item.title }} · 查看依据</button>
              <p v-if="!result.recommendations.length" class="muted">当前摘录中未找到适用于所选条件的明确建议。</p>
            </section>
          </div>
          <details v-if="edgeLabels.length" class="scenario-paths">
            <summary>查看关联路径（{{ edgeLabels.length }}）</summary>
            <ul><li v-for="path in edgeLabels" :key="path">{{ path }}</li></ul>
          </details>
          <section v-if="result.focus.length" class="health-stack scenario-deep-dive">
            <h3>深入了解</h3>
            <a v-for="focus in result.focus" :key="focus.factor" :href="detectiveLink(focus)">{{ focus.question }}</a>
          </section>
          <div class="scenario-limitations"><p v-for="line in result.limitations" :key="line" class="muted">{{ line }}</p></div>
        </template>
      </section>
      <HealthGraph :graph="result?.graph ?? displayed?.data.graph ?? emptyHealthGraph" :index="index" :highlighted="highlight"
        :removed="result?.removed_edge_ids ?? displayed?.data.removed_edge_ids"
        :added="result?.added_edge_ids ?? displayed?.data.added_edge_ids" fixed-label-size>
        <p v-if="displayed && !result" class="muted" role="status">正在显示上一场景的关联图谱。</p>
      </HealthGraph>
    </div>
    <section v-if="staticDemo" class="card health-panel">
      <h2>AI 解释与风险评分</h2>
      <p role="status">AI 解释、RAGFlow 文献检索及风险评分服务未连接。当前场景仅展示图谱中已有的知识关系。</p>
    </section>
    <div v-else-if="!neutral" class="health-explanation">
      <section class="card health-panel">
        <h2>AI 解释</h2>
        <p v-if="explaining" class="muted" role="status">正在根据当前场景更新解释…</p>
        <p v-else-if="explanationError" role="alert">{{ explanationError }}</p>
        <MarkdownRenderer v-else-if="explanation" :markdown="explanation.answer_markdown" :legacy="explanation.explanation"
          :sources="explanation.evidence" @citation="showSource"/>
      </section>
      <HealthEvidence v-if="evidence" ref="evidencePanel" :items="evidence.evidence" :status="evidence.evidence_status" :active="highlight?.id"
        @highlight="source => highlight = source"/>
    </div>
    <HealthRisk v-if="!staticDemo"/>
  </main>
</template>
