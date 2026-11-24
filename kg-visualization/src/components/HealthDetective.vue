<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import type { indexGraph } from '../utils/graphFilter'
import { api, emptyHealthGraph, staticDemo, saveLocal, stored, type ChatReply, type Context, type Source } from '../utils/healthApi'
import HealthEvidence from './HealthEvidence.vue'
import HealthGraph from './HealthGraph.vue'
import MarkdownRenderer from './MarkdownRenderer.vue'
import { legacyMarkdown, shortSummary } from '../utils/healthMarkdown'

const props = defineProps<{ index: ReturnType<typeof indexGraph>; launch: URLSearchParams }>()
const examples = [
  '什么是高血压？', '高盐饮食为什么会影响血压？', '长期缺乏运动可能带来哪些健康影响？',
  '吸烟与心血管疾病有什么关系？', '高血压与冠心病之间有什么联系？',
  '有哪些生活方式有助于预防心血管疾病？',
]
interface Turn { question: string; reply?: ChatReply }
interface Thread { id: string; title: string; turns: Turn[]; updatedAt?: string }
const cacheKey = 'hfkg:conversations'
const threads = ref(stored<Thread[]>(cacheKey, []))
const activeId = ref(threads.value[0]?.id ?? '')
const side = ref<ChatReply>()
const current = computed(() => threads.value.find(thread => thread.id === activeId.value))
const input = ref('')
const pending = ref(false)
const error = ref('')
const highlight = ref<Source>()
const evidencePanel = ref<InstanceType<typeof HealthEvidence>>()
const historyThreads = computed(() => [...threads.value].sort((a, b) => (b.updatedAt ?? '').localeCompare(a.updatedAt ?? '')))
const historyDate = new Intl.DateTimeFormat('zh-CN', { dateStyle: 'short', timeStyle: 'short' })

function latestSummary(thread: Thread) {
  const reply = thread.turns.at(-1)?.reply
  return reply ? shortSummary(reply.answer_markdown ?? legacyMarkdown(reply.answer)) : ''
}

function updatedLabel(value?: string) {
  const time = value ? new Date(value) : undefined
  return time && !isNaN(time.getTime()) ? historyDate.format(time) : '更新时间未记录'
}

watch(threads, () => saveLocal(cacheKey, historyThreads.value.slice(0, 15)), { deep: true })
watch(current, thread => {
  side.value = thread?.turns.at(-1)?.reply
  highlight.value = undefined
  error.value = ''
}, { immediate: true })

function newThread() {
  activeId.value = ''
  side.value = undefined
  highlight.value = undefined
  error.value = ''
}
function clear() {
  threads.value = threads.value.filter(thread => thread.id !== activeId.value)
  newThread()
}
function show(reply: ChatReply) {
  side.value = reply
  highlight.value = undefined
}
function openCitation(reply: ChatReply, id: string) {
  show(reply)
  highlight.value = reply.evidence.find(item => item.id === id)
  void evidencePanel.value?.openSource(id)
}

async function ask(question = input.value, context: Context = {}) {
  if (pending.value || !question.trim()) return
  question = question.trim()
  pending.value = true
  error.value = ''
  input.value = ''
  let thread = current.value
  if (!thread) {
    const id = crypto.randomUUID()
    threads.value.unshift({ id, title: question.slice(0, 32), turns: [] })
    activeId.value = id
    thread = threads.value[0]
  }
  const questions = thread.turns.filter(turn => turn.reply).map(turn => turn.question)
  const anchor = questions.reduce((latest, text, i) => /^(那|这|它|还有|如何改善|有哪些可以)/.test(text) ? latest : i, -1)
  const previous = questions.slice(Math.max(anchor, questions.length - 3, 0)).join('；').slice(-1000)
  thread.turns.push({ question })
  const turn = thread.turns[thread.turns.length - 1]
  try {
    const reply = await api<ChatReply>('agent/chat', {
      conversation_id: thread.id, message: question,
      context: { ...context, ...(previous ? { previous_question: previous } : {}) },
    })
    turn.reply = reply
    thread.updatedAt = new Date().toISOString()
    if (thread.turns.length > 12) thread.turns.shift()
    show(reply)
  } catch (cause) {
    thread.turns.pop()
    input.value = question
    error.value = String(cause)
  } finally {
    pending.value = false
  }
}

