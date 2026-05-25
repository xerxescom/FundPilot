<template>
  <div>
    <div class="toolbar panel">
      <FundSelector v-model="selected" :items="watchlist" />
      <el-input v-model="manualCode" placeholder="或手动输入基金代码" style="max-width: 220px" />
      <el-button :loading="actionLoading === 'sync'" :disabled="busy" @click="syncNav">同步净值</el-button>
      <el-button :loading="actionLoading === 'indicator'" :disabled="busy" @click="calcIndicators">计算指标</el-button>
      <el-button :loading="actionLoading === 'score'" :disabled="busy" @click="calcScore">计算评分</el-button>
      <el-button type="primary" :loading="actionLoading === 'analyze'" :disabled="busy" @click="analyze">
        一键同步并分析
      </el-button>
      <el-button :loading="actionLoading === 'report'" :disabled="busy || !score" @click="generateReport">
        生成基金解释
      </el-button>
    </div>

    <PageSkeleton v-if="loading && !hasLoadedOnce" class="section" />

    <div v-else-if="fundCode" v-loading="loading || busy" :element-loading-text="loadingText" class="fund-detail-body">
      <div v-if="status" class="section panel">
        <h2 class="section-title">基金档案</h2>
        <div class="metric-grid">
          <MetricCard label="基金名称" :value="status.fund_name || fundCode" />
          <MetricCard label="分析状态" :value="status.status_label" :hint="status.data_status" />
          <MetricCard label="最新净值" :value="status.latest_nav ?? '暂无'" :hint="dateText(status.latest_nav_date)" />
          <MetricCard label="当前评级" :value="status.rating || '暂无'" :hint="scoreText(status.latest_score)" />
          <MetricCard label="评分可信度" :value="confidenceText(score?.confidence_level)" :hint="scoreText(score?.confidence_score)" />
          <MetricCard label="窗口信号" :value="signalText(score?.buy_window_signal)" :hint="score?.buy_window_reason || '不构成投资建议'" />
          <MetricCard label="市场环境" :value="marketText(score?.market_signal)" :hint="score?.market_reason" />
          <MetricCard label="同类排名" :value="peerText(score)" :hint="score?.peer_reason" />
          <MetricCard label="组合适配" :value="fitText(score?.portfolio_fit_level)" :hint="score?.portfolio_fit_reason" />
        </div>
        <el-steps class="section" :active="activeStep" finish-status="success" simple>
          <el-step v-for="step in status.steps" :key="step.key" :title="step.label" />
        </el-steps>
        <el-alert
          v-if="status.score_reason"
          class="section"
          type="info"
          :closable="false"
          title="评分原因"
          :description="status.score_reason"
        />
        <el-alert
          v-if="score?.risk_flags?.length"
          class="section"
          type="warning"
          :closable="false"
          title="风险提示"
          :description="score.risk_flags.join('；')"
        />
      </div>

      <el-alert
        v-if="needsFullAnalysis"
        class="section"
        type="warning"
        :closable="false"
        show-icon
        title="这只基金还没有完成同步分析"
        description="当前基金缺少净值、指标或评分数据。请点击“一键同步并分析”先完成快速分析；基金解释可在评分生成后单独触发。"
      />

      <div v-if="needsFullAnalysis" class="section panel empty-action">
        <el-button type="primary" size="large" :loading="actionLoading === 'analyze'" @click="analyze">
          一键同步并分析
        </el-button>
      </div>

      <div v-if="syncDiagnostics" class="section panel">
        <h2 class="section-title">同步诊断</h2>
        <div class="metric-grid">
          <MetricCard label="使用数据源" :value="syncDiagnostics.source" />
          <MetricCard label="同步行数" :value="syncDiagnostics.synced_rows" />
          <MetricCard label="重复日期" :value="syncDiagnostics.quality.duplicate_count" />
          <MetricCard label="缺失日涨跌幅" :value="syncDiagnostics.quality.missing_daily_return_count" />
        </div>
        <el-alert
          v-if="syncDiagnostics.quality.issues.length"
          class="section"
          type="warning"
          :closable="false"
          title="数据质量提示"
          :description="syncDiagnostics.quality.issues.join('；')"
        />
        <el-table class="section" :data="syncDiagnostics.attempts" border stripe>
          <el-table-column prop="source" label="数据源" min-width="120" />
          <el-table-column prop="attempt" label="重试次数" width="100" />
          <el-table-column prop="status" label="状态" min-width="120">
            <template #default="{ row }">{{ syncStatusText(row.status) }}</template>
          </el-table-column>
          <el-table-column prop="row_count" label="返回行数" width="110" />
          <el-table-column label="问题说明" min-width="220">
            <template #default="{ row }">{{ row.issues?.length ? row.issues.join("；") : "无" }}</template>
          </el-table-column>
        </el-table>
      </div>

      <template v-if="!needsFullAnalysis">
        <div class="section metric-grid">
          <MetricCard label="近 1 月收益" :value="pct(indicator?.return_1m)" />
          <MetricCard label="近 1 年收益" :value="pct(indicator?.return_1y)" />
          <MetricCard label="最大回撤" :value="pct(indicator?.max_drawdown_1y)" />
          <MetricCard label="评分" :value="scoreText(score?.total_score)" :hint="score?.rating" />
          <MetricCard label="可信度" :value="confidenceText(score?.confidence_level)" :hint="scoreText(score?.confidence_score)" />
          <MetricCard label="窗口信号" :value="signalText(score?.buy_window_signal)" :hint="score?.buy_window_reason" />
          <MetricCard label="市场环境" :value="marketText(score?.market_signal)" :hint="score?.market_reason" />
          <MetricCard label="同类排名" :value="peerText(score)" :hint="score?.peer_reason" />
          <MetricCard label="组合适配" :value="fitText(score?.portfolio_fit_level)" :hint="score?.portfolio_fit_reason" />
        </div>

        <div class="section panel chart-panel">
          <h2 class="section-title">净值、回撤与日涨跌幅</h2>
          <ChartSkeleton v-if="loading" />
          <ChartBox v-else :option="navOption" />
        </div>

        <div class="section panel">
          <h2 class="section-title">净值明细</h2>
          <el-skeleton v-if="loading" :rows="6" animated />
          <el-table
            v-else
            :data="pagedNavRows"
            border
            stripe
            :default-sort="{ prop: 'nav_date', order: 'descending' }"
            @sort-change="handleNavSort"
          >
            <el-table-column prop="nav_date" label="日期" sortable="custom" />
            <el-table-column prop="unit_nav" label="单位净值" sortable="custom" />
            <el-table-column prop="accumulated_nav" label="累计净值" sortable="custom" />
            <el-table-column prop="daily_return" label="日涨跌幅" sortable="custom">
              <template #default="{ row }">{{ pct(row.daily_return) }}</template>
            </el-table-column>
            <el-table-column prop="source" label="来源" />
          </el-table>
          <el-pagination
            class="table-pagination"
            layout="total, sizes, prev, pager, next"
            :total="sortedNavRows.length"
            :page-sizes="[10, 20, 50, 100]"
            v-model:current-page="navPage"
            v-model:page-size="navPageSize"
          />
        </div>
      </template>
    </div>

    <el-empty v-else description="先选择基金或手动输入基金代码" />
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from "element-plus";
import type { EChartsOption } from "echarts";
import { computed, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";

import { api } from "../api/fundpilot";
import { dateText, pct, scoreText } from "../api/format";
import type { AnalysisStatus, FundNav, Indicator, Score, SyncDiagnostics, WatchlistItem } from "../api/types";
import ChartBox from "../components/ChartBox.vue";
import ChartSkeleton from "../components/ChartSkeleton.vue";
import FundSelector from "../components/FundSelector.vue";
import MetricCard from "../components/MetricCard.vue";
import PageSkeleton from "../components/PageSkeleton.vue";

type ActionLoading = "sync" | "indicator" | "score" | "analyze" | "report" | null;

const route = useRoute();
const watchlist = ref<WatchlistItem[]>([]);
const selected = ref<string>();
const manualCode = ref("");
const loading = ref(false);
const hasLoadedOnce = ref(false);
const actionLoading = ref<ActionLoading>(null);
const navRows = ref<FundNav[]>([]);
const navPage = ref(1);
const navPageSize = ref(20);
const navSort = ref<{ prop: keyof FundNav; order: "ascending" | "descending" }>({
  prop: "nav_date",
  order: "descending",
});
const indicator = ref<Indicator | null>(null);
const score = ref<Score | null>(null);
const status = ref<AnalysisStatus | null>(null);
const syncDiagnostics = ref<SyncDiagnostics | null>(null);
const fundCode = computed(() => (manualCode.value || selected.value || String(route.params.fundCode || "")).trim());
const needsFullAnalysis = computed(() => !navRows.value.length || !indicator.value || !score.value);
const busy = computed(() => actionLoading.value !== null);
const activeStep = computed(() => status.value?.steps.filter((step) => step.done).length || 0);
const loadingText = computed(() => {
  if (actionLoading.value === "analyze") return "正在同步净值、计算指标并生成评分...";
  if (actionLoading.value === "report") return "正在调用模型生成基金解释，可能需要一点时间...";
  if (actionLoading.value === "sync") return "正在同步净值数据...";
  if (actionLoading.value === "indicator") return "正在计算指标...";
  if (actionLoading.value === "score") return "正在计算评分...";
  return "正在加载基金详情...";
});

const drawdown = computed(() => {
  let peak = 0;
  return navRows.value.map((row) => {
    const value = Number(row.unit_nav || 0);
    peak = Math.max(peak, value);
    return peak ? value / peak - 1 : 0;
  });
});

const sortedNavRows = computed(() => {
  const { prop, order } = navSort.value;
  return [...navRows.value].sort((left, right) => {
    const leftValue = left[prop];
    const rightValue = right[prop];
    if (leftValue === rightValue) return 0;
    if (leftValue === null || leftValue === undefined) return 1;
    if (rightValue === null || rightValue === undefined) return -1;
    const leftNumber = Number(leftValue);
    const rightNumber = Number(rightValue);
    const result =
      Number.isNaN(leftNumber) || Number.isNaN(rightNumber)
        ? String(leftValue).localeCompare(String(rightValue))
        : leftNumber - rightNumber;
    return order === "ascending" ? result : -result;
  });
});

const pagedNavRows = computed(() => {
  const start = (navPage.value - 1) * navPageSize.value;
  return sortedNavRows.value.slice(start, start + navPageSize.value);
});

const navOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: "axis" },
  legend: { top: 0 },
  grid: [
    { top: 44, left: 68, right: 42, height: 86, containLabel: true },
    { top: 174, left: 68, right: 42, height: 86, containLabel: true },
    { top: 304, left: 68, right: 42, bottom: 36, containLabel: true },
  ],
  xAxis: [
    { type: "category", data: navRows.value.map((row) => row.nav_date) },
    { type: "category", gridIndex: 1, data: navRows.value.map((row) => row.nav_date) },
    { type: "category", gridIndex: 2, data: navRows.value.map((row) => row.nav_date) },
  ],
  yAxis: [{ type: "value" }, { type: "value", gridIndex: 1 }, { type: "value", gridIndex: 2 }],
  series: [
    { name: "单位净值", type: "line", data: navRows.value.map((row) => row.unit_nav) },
    { name: "回撤", type: "line", xAxisIndex: 1, yAxisIndex: 1, data: drawdown.value },
    { name: "日涨跌幅", type: "bar", xAxisIndex: 2, yAxisIndex: 2, data: navRows.value.map((row) => row.daily_return) },
  ],
}));

