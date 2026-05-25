<template>
  <PageSkeleton v-if="loading && !hasLoadedOnce" />
  <div v-else v-loading="loading || running" :element-loading-text="loadingText">
    <div class="metric-grid">
      <MetricCard label="待计算指标" :value="health?.pending_indicator_count ?? 0" />
      <MetricCard label="需关注数据" :value="health?.stale_fund_count ?? 0" />
      <MetricCard label="净值断档" :value="health?.gap_count ?? 0" />
      <MetricCard label="任务数量" :value="tasks.length" />
    </div>

    <div class="section panel">
      <h2 class="section-title">快捷任务</h2>
      <div class="toolbar">
        <el-button type="primary" :loading="runningTask === 'sync_watchlist_nav'" :disabled="running" @click="run('sync_watchlist_nav')">
          同步自选净值
        </el-button>
        <el-button type="primary" :loading="runningTask === 'calc_indicators'" :disabled="running" @click="run('calc_indicators')">
          计算全部指标
        </el-button>
        <el-button type="primary" :loading="runningTask === 'calc_scores'" :disabled="running" @click="run('calc_scores')">
          计算全部评分
        </el-button>
        <el-button type="primary" :loading="runningTask === 'generate_alerts'" :disabled="running" @click="run('generate_alerts')">
          生成风险预警
        </el-button>
        <el-button :loading="runningTask === 'sync_market_context'" :disabled="running" @click="run('sync_market_context')">
          同步市场数据
        </el-button>
        <el-button :loading="runningTask === 'generate_daily_report'" :disabled="running" @click="run('generate_daily_report')">
          生成每日简报
        </el-button>
      </div>
      <el-skeleton v-if="running && !result" :rows="4" animated />
      <TaskResultTable v-if="result" :result="result" />
    </div>

    <div class="section panel">
      <h2 class="section-title">按名称触发任务</h2>
      <div class="toolbar">
        <el-select v-model="selectedTask" style="min-width: 460px" :disabled="running">
          <el-option
            v-for="item in tasks"
            :key="item.task_name"
            :label="`${item.priority}｜${item.description}｜${item.scenario}`"
            :value="item.task_name"
          />
        </el-select>
        <el-button :loading="runningTask === selectedTask" :disabled="running" @click="run(selectedTask)">
          运行选中任务
        </el-button>
      </div>
      <el-table :data="tasks" border stripe>
        <el-table-column prop="priority" label="优先级" width="90" />
        <el-table-column prop="description" label="任务名称" min-width="180" />
        <el-table-column prop="scenario" label="应用场景" min-width="240" />
        <el-table-column prop="task_name" label="任务标识" min-width="180" />
      </el-table>
    </div>

    <div class="section panel">
      <h2 class="section-title">最近任务日志</h2>
      <el-skeleton v-if="loading" :rows="6" animated />
      <AutoTable v-else :rows="logs" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import { api } from "../api/fundpilot";
import type { DataHealth } from "../api/types";
import AutoTable from "../components/AutoTable.vue";
import MetricCard from "../components/MetricCard.vue";
import PageSkeleton from "../components/PageSkeleton.vue";
import TaskResultTable from "../components/TaskResultTable.vue";

interface AvailableTask {
  task_name: string;
  description: string;
  priority: string;
  scenario: string;
}

const health = ref<DataHealth | null>(null);
const tasks = ref<AvailableTask[]>([]);
const selectedTask = ref("");
const logs = ref<Array<Record<string, unknown>>>([]);
const result = ref<unknown>();
const loading = ref(false);
const hasLoadedOnce = ref(false);
const runningTask = ref("");
const running = computed(() => Boolean(runningTask.value));
const loadingText = computed(() => (running.value ? `正在运行任务：${runningTask.value}` : "正在加载任务中心..."));

async function load() {
  loading.value = true;
  try {
    const [healthData, taskData, logData] = await Promise.all([api.dataHealth(), api.availableTasks(), api.taskLogs()]);
    health.value = healthData;
    tasks.value = taskData as AvailableTask[];
    logs.value = logData as Array<Record<string, unknown>>;
    selectedTask.value ||= tasks.value[0]?.task_name || "";
    hasLoadedOnce.value = true;
  } finally {
    loading.value = false;
  }
}

async function run(task: string) {
  if (!task || running.value) return;
  runningTask.value = task;
  result.value = undefined;
  try {
    result.value = await api.runTask(task);
    await load();
  } finally {
    runningTask.value = "";
  }
}

onMounted(load);
</script>
