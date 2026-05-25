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
      </div>

      <el-alert
        v-if="needsFullAnalysis"
        class="section"
        type="warning"
        :closable="false"
        show-icon
        title="这只基金还没有完成同步分析"
        description="当前基金缺少净值、指标或评分数据。请点击“一键同步并分析”完成数据同步、指标计算、评分生成和基金解释后再查看详情。"
      />

      <div v-if="needsFullAnalysis" class="section panel empty-action">
        <el-button type="primary" size="large" :loading="actionLoading === 'analyze'" @click="analyze">
          一键同步并分析
        </el-button>
      </div>

      <template v-else>
        <div class="section metric-grid">
          <MetricCard label="近 1 月收益" :value="pct(indicator?.return_1m)" />
          <MetricCard label="近 1 年收益" :value="pct(indicator?.return_1y)" />
          <MetricCard label="最大回撤" :value="pct(indicator?.max_drawdown_1y)" />
          <MetricCard label="评分" :value="scoreText(score?.total_score)" :hint="score?.rating" />
        </div>

        <div class="section panel chart-panel">
          <h2 class="section-title">净值、回撤与日涨跌幅</h2>
          <ChartSkeleton v-if="loading" />
          <ChartBox v-else :option="navOption" />
        </div>

        <div class="section panel">
          <h2 class="section-title">净值明细</h2>
          <el-skeleton v-if="loading" :rows="6" animated />
          <el-table v-else :data="navRows" border stripe>
            <el-table-column prop="nav_date" label="日期" />
            <el-table-column prop="unit_nav" label="单位净值" />
            <el-table-column prop="accumulated_nav" label="累计净值" />
            <el-table-column label="日涨跌幅">
              <template #default="{ row }">{{ pct(row.daily_return) }}</template>
            </el-table-column>
            <el-table-column prop="source" label="来源" />
          </el-table>
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
import type { AnalysisStatus, FundNav, Indicator, Score, WatchlistItem } from "../api/types";
import ChartBox from "../components/ChartBox.vue";
import ChartSkeleton from "../components/ChartSkeleton.vue";
import FundSelector from "../components/FundSelector.vue";
import MetricCard from "../components/MetricCard.vue";
import PageSkeleton from "../components/PageSkeleton.vue";

type ActionLoading = "sync" | "indicator" | "score" | "analyze" | null;

const route = useRoute();
const watchlist = ref<WatchlistItem[]>([]);
const selected = ref<string>();
const manualCode = ref("");
const loading = ref(false);
const hasLoadedOnce = ref(false);
const actionLoading = ref<ActionLoading>(null);
const navRows = ref<FundNav[]>([]);
const indicator = ref<Indicator | null>(null);
const score = ref<Score | null>(null);
const status = ref<AnalysisStatus | null>(null);
const fundCode = computed(() => (manualCode.value || selected.value || String(route.params.fundCode || "")).trim());
const needsFullAnalysis = computed(() => !navRows.value.length || !indicator.value || !score.value);
const busy = computed(() => actionLoading.value !== null);
const activeStep = computed(() => status.value?.steps.filter((step) => step.done).length || 0);
const loadingText = computed(() => {
  if (actionLoading.value === "analyze") return "正在同步净值、计算指标、生成评分和基金解释...";
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
    indicator.value = await api.indicators(fundCode.value).catch(() => null);
    score.value = await api.score(fundCode.value).catch(() => null);
    hasLoadedOnce.value = true;
  } finally {
    loading.value = false;
  }
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
    await api.syncFundNav(fundCode.value);
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
    await api.analyzeFund(fundCode.value);
    ElMessage.success("同步分析完成");
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
</style>