async function loadBase() {
  watchlist.value = await api.watchlist();
  selected.value ||= watchlist.value[0]?.fund_code;
}

async function loadFund() {
  if (!fundCode.value) return;
  loading.value = true;
  try {
    status.value = (await api.analysisStatus(fundCode.value).catch(() => null)) as AnalysisStatus | null;
    navRows.value = await api.nav(fundCode.value);
    navPage.value = 1;
    indicator.value = await api.indicators(fundCode.value).catch(() => null);
    score.value = await api.score(fundCode.value).catch(() => null);
    hasLoadedOnce.value = true;
  } finally {
    loading.value = false;
  }
}

function handleNavSort({ prop, order }: { prop: keyof FundNav; order: "ascending" | "descending" | null }) {
  navSort.value = { prop: prop || "nav_date", order: order || "descending" };
  navPage.value = 1;
}

function syncStatusText(statusText: string) {
  const labels: Record<string, string> = {
    success: "成功",
    invalid: "数据质量异常",
    invalid_data: "数据质量异常",
    error: "失败",
    failed: "失败",
    skipped: "已跳过",
  };
  return labels[statusText] || statusText;
}

function confidenceText(level?: Score["confidence_level"] | null) {
  const labels = { high: "高", medium: "中", low: "低" };
  return level ? labels[level] : "暂无";
}

