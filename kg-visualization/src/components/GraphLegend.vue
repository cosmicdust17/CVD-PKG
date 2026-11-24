<script setup lang="ts">
import { colorFor } from '../utils/graphTransform'

defineProps<{ types: string[]; undirected: boolean }>()
</script>

<template>
  <div class="legend" aria-label="图例">
    <span v-for="type in types" :key="type" class="legend-item">
      <i class="type-dot" :style="{ background: colorFor(type).fill }"/>{{ type }}
    </span>
    <span class="legend-item" v-if="undirected"><i class="dash-sample"/>无向关系</span>
  </div>
</template>
