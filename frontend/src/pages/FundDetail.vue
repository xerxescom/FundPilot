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
      <div v-if="status" class="section detail-hero">
        <div class="hero-main">
          <div>
            <div class="hero-kicker">基金档案</div>
            <h2 class="fund-title">{{ status.fund_name || fundCode }}</h2>
            <div class="fund-meta">
              <span>{{ fundCode }}</span>
              <span>{{ status.data_status }}</span>
              <span>{{ dateText(status.latest_nav_date) }}</span>
            </div>
          </div>
          <div class="hero-score">
            <div class="hero-score-label">综合评分</div>
            <div class="hero-score-value">{{ scoreText(status.latest_score) }}</div>
            <el-tag :type="status.rating ? 'primary' : 'info'" effect="plain">{{ status.rating || '暂无评级' }}</el-tag>
          </div>
        </div>

        <div class="hero-facts">
          <div class="fact-item">
            <span>分析状态</span>
            <strong>{{ status.status_label }}</strong>
          </div>
          <div class="fact-item">
            <span>最新净值</span>
            <strong>{{ status.latest_nav ?? '暂无' }}</strong>
          </div>
          <div class="fact-item">
            <span>评分可信度</span>
            <strong>{{ confidenceText(score?.confidence_level) }}</strong>
            <small>{{ scoreText(score?.confidence_score) }}</small>
          </div>
          <div class="fact-item">
            <span>同类排名</span>
            <strong>{{ peerText(score) }}</strong>
          </div>
        </div>
      </div>

      <div v-if="status" class="section decision-layout">
        <section class="decision-panel signal-panel">
          <div class="module-heading">
            <span>窗口判断</span>
            <el-tag :type="signalTag(score?.buy_window_signal)" effect="dark">
              {{ signalText(score?.buy_window_signal) }}
            </el-tag>
          </div>
          <p class="decision-text">{{ score?.buy_window_reason || '暂无窗口判断，请先完成评分。' }}</p>
          <div class="signal-grid">
            <div>
              <span>市场环境</span>
              <strong>{{ marketText(score?.market_signal) }} {{ percentileText(score?.market_pe_percentile) }}</strong>
              <small>{{ score?.market_reason || '暂无' }}</small>
            </div>
            <div>
              <span>组合适配</span>
              <strong>{{ fitText(score?.portfolio_fit_level) }}</strong>
              <small>{{ score?.portfolio_fit_reason || '暂无' }}</small>
            </div>
          </div>
        </section>

        <section class="decision-panel progress-panel">
          <div class="module-heading">
            <span>分析进度</span>
            <strong>{{ activeStep }}/{{ status.steps.length }}</strong>
          </div>
          <el-steps class="progress-steps" :active="activeStep" finish-status="success" simple>
            <el-step v-for="step in status.steps" :key="step.key" :title="step.label" />
          </el-steps>
        </section>
      </div>

      <div v-if="status && (scoreReasonItems.length || riskLabelItems.length)" class="section insight-section">
        <section v-if="scoreReasonItems.length" class="insight-panel">
          <div class="module-heading">
            <span>评分拆解</span>
            <el-tag type="info" effect="plain">{{ scoreReasonItems.length }} 条</el-tag>
          </div>
          <ul class="insight-list">
            <li v-for="item in scoreReasonItems" :key="item">{{ item }}</li>
          </ul>
        </section>

        <section v-if="riskLabelItems.length" class="insight-panel risk-panel">
          <div class="module-heading">
            <span>风险提示</span>
            <el-tag type="warning" effect="plain">{{ riskLabelItems.length }} 条</el-tag>
          </div>
          <div class="risk-tags">
            <el-tag v-for="item in riskLabelItems" :key="item" type="warning" effect="light">
              {{ item }}
            </el-tag>
          </div>
        </section>
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

      <div v-if="syncDiagnostics" class="section diagnostics-section">
        <div class="section-heading-row">
          <div>
            <div class="section-eyebrow">Data Quality</div>
            <h2 class="section-title">同步诊断</h2>
          </div>
          <el-tag type="info" effect="plain">{{ syncDiagnostics.source }}</el-tag>
        </div>
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
        <div class="section section-heading-row">
          <div>
            <div class="section-eyebrow">Risk & Return</div>
            <h2 class="section-title">收益风险概览</h2>
          </div>
        </div>
        <div class="metric-grid metric-strip">
          <MetricCard label="近 1 月收益" :value="pct(indicator?.return_1m)" />
          <MetricCard label="近 1 年收益" :value="pct(indicator?.return_1y)" />
          <MetricCard label="最大回撤" :value="pct(indicator?.max_drawdown_1y)" />
          <MetricCard label="评分" :value="scoreText(score?.total_score)" :hint="score?.rating" />
          <MetricCard label="可信度" :value="confidenceText(score?.confidence_level)" :hint="scoreText(score?.confidence_score)" />
          <MetricCard label="窗口信号" :value="signalText(score?.buy_window_signal)" :hint="score?.buy_window_reason" />
          <MetricCard
            label="市场环境"
            :value="marketText(score?.market_signal)"
            :hint="marketHint(score)"
          />
          <MetricCard label="同类排名" :value="peerText(score)" :hint="score?.peer_reason" />
          <MetricCard label="组合适配" :value="fitText(score?.portfolio_fit_level)" :hint="score?.portfolio_fit_reason" />
        </div>

        <div class="section chart-panel">
          <div class="section-heading-row">
            <div>
              <div class="section-eyebrow">Performance</div>
              <h2 class="section-title">净值、回撤与日涨跌幅</h2>
            </div>
          </div>
          <ChartSkeleton v-if="loading" />
          <ChartBox v-else :option="navOption" />
        </div>

        <div class="section table-section">
          <div class="section-heading-row">
            <div>
              <div class="section-eyebrow">NAV Detail</div>
              <h2 class="section-title">净值明细</h2>
            </div>
          </div>
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
const scoreReasonItems = computed(() =>
  (status.value?.score_reason || "")
    .split("；")
    .map((item) => item.trim())
    .filter(Boolean),
);
const riskLabelItems = computed(() => {
  if (!score.value) return [];
  const labels = score.value.risk_flag_labels?.length ? score.value.risk_flag_labels : score.value.risk_flags;
  return labels || [];
});
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

