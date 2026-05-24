<template>
  <div v-loading="loading">
    <div class="metric-grid">
      <MetricCard label="最新可用交易日" :value="dateText(health?.latest_available_trade_date)" />
      <MetricCard label="需关注基金" :value="health?.stale_fund_count ?? 0" />
      <MetricCard label="待计算指标" :value="health?.pending_indicator_count ?? 0" />
      <MetricCard label="缺失涨跌幅" :value="health?.missing_daily_return_count ?? 0" />
    </div>
    <div class="section panel">
      <h2 class="section-title">数据质量明细</h2>
      <el-table :data="health?.funds || []" border stripe>
        <el-table-column prop="fund_code" label="基金代码" />
        <el-table-column prop="status" label="状态" />
        <el-table-column prop="latest_nav_date" label="最新净值" />
        <el-table-column prop="stale_days" label="过旧天数" />
        <el-table-column prop="latest_sync_date" label="最近同步" />
        <el-table-column prop="latest_sync_status" label="同步状态" />
        <el-table-column label="问题" min-width="260">
          <template #default="{ row }">{{ (row.issues || []).join("；") || "正常" }}</template>
        </el-table-column>
      </el-table>
    </div>
    <div class="section panel">
      <h2 class="section-title">数据源对账</h2>
      <div class="toolbar">
        <FundSelector v-model="selected" :items="watchlist" />
        <el-button type="primary" :disabled="!selected" @click="reconcile">执行对账</el-button>
      </div>
      <pre v-if="reconcileResult" class="json-box">{{ JSON.stringify(reconcileResult, null, 2) }}</pre>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";

import { api } from "../api/fundpilot";
import { dateText } from "../api/format";
import type { DataHealth, WatchlistItem } from "../api/types";
import FundSelector from "../components/FundSelector.vue";
import MetricCard from "../components/MetricCard.vue";

const loading = ref(false);
const health = ref<DataHealth | null>(null);
const watchlist = ref<WatchlistItem[]>([]);
const selected = ref<string>();
const reconcileResult = ref<unknown>();

async function load() {
  loading.value = true;
  try {
    [health.value, watchlist.value] = await Promise.all([api.dataHealth(), api.watchlist()]);
  } finally {
    loading.value = false;
  }
}

async function reconcile() {
  if (!selected.value) return;
  reconcileResult.value = await api.reconcile(selected.value);
}

onMounted(load);
</script>

<style scoped>
.json-box {
  padding: 12px;
  overflow: auto;
  background: #f8fafc;
  border-radius: 8px;
}
</style>