function signalText(signal?: Score["buy_window_signal"] | null) {
  const labels = {
    favorable: "窗口较好",
    watch: "可以观察",
    wait_pullback: "等待确认",
    cautious: "谨慎观察",
    blocked: "不可操作",
  };
  return signal ? labels[signal] : "暂无";
}

function marketText(signal?: Score["market_signal"] | null) {
  const labels = { supportive: "偏强", neutral: "中性", weak: "偏弱" };
  return signal ? labels[signal] : "暂无";
}

function peerText(row?: Score | null) {
  if (!row) return "暂无";
  if (row.peer_percentile === null || row.peer_percentile === undefined) {
    return row.peer_group ? `${row.peer_group} 样本不足` : "暂无";
  }
  return `${Math.round(row.peer_percentile * 100)}%`;
}

function fitText(level?: Score["portfolio_fit_level"] | null) {
  const labels = { high: "高", medium: "中", low: "低" };
  return level ? labels[level] : "暂无";
}

async function runAction(action: Exclude<ActionLoading, null>, work: () => Promise<void>) {
  actionLoading.value = action;
  try {
    await work();
  } finally {
    actionLoading.value = null;
  }
}

async function syncNav() {
  if (!fundCode.value) return;
  await runAction("sync", async () => {
    syncDiagnostics.value = await api.syncFundNav(fundCode.value);
    ElMessage.success("净值已同步");
    await loadFund();
  });
}

