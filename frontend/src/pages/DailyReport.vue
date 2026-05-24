<template>
  <div>
    <div class="toolbar panel">
      <el-button type="primary" @click="generate">生成每日简报</el-button>
      <el-button @click="checkOllama">测试 Ollama 连接</el-button>
    </div>
    <div v-if="ollamaStatus" class="section panel">
      <el-table :data="statusRows" border stripe>
        <el-table-column prop="项目" label="项目" />
        <el-table-column prop="值" label="值" min-width="220" />
      </el-table>
    </div>
    <div v-if="report" class="section">
      <ReportCard :report="report" />
    </div>
    <el-empty v-else class="section" description="暂无简报" />
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from "element-plus";
import { computed, onMounted, ref } from "vue";

import { api } from "../api/fundpilot";
import { fieldLabel } from "../api/labels";
import type { Report } from "../api/types";
import ReportCard from "../components/ReportCard.vue";

const report = ref<Report | null>(null);
const ollamaStatus = ref<Record<string, unknown> | null>(null);
const statusRows = computed(() =>
  Object.entries(ollamaStatus.value || {}).map(([key, value]) => ({
    项目: fieldLabel(key),
    值: Array.isArray(value) ? value.join("、") : String(value),
  })),
);

async function loadLatest() {
  report.value = await api.latestReport().catch(() => null);
}

async function generate() {
  report.value = await api.generateDailyReport();
  ElMessage.success("已生成每日简报");
}

async function checkOllama() {
  ollamaStatus.value = (await api.ollamaStatus()) as Record<string, unknown>;
}

onMounted(loadLatest);
</script>