function signalTag(signal?: Score["buy_window_signal"] | null) {
  if (signal === "favorable") return "success";
  if (signal === "watch") return "primary";
  if (signal === "wait_pullback") return "warning";
  return "danger";
}

function marketText(signal?: Score["market_signal"] | null) {
  const labels = { supportive: "偏强", neutral: "中性", weak: "偏弱" };
  return signal ? labels[signal] : "暂无";
}

function percentileText(value?: number | null) {
  return value === null || value === undefined ? "" : `PE ${Math.round(value * 100)}%`;
}

function marketHint(row?: Score | null) {
  const percentile = percentileText(row?.market_pe_percentile);
  return [percentile, row?.market_reason].filter(Boolean).join("；") || "暂无";
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

function riskLabels(row: Score) {
  const labels = row.risk_flag_labels?.length ? row.risk_flag_labels : row.risk_flags;
  return labels?.length ? labels.join("；") : "无";
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

.detail-hero,
.decision-panel,
.diagnostics-section,
.chart-panel,
.table-section {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.detail-hero {
  padding: 22px;
  border-left: 4px solid #2563eb;
}

.hero-main {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  align-items: flex-start;
}

.hero-kicker,
.section-eyebrow {
  color: #64748b;
  font-size: 12px;
  font-weight: 720;
  text-transform: uppercase;
}

.fund-title {
  margin: 6px 0 8px;
  font-size: 26px;
  font-weight: 780;
}

.fund-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  color: #64748b;
  font-size: 13px;
}

.fund-meta span + span::before {
  content: "/";
  margin-right: 8px;
  color: #cbd5e1;
}

.hero-score {
  min-width: 148px;
  text-align: right;
}

.hero-score-label {
  color: #64748b;
  font-size: 13px;
}

.hero-score-value {
  margin: 4px 0 8px;
  font-size: 34px;
  font-weight: 800;
}

.hero-facts {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1px;
  margin-top: 20px;
  overflow: hidden;
  background: #e5e7eb;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.fact-item {
  min-height: 86px;
  padding: 14px;
  background: #f8fafc;
}

.fact-item span,
.signal-grid span {
  display: block;
  color: #64748b;
  font-size: 12px;
}

.fact-item strong,
.signal-grid strong {
  display: block;
  margin-top: 7px;
  font-size: 18px;
}

.fact-item small,
.signal-grid small {
  display: block;
  margin-top: 5px;
  color: #64748b;
  line-height: 1.5;
}

.decision-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(360px, 0.85fr);
  gap: 14px;
}

.decision-panel {
  padding: 18px;
}

.signal-panel {
  border-left: 4px solid #10b981;
}

.progress-panel {
  border-left: 4px solid #8b5cf6;
}

.module-heading,
.section-heading-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.module-heading span {
  font-size: 16px;
  font-weight: 760;
}

.decision-text {
  margin: 14px 0 16px;
  color: #334155;
  line-height: 1.7;
}

.signal-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.signal-grid > div {
  padding: 13px;
  background: #f8fafc;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.progress-steps {
  margin-top: 16px;
}

.insight-section {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(300px, 0.65fr);
  gap: 14px;
}

.insight-panel {
  padding: 16px;
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-left: 4px solid #0ea5e9;
  border-radius: 8px;
}

.risk-panel {
  border-left-color: #f59e0b;
}

.insight-list {
  display: grid;
  gap: 9px;
  margin: 14px 0 0;
  padding: 0;
  list-style: none;
}

.insight-list li {
  position: relative;
  padding-left: 18px;
  color: #334155;
  line-height: 1.6;
}

.insight-list li::before {
  position: absolute;
  top: 0.68em;
  left: 0;
  width: 7px;
  height: 7px;
  background: #0ea5e9;
  border-radius: 50%;
  content: "";
}

.risk-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.diagnostics-section,
.chart-panel,
.table-section {
  padding: 16px;
}

.metric-strip {
  align-items: stretch;
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

@media (max-width: 980px) {
  .hero-main,
  .module-heading,
  .section-heading-row {
    align-items: flex-start;
  }

  .hero-main,
  .decision-layout,
  .signal-grid,
  .hero-facts,
  .insight-section {
    grid-template-columns: 1fr;
  }

  .hero-main,
  .module-heading,
  .section-heading-row {
    flex-direction: column;
  }

  .hero-score {
    text-align: left;
  }
}
</style>