onMounted(() => {
  if (staticDemo) return
  const question = props.launch.get('q')
  if (!question) return
  newThread()
  void ask(question.slice(0, 1000), {
    entity_ids: props.launch.getAll('entity').slice(0, 8),
    path_edge_ids: props.launch.getAll('edge').slice(0, 12),
  })
})

const simulationLink = computed(() => {
  const params = new URLSearchParams()
  for (const topic of side.value?.topics ?? []) params.append('factor', topic)
  return '#simulator' + (params.size ? '?' + params : '')
})
</script>

<template>
  <main class="page health-page">
    <div class="intro">
      <div><h1>AI 健康知识侦探</h1><p>从你的问题出发，找到图谱关系和文献原文。</p></div>
    </div>
    <div class="health-workspace detective-layout">
      <section class="card health-panel conversation" aria-label="对话">
        <template v-if="staticDemo">
          <h2>对话</h2>
          <p role="status">AI 问答和 RAGFlow 文献检索服务未连接。可在右侧搜索、展开图谱节点，或进入生活方式模拟器。</p>
          <a href="#simulator">进入生活方式模拟器</a>
        </template>
        <template v-else>
          <div class="health-heading">
            <h2>对话</h2>
            <button class="button" type="button" :disabled="pending" @click="newThread">新建对话</button>
          </div>
          <details v-if="threads.length">
            <summary>历史对话</summary>
            <div class="history-list conversation-history">
              <button v-for="thread in historyThreads" :key="thread.id" type="button" class="conversation-history-item"
                :aria-pressed="activeId === thread.id" :disabled="pending" @click="activeId = thread.id">
                <strong>{{ shortSummary(thread.turns.at(-1)?.question || thread.title) }}</strong>
                <time :datetime="thread.updatedAt">{{ updatedLabel(thread.updatedAt) }}</time>
                <span v-if="latestSummary(thread)">{{ latestSummary(thread) }}</span>
              </button>
            </div>
          </details>
          <div v-if="!current?.turns.length" class="health-prompts">
            <button v-for="item in examples" :key="item" type="button" class="button" :disabled="pending" @click="ask(item)">{{ item }}</button>
          </div>
          <div class="conversation-turns" aria-live="polite">
            <article v-for="(turn, i) in current?.turns" :key="i">
              <p class="user-question">{{ turn.question }}</p>
              <template v-if="turn.reply">
                <MarkdownRenderer :markdown="turn.reply.answer_markdown" :legacy="turn.reply.answer" :sources="turn.reply.evidence"
                  @citation="id => turn.reply && openCitation(turn.reply, id)"/>
                <button v-if="turn.reply !== side" class="plain-action" type="button" @click="show(turn.reply)">查看这轮图谱和证据</button>
              </template>
            </article>
          </div>
          <p v-if="pending" role="status" class="muted">正在调查图谱和文献…</p>
          <p v-if="error" role="alert">{{ error }}</p>
          <div v-if="side?.suggested_questions.length" class="health-prompts followups">
            <button v-for="item in side.suggested_questions" :key="item" type="button" class="plain-action"
              :disabled="pending" @click="ask(item)">{{ item }}</button>
            <a :href="simulationLink">试试生活方式模拟</a>
          </div>
          <form class="health-form" @submit.prevent="ask()">
            <label class="health-field">提问或追问
              <textarea v-model="input" rows="2" maxlength="1000" placeholder="输入你想了解的问题"></textarea>
            </label>
            <div class="health-actions">
              <button class="button health-primary" :disabled="pending || !input.trim()">发送</button>
              <button v-if="current" class="button" type="button" :disabled="pending" @click="clear">清空当前对话</button>
            </div>
          </form>
          <details v-if="side?.agent_trace.length">
            <summary>调查步骤</summary>
            <ul><li v-for="step in side.agent_trace" :key="step.agent">{{ step.agent }}<span v-if="step.detail"> · {{ step.detail }}</span></li></ul>
          </details>
        </template>
      </section>
      <HealthGraph :graph="side?.graph ?? emptyHealthGraph" :index="index" :highlighted="highlight"/>
      <HealthEvidence v-if="!staticDemo" ref="evidencePanel" :items="side?.evidence ?? []" :status="side?.evidence_status" :active="highlight?.id"
        @highlight="source => highlight = source"/>
    </div>
  </main>
</template>
