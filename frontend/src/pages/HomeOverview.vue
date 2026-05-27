<template>
  <PageSkeleton v-if="loading && !data" />
  <div v-else v-loading="loading" element-loading-text="正在刷新今日驾驶舱...">
    <div class="metric-grid">
      <MetricCard label="自选基金" :value="data?.watchlist_count ?? 0" accent="blue" />
      <MetricCard label="待办事项" :value="todos.length" accent="amber" />
      <MetricCard label="未读预警" :value="alerts.length" accent="amber" />
      <MetricCard label="最新日报" :value="latestReportTime" accent="sky" />
    </div>

    <div class="section panel">
      <h2 class="section-title">评分信号概览</h2>
      <div class="metric-grid">
        <button class="metric-action" @click="go('/scores')">
          <MetricCard label="已评分基金" :value="scoreSummary?.total_scored ?? 0" accent="blue" />
        </button>
        <button class="metric-action" @click="goScoreSignal(['favorable'])">
          <MetricCard label="窗口较好" :value="scoreSummary?.favorable_count ?? 0" accent="green" />
        </button>
        <button class="metric-action" @click="goScoreSignal(['watch'])">
          <MetricCard label="可以观察" :value="scoreSummary?.watch_count ?? 0" accent="sky" />
        </button>
        <button class="metric-action" @click="goScoreSignal(['wait_pullback', 'cautious', 'blocked'])">
          <MetricCard label="谨慎/等待" :value="scoreSummary?.cautious_count ?? 0" accent="amber" />
        </button>
      </div>
      <div v-if="scoreSummary?.top_risks.length" class="risk-chip-row">
        <el-tag v-for="risk in scoreSummary.top_risks" :key="risk.label" type="warning" effect="light">
          {{ risk.label }} {{ risk.count }}
        </el-tag>
      </div>
      <el-empty v-else class="compact-empty" description="暂无评分风险标签" />
    </div>

    <div class="section panel">
      <h2 class="section-title">今日待办</h2>
      <el-empty v-if="!todos.length" description="暂无待办事项" />
      <el-table v-else :data="todos" border stripe>
        <el-table-column label="事项" min-width="180">
          <template #default="{ row }">
            <el-tag :type="tagType(row.level)" effect="plain">{{ row.title }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="说明" min-width="280" />
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-button link type="primary" @click="go(row.route)">去处理</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div class="section two-col">
      <div class="panel">
        <h2 class="section-title">关键风险</h2>
        <el-alert
          v-for="risk in risks"
          :key="risk.title"
          class="alert-item"
          :type="tagType(risk.level)"
          :closable="false"
          :title="risk.title"
          :description="risk.description"
        />
      </div>
      <div class="panel">
        <h2 class="section-title">风险预警</h2>
        <el-empty v-if="!alerts.length" description="暂无未读风险提醒" />
        <el-collapse v-else v-model="openGroups">
          <AlertGroup
            v-for="group in groupedAlerts"
            :key="group.key"
            :group-key="group.key"
            :group-label="group.label"
            :items="group.items"
            @batch-update="batchUpdate"
            @single-update="updateAlert"
          />
        </el-collapse>
      </div>
    </div>

    <div class="section panel">
      <h2 class="section-title">数据状态</h2>
      <div class="metric-grid">
        <MetricCard label="最新净值日期" :value="dateText(health?.latest_nav_date)" />
        <MetricCard label="需关注基金" :value="health?.stale_fund_count ?? 0" />
        <MetricCard label="待计算指标" :value="health?.pending_indicator_count ?? 0" />
        <MetricCard label="待生成评分" :value="health?.pending_score_count ?? 0" />
        <MetricCard label="净值断档" :value="health?.gap_count ?? 0" />
      </div>
      <el-table class="section" :data="problemRows" border stripe>
        <el-table-column prop="fund_code" label="基金代码" />
        <el-table-column prop="status" label="状态" />
        <el-table-column prop="latest_nav_date" label="最新净值" />
        <el-table-column prop="nav_count" label="净值条数" />
        <el-table-column label="问题" min-width="240">
          <template #default="{ row }">{{ (row.issues || []).join("；") }}</template>
        </el-table-column>
      </el-table>
    </div>

    <div v-if="data?.latest_report" class="section">
      <ReportCard :report="data.latest_report" />
    </div>

    <div class="section panel">
      <h2 class="section-title">市场概览</h2>
      <div class="metric-grid">
        <MetricCard
          v-for="item in markets.slice(0, 4)"
          :key="item.index_code"
          :label="item.index_name"
          :value="pct(item.daily_return)"
          :hint="marketHint(item)"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from "element-plus";
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";

import { api } from "../api/fundpilot";
import { dateText, pct } from "../api/format";
import type { Alert, DashboardTodo, DataHealth, MarketContext, Report, RiskItem, ScoreSignalSummary } from "../api/types";
import AlertGroup from "../components/AlertGroup.vue";
import MetricCard from "../components/MetricCard.vue";
import PageSkeleton from "../components/PageSkeleton.vue";
import ReportCard from "../components/ReportCard.vue";

interface DashboardToday {
  watchlist_count: number;
  todos: DashboardTodo[];
  key_risks: RiskItem[];
  unread_alerts: Alert[];
  latest_report?: Report | null;
  market_context: MarketContext[];
  data_health: DataHealth;
  score_summary?: ScoreSignalSummary;
}

const GROUP_LABEL: Record<string, string> = {
  daily_drop: "单日大幅下跌",
  drawdown: "回撤超阈值",
  score_drop: "评分明显下降",
  position_weight: "持仓集中度过高",
  portfolio_drawdown: "组合整体回撤",
};

const router = useRouter();
const loading = ref(false);
const data = ref<DashboardToday | null>(null);
const health = computed(() => data.value?.data_health);
const todos = computed(() => data.value?.todos || []);
const alerts = computed(() => data.value?.unread_alerts || []);
const risks = computed(() => data.value?.key_risks || []);
const markets = computed(() => data.value?.market_context || []);
const scoreSummary = computed(() => data.value?.score_summary);
const latestReportTime = computed(() => data.value?.latest_report?.created_at?.slice(0, 16) || "暂无");
const problemRows = computed(() => (health.value?.funds || []).filter((item) => (item.issues as unknown[])?.length));

// Group alerts by alert_type, preserving a stable display order
const GROUP_ORDER = ["daily_drop", "drawdown", "score_drop", "position_weight", "portfolio_drawdown"];
const groupedAlerts = computed(() => {
  const map = new Map<string, Alert[]>();
  for (const a of alerts.value) {
    const key = a.alert_type || "other";
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(a);
  }
  // Add any alert_type not in the predefined order at the end
  const keys = [...GROUP_ORDER.filter((k) => map.has(k)), ...([...map.keys()].filter((k) => !GROUP_ORDER.includes(k)))];
  return keys.map((key) => ({
    key,
    label: GROUP_LABEL[key] || key,
    items: map.get(key) || [],
  }));
});

// Default open groups: those that have items (writable ref so el-collapse v-model works)
const openGroups = ref<string[]>([]);
watch(
  groupedAlerts,
  (groups) => {
    openGroups.value = groups.filter((g) => g.items.length).map((g) => g.key);
  },
  { immediate: true }
);

function tagType(level: string) {
  if (level === "danger") return "error";
  if (level === "warning" || level === "medium") return "warning";
  if (level === "success" || level === "info") return "success";
  return "info";
}

function go(route: string) {
  router.push(route);
}

function goScoreSignal(signals: string[]) {
  router.push({ path: "/scores", query: { signals: signals.join(",") } });
}

function peText(value?: number | null) {
  return value === null || value === undefined ? "PE 暂无" : `PE ${Math.round(value * 100)}%`;
}

function marketHint(item: MarketContext) {
  return `近 1 月 ${pct(item.return_1m)} · ${peText(item.pe_percentile)}`;
}

async function updateAlert(id: number, status: string) {
  await api.updateAlert(id, status);
  ElMessage.success("预警状态已更新");
  await load();
}

async function batchUpdate(ids: number[], status: string) {
  await Promise.all(ids.map((id) => api.updateAlert(id, status)));
  ElMessage.success(`已批量更新 ${ids.length} 条预警`);
  await load();
}

async function load() {
  loading.value = true;
  try {
    data.value = (await api.dashboardToday()) as DashboardToday;
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<style scoped>
.alert-item + .alert-item {
  margin-top: 10px;
}

.compact {
  margin: 8px 0 0;
}

.risk-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.compact-empty {
  padding: 8px 0 0;
}

.metric-action {
  padding: 0;
  color: inherit;
  text-align: left;
  background: transparent;
  border: 0;
  cursor: pointer;
}

.metric-action:hover :deep(.metric-card) {
  border-color: var(--color-accent-blue);
}
</style>
