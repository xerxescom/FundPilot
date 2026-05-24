<template>
  <div>
    <div class="metric-grid">
      <MetricCard label="待计算指标" :value="health?.pending_indicator_count ?? 0" />
      <MetricCard label="需关注数据" :value="health?.stale_fund_count ?? 0" />
      <MetricCard label="净值断档" :value="health?.gap_count ?? 0" />
      <MetricCard label="任务数量" :value="tasks.length" />
    </div>
    <div class="section panel">
      <h2 class="section-title">快捷任务</h2>
      <div class="toolbar">
        <el-button type="primary" @click="run('sync_watchlist_nav')">同步自选净值</el-button>
        <el-button type="primary" @click="run('calc_indicators')">计算全部指标</el-button>
        <el-button type="primary" @click="run('calc_scores')">计算全部评分</el-button>
        <el-button type="primary" @click="run('generate_alerts')">生成风险预警</el-button>
        <el-button @click="run('sync_market_context')">同步市场数据</el-button>
        <el-button @click="run('generate_daily_report')">生成每日简报</el-button>
      </div>
      <TaskResultTable v-if="result" :result="result" />
    </div>
    <div class="section panel">
      <h2 class="section-title">按名称触发任务</h2>
      <div class="toolbar">
        <el-select v-model="selectedTask" style="min-width: 360px">
          <el-option
            v-for="item in tasks"
            :key="item.task_name"
            :label="`${item.description}（${item.task_name}）`"
            :value="item.task_name"
          />
        </el-select>
        <el-button @click="run(selectedTask)">运行选中任务</el-button>
      </div>
    </div>
    <div class="section panel">
      <h2 class="section-title">最近任务日志</h2>
      <AutoTable :rows="logs" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";

import { api } from "../api/fundpilot";
import type { DataHealth } from "../api/types";
import AutoTable from "../components/AutoTable.vue";
import MetricCard from "../components/MetricCard.vue";
import TaskResultTable from "../components/TaskResultTable.vue";

const health = ref<DataHealth | null>(null);
const tasks = ref<Array<{ task_name: string; description: string }>>([]);
const selectedTask = ref("");
const logs = ref<Array<Record<string, unknown>>>([]);
const result = ref<unknown>();

async function load() {
  const [healthData, taskData, logData] = await Promise.all([api.dataHealth(), api.availableTasks(), api.taskLogs()]);
  health.value = healthData;
  tasks.value = taskData;
  logs.value = logData as Array<Record<string, unknown>>;
  selectedTask.value ||= tasks.value[0]?.task_name || "";
}

async function run(task: string) {
  if (!task) return;
  result.value = await api.runTask(task);
  await load();
}

onMounted(load);
</script>
