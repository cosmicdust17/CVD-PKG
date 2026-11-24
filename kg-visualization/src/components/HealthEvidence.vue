<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { sourceUrl, type Source } from '../utils/healthApi'
import { citationNumber, displayExcerpt } from '../utils/healthMarkdown'

defineProps<{ items: Source[]; status?: string; active?: string }>()
const emit = defineEmits<{ highlight: [source: Source] }>()
const panel = ref<HTMLElement>()

async function openSource(id: string) {
  await nextTick()
  const card = panel.value?.querySelector<HTMLDetailsElement>('details[data-source-id="' + CSS.escape(id) + '"]')
  if (!card) return
  card.open = true
  card.scrollIntoView({ block: 'nearest' })
  card.querySelector('summary')?.focus({ preventScroll: true })
}

defineExpose({ openSource })
</script>

<template>
  <aside ref="panel" class="card health-panel" aria-label="知识依据">
    <h2>知识依据</h2>
    <p v-if="status" class="muted" role="status">{{ status }}</p>
    <p v-if="!items.length" class="muted">暂无可显示的文献片段。</p>
    <ol v-else class="health-sources">
      <li v-for="(item, index) in items" :key="item.id" :class="{ 'source-active': active === item.id }">
        <details :data-source-id="item.id" @toggle="($event.target as HTMLDetailsElement).open && emit('highlight', item)">
          <summary class="source-summary">
            <span class="source-reference">[{{ citationNumber(item, index) }}]</span>
            <span class="source-title">{{ item.document_name || '文档未命名' }}</span>
            <span class="source-meta">{{ item.source }}<span v-if="item.page != null"> · PDF 第 {{ item.page }} 页</span></span>
          </summary>
          <div class="source-content">
            <p class="source-meta">原文摘录</p>
            <blockquote>{{ displayExcerpt(item.quote) }}</blockquote>
            <p class="source-meta">原始证据标识 {{ item.chunk_id }}</p>
            <p v-if="item.relevance != null" class="source-meta">相关度 {{ item.relevance.toFixed(2) }}</p>
            <a v-if="sourceUrl(item)" :href="sourceUrl(item)" target="_blank" rel="noopener">打开原始 PDF</a>
          </div>
        </details>
      </li>
    </ol>
  </aside>
</template>