async function calcIndicators() {
  if (!fundCode.value) return;
  await runAction("indicator", async () => {
    indicator.value = await api.calcIndicators(fundCode.value);
    ElMessage.success("指标已更新");
    await loadFund();
  });
}

async function calcScore() {
  if (!fundCode.value) return;
  await runAction("score", async () => {
    score.value = await api.calcScore(fundCode.value);
    ElMessage.success("评分已更新");
    await loadFund();
  });
}

async function analyze() {
  if (!fundCode.value) return;
  await runAction("analyze", async () => {
    const result = await api.analyzeFund(fundCode.value);
    syncDiagnostics.value = result.sync_diagnostics || null;
    ElMessage.success("同步分析完成");
    await loadFund();
  });
}

async function generateReport() {
  if (!fundCode.value) return;
  await runAction("report", async () => {
    await api.generateFundReport(fundCode.value);
    ElMessage.success("基金解释已生成");
    await loadFund();
  });
}

onMounted(async () => {
  await loadBase();
  await loadFund();
});
watch(fundCode, loadFund);
</script>

<style scoped>
.fund-detail-body {
  min-height: 360px;
}

.empty-action {
  display: flex;
  justify-content: center;
  padding: 28px;
}

.chart-panel :deep(.chart) {
  height: 440px;
}

.table-pagination {
  justify-content: flex-end;
  margin-top: 14px;
}
</style>
