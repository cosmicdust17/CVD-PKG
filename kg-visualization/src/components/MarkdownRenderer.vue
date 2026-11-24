<script setup lang="ts">
import { computed } from 'vue'
import type { Source } from '../utils/healthApi'
import { citationNumber, legacyMarkdown, renderHealthMarkdown } from '../utils/healthMarkdown'

const props = defineProps<{ markdown?: string; legacy?: string; sources: Source[] }>()
const emit = defineEmits<{ citation: [id: string] }>()
const html = computed(() => renderHealthMarkdown(props.markdown ?? legacyMarkdown(props.legacy ?? ''), props.sources))

function selectCitation(event: MouseEvent) {
  const button = (event.target as HTMLElement).closest<HTMLButtonElement>('button[data-citation]')
  if (!button) return
  const number = Number(button.dataset.citation)
  const source = props.sources.find((item, index) => citationNumber(item, index) === number)
  if (source) emit('citation', source.id)
}
</script>

<template>
  <div class="health-answer ai-markdown" @click="selectCitation" v-html="html"/>
</template>
