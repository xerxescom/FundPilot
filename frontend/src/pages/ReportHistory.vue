<template>
  <div>
    <div class="toolbar panel">
      <el-select v-model="selectedId" placeholder="选择日报" style="min-width: 420px">
        <el-option
          v-for="item in reports"
          :key="item.id"
          :label="`${item.id} - ${item.created_at.slice(0, 16)} - ${item.model_name}`"
          :value="item.id"
        />
      </el-select>
    </div>
    <ReportCard v-if="selectedReport" class="section" :report="selectedReport" />
    <div v-if="selectedReport?.input_snapshot" class="section panel">
      <h2 class="section-title">输入数据摘要</h2>
      <pre class="json-box">{{ prettySnapshot }}</pre>
    </div>
    <el-empty v-if="!reports.length" description="暂无历史日报" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import { api } from "../api/fundpilot";
import type { Report } from "../api/types";
import ReportCard from "../components/ReportCard.vue";

const reports = ref<Report[]>([]);
const selectedId = ref<number>();
const selectedReport = computed(() => reports.value.find((item) => item.id === selectedId.value));
const prettySnapshot = computed(() => {
  if (!selectedReport.value?.input_snapshot) return "";
  try {
    return JSON.stringify(JSON.parse(selectedReport.value.input_snapshot), null, 2);
  } catch {
    return selectedReport.value.input_snapshot;
  }
});

onMounted(async () => {
  reports.value = await api.reportHistory();
  selectedId.value = reports.value[0]?.id;
});
</script>

<style scoped>
.json-box {
  max-height: 460px;
  overflow: auto;
}
</style>
