<template>
  <div v-loading="loading">
    <div class="metric-grid">
      <MetricCard label="自选基金" :value="data?.watchlist_count ?? 0" />
      <MetricCard label="最高评分" :value="scoreText(bestScore?.total_score)" :hint="bestScore?.rating || '暂无'" />
      <MetricCard label="未读预警" :value="alerts.length" />
      <MetricCard label="最近简报" :value="latestReportTime" />
    </div>

    <div class="section panel">
      <h2 class="section-title">数据状态</h2>
      <div class="metric-grid">
        <MetricCard label="最新净值日期" :value="dateText(health?.latest_nav_date)" />
        <MetricCard label="需关注基金" :value="health?.stale_fund_count ?? 0" />
        <MetricCard label="待计算指标" :value="health?.pending_indicator_count ?? 0" />
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

    <div class="section two-col">
      <div class="panel">
        <h2 class="section-title">推荐关注 Top 5</h2>
        <el-table :data="data?.top_scores || []" border stripe>
          <el-table-column prop="fund_code" label="基金代码" />
          <el-table-column prop="fund_name" label="基金名称" min-width="160" />
          <el-table-column label="总分"><template #default="{ row }">{{ scoreText(row.total_score) }}</template></el-table-column>
          <el-table-column prop="rating" label="评级" />
          <el-table-column prop="reason" label="理由" min-width="260" />
        </el-table>
      </div>
      <div class="panel">
        <h2 class="section-title">风险提醒</h2>
        <el-alert
          v-for="alert in alerts.slice(0, 6)"
          :key="alert.id"
          class="alert-item"
          type="warning"
          :closable="false"
          :title="alert.title || alert.alert_type"
          :description="alert.content || ''"
        />
        <el-empty v-if="!alerts.length" description="暂无未读风险提醒" />
      </div>
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
          :hint="`近1月 ${pct(item.return_1m)}`"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import { api } from "../api/fundpilot";
import { dateText, pct, scoreText } from "../api/format";
import type { Alert, DataHealth, MarketContext, Report } from "../api/types";
import MetricCard from "../components/MetricCard.vue";
import ReportCard from "../components/ReportCard.vue";

interface DashboardData {
  watchlist_count: number;
  top_scores: Array<Record<string, unknown>>;
  unread_alerts: Alert[];
  latest_report?: Report | null;
  market_context: MarketContext[];
  data_health: DataHealth;
}

const loading = ref(false);
const data = ref<DashboardData | null>(null);
const health = computed(() => data.value?.data_health);
const alerts = computed(() => data.value?.unread_alerts || []);
const markets = computed(() => data.value?.market_context || []);
const bestScore = computed(() => data.value?.top_scores?.[0]);
const latestReportTime = computed(() => data.value?.latest_report?.created_at?.slice(0, 16) || "暂无");
const problemRows = computed(() => (health.value?.funds || []).filter((item) => (item.issues as unknown[])?.length));

async function load() {
  loading.value = true;
  try {
    data.value = (await api.dashboard()) as DashboardData;
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
</style>
