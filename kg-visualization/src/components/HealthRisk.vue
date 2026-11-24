<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { api, type RiskResult } from '../utils/healthApi'

const form = reactive({ age: '', sbp: '', total_chol: '', sex: '', region: '', smoker: '', diabetes: '', prior_cvd: '' })
const boolFields = { smoker: '目前吸烟', diabetes: '糖尿病', prior_cvd: '已有心血管病史' } as const
const result = ref<RiskResult>()
const error = ref('')
const pending = ref(false)
watch(form, () => { result.value = undefined; error.value = '' })
async function calculate() {
  pending.value = true
  error.value = ''
  result.value = undefined
  try {
    result.value = await api<RiskResult>('simulator/risk-assessment', {
      ...form, age: Number(form.age), sbp: Number(form.sbp), total_chol: Number(form.total_chol),
      smoker: form.smoker === 'yes', diabetes: form.diabetes === 'yes', prior_cvd: form.prior_cvd === 'yes',
    })
  } catch (cause) {
    error.value = String(cause)
  } finally { pending.value = false }
}
</script>

<template>
  <details class="card health-panel health-section">
    <summary>可选 · 心血管风险评分</summary>
    <p class="muted">WHO 2019 东亚实验室版适用于 40–79 岁、无既往心血管病的成人。此处使用另行填写的实际指标。</p>
    <form class="risk-form" @submit.prevent="calculate">
      <fieldset :disabled="pending" class="risk-fields">
        <label class="health-field">地区<select v-model="form.region" required><option value="">请选择</option><option value="china_mainland">中国大陆</option></select></label>
        <label class="health-field">年龄<input v-model="form.age" type="number" required min="40" max="79"></label>
        <label class="health-field">模型性别变量<select v-model="form.sex" required><option value="">请选择</option><option value="male">男</option><option value="female">女</option></select></label>
        <label class="health-field">收缩压（mmHg）<input v-model="form.sbp" type="number" required min="70" max="250" step="any"></label>
        <label class="health-field">总胆固醇（mmol/L）<input v-model="form.total_chol" type="number" required min="2" max="15" step="any"></label>
        <label v-for="(label, key) in boolFields" :key="key" class="health-field">{{ label }}
          <select v-model="form[key]" required><option value="">请选择</option><option value="yes">是</option><option value="no">否</option></select>
        </label>
      </fieldset>
      <button type="submit" class="button health-primary" :disabled="pending">计算风险</button>
    </form>
    <p v-if="error" role="alert">{{ error }}</p>
    <div v-if="result" class="risk-result" aria-live="polite">
      <strong>{{ result.result_percent }}{{ result.unit }}</strong>
      <p>{{ result.outcome }}</p>
      <p>{{ result.model }} · PyCVDRisk {{ result.package_version }} · {{ result.region }}</p>
      <p>{{ result.population }}</p>
      <ul><li v-for="line in result.limitations" :key="line">{{ line }}</li></ul>
      <a :href="result.citation" target="_blank" rel="noopener">查看 WHO 2019 原始研究</a>
    </div>
  </details>
</template>
