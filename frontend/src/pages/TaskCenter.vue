<template>
  <PageSkeleton v-if="loading && !hasLoadedOnce" />
  <div v-else v-loading="loading || running || Boolean(enqueueingTask)" :element-loading-text="loadingText">
    <div class="metric-grid">
      <MetricCard label="待计算指标" :value="health?.pending_indicator_count ?? 0" />
      <MetricCard label="待生成评分" :value="health?.pending_score_count ?? 0" />
      <MetricCard label="待生成报告" :value="health?.pending_report_count ?? 0" />
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
      <div class="section-heading">
        <div>
          <h2 class="section-title">每日批次</h2>
          <p class="muted">按依赖推进：行情及市场背景 → 数据质量 → 指标 → 评分 → 预警 → 报告。</p>
        </div>
        <div class="toolbar">
          <el-button type="primary" :loading="batchCreating" @click="startBatch">更新今日数据</el-button>
          <el-button :disabled="!batches.length" @click="loadBatches">刷新批次</el-button>
        </div>
      </div>
      <el-empty v-if="!batches.length" description="暂无批次，点击“更新今日数据”创建" />
      <template v-else>
        <el-table :data="batches" border stripe highlight-current-row @current-change="selectBatch">
          <el-table-column prop="id" label="批次" width="80" />
          <el-table-column prop="trade_date" label="交易日" width="120" />
          <el-table-column label="状态" width="120">
            <template #default="{ row }">
              <el-tag :type="batchTagType(row.effective_status)" effect="plain">
                {{ BATCH_STATUS_LABEL[row.effective_status] || row.effective_status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="进度" min-width="260">
            <template #default="{ row }">
              成功 {{ row.success_count }} · 暂未发布 {{ row.pending_count }} · 失败 {{ row.failure_count }} · 跳过 {{ row.skipped_count }} · 中断 {{ row.interrupted_count }}
            </template>
          </el-table-column>
          <el-table-column label="创建时间" min-width="170">
            <template #default="{ row }">{{ (row.created_at || "").slice(0, 19) }}</template>
          </el-table-column>
        </el-table>
        <template v-if="batchDetail">
          <h3 class="batch-subtitle">步骤明细（批次 #{{ batchDetail.batch.id }}）</h3>
          <el-table :data="batchDetail.items" border stripe max-height="440">
            <el-table-column prop="step_label" label="步骤" width="140" />
            <el-table-column label="资产" min-width="170">
              <template #default="{ row }">
                {{ row.display_name || row.asset_code || "全局" }}
                <span v-if="row.asset_code" class="muted">（{{ row.asset_code }}）</span>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="110">
              <template #default="{ row }">
                <el-tag :type="itemTagType(row.effective_status)" effect="plain">
                  {{ ITEM_STATUS_LABEL[row.effective_status] || row.effective_status }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="说明" min-width="240">
              <template #default="{ row }">{{ row.error_message || "" }}</template>
            </el-table-column>
            <el-table-column label="操作" width="90">
              <template #default="{ row }">
                <el-button v-if="isRetryable(row)" link type="primary" @click="retryItem(row)">重试</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-alert
            v-for="note in batchNotes"
            :key="note"
            class="alert-item"
            type="info"
            :closable="false"
            :title="note"
          />
        </template>
      </template>
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
        <el-button :loading="runningTask === selectedTask" :disabled="running || Boolean(enqueueingTask)" @click="run(selectedTask)">
          前台运行
        </el-button>
        <el-button
          type="primary"
          :loading="enqueueingTask === selectedTask"
          :disabled="running || Boolean(enqueueingTask)"
          @click="enqueue(selectedTask)"
        >
          后台运行
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
import { ElMessage } from "element-plus";
import { computed, onMounted, onUnmounted, ref } from "vue";

import { api } from "../api/fundpilot";
import type { BatchDetail, BatchItem, DataHealth, TaskBatchInfo } from "../api/types";
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

const STATUS_LABEL: Record<string, string> = {
  success: "成功",
  partial_success: "部分成功",
  failed: "失败",
  queued: "排队中",
  running: "执行中",
};
const BATCH_STATUS_LABEL: Record<string, string> = {
  queued: "排队中",
  running: "运行中",
  success: "已完成",
  partial_success: "部分成功",
  failed: "失败",
  interrupted: "中断（可恢复）",
};
const ITEM_STATUS_LABEL: Record<string, string> = {
  queued: "排队中",
  running: "运行中",
  success: "成功",
  failed: "失败",
  skipped: "已跳过",
  pending: "暂未发布",
  interrupted: "中断",
};
const BATCH_ACTIVE = new Set(["queued", "running"]);
const batches = ref<TaskBatchInfo[]>([]);
const batchDetail = ref<BatchDetail | null>(null);
const batchCreating = ref(false);
let batchTimer: number | undefined;
const health = ref<DataHealth | null>(null);
const tasks = ref<AvailableTask[]>([]);
const selectedTask = ref("");
const logs = ref<Array<Record<string, unknown>>>([]);
const result = ref<unknown>();
const loading = ref(false);
const hasLoadedOnce = ref(false);
const runningTask = ref("");
const enqueueingTask = ref("");
const running = computed(() => Boolean(runningTask.value));
const loadingText = computed(() => {
  if (running.value) return `正在前台运行任务：${runningTask.value}`;
  if (enqueueingTask.value) return `正在提交后台任务：${enqueueingTask.value}`;
  return "正在加载任务中心...";
});

async function load() {
  loading.value = true;
  try {
    const [healthData, taskData, logData] = await Promise.all([api.dataHealth(), api.availableTasks(), api.taskLogs()]);
    health.value = healthData;
    tasks.value = taskData as AvailableTask[];
    logs.value = (logData as Array<Record<string, unknown>>).map((item) => ({
      ...item,
      status: STATUS_LABEL[String(item.status)] || item.status,
    }));
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

async function enqueue(task: string) {
  if (!task || running.value || enqueueingTask.value) return;
  enqueueingTask.value = task;
  result.value = undefined;
  try {
    result.value = await api.enqueueTask(task);
    ElMessage.success("任务已提交后台执行");
    await load();
  } finally {
    enqueueingTask.value = "";
  }
}

// —— 每日批次 ——
function batchTagType(status: string) {
  if (status === "success") return "success";
  if (status === "partial_success") return "warning";
  if (status === "failed" || status === "interrupted") return "danger";
  return "info";
}

function itemTagType(status: string) {
  if (status === "success") return "success";
  if (status === "failed" || status === "interrupted") return "danger";
  if (status === "skipped") return "warning";
  return "info";
}

const batchNotes = computed(() => batchDetail.value?.batch.coverage_json?.notes || []);

function isRetryable(item: BatchItem) {
  return ["failed", "interrupted", "pending"].includes(item.effective_status);
}

async function selectBatch(row: TaskBatchInfo | null) {
  if (!row) return;
  batchDetail.value = await api.taskBatchDetail(row.id);
}

async function loadBatches() {
  batches.value = await api.taskBatches(10);
  const currentId = batchDetail.value?.batch.id;
  const target = batches.value.find((item) => item.id === currentId) || batches.value[0];
  if (target) await selectBatch(target);
  scheduleBatchPolling();
}

async function startBatch() {
  batchCreating.value = true;
  try {
    const result = await api.createDailyBatch();
    ElMessage.success(result.created ? "已提交今日更新批次" : "今日批次已存在，继续跟进进度");
    await loadBatches();
  } finally {
    batchCreating.value = false;
  }
}

async function retryItem(item: BatchItem) {
  if (!batchDetail.value) return;
  const result = await api.retryTaskBatch(batchDetail.value.batch.id, {
    step: item.step,
    asset_type: item.asset_type || undefined,
    asset_code: item.asset_code || undefined,
  });
  ElMessage.success(`已重新排队 ${result.retried} 项`);
  await loadBatches();
}

function scheduleBatchPolling() {
  window.clearTimeout(batchTimer);
  if (!batches.value.some((item) => BATCH_ACTIVE.has(item.effective_status))) return;
  batchTimer = window.setTimeout(loadBatches, 3000);
}

onMounted(async () => {
  await load();
  await loadBatches();
});

onUnmounted(() => window.clearTimeout(batchTimer));
</script>

<style scoped>
.section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
}

.batch-subtitle {
  margin: 16px 0 8px;
  font-size: 14px;
  font-weight: 600;
}

.alert-item {
  margin-top: 10px;
}
</style>
