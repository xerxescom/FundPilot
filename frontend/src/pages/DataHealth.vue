<template>
  <div v-loading="loading">
    <ErrorState
      v-if="loadError"
      class="section"
      title="数据健康加载失败"
      :message="loadError"
      :loading="loading"
      @retry="load"
    />
    <template v-else>
      <div class="metric-grid">
        <MetricCard label="最新可用交易日" :value="dateText(health?.latest_available_trade_date)" />
        <MetricCard label="需关注基金" :value="health?.stale_fund_count ?? 0" />
        <MetricCard label="待计算指标" :value="health?.pending_indicator_count ?? 0" />
        <MetricCard label="待生成评分" :value="health?.pending_score_count ?? 0" />
        <MetricCard label="待生成报告" :value="health?.pending_report_count ?? 0" />
        <MetricCard label="缺失涨跌幅" :value="health?.missing_daily_return_count ?? 0" />
      </div>
      <div class="section panel">
        <h2 class="section-title">数据质量明细</h2>
        <el-table :data="health?.funds || []" border stripe>
          <el-table-column prop="fund_code" label="基金代码" />
          <el-table-column prop="status" label="状态" />
          <el-table-column prop="latest_nav_date" label="最新净值" />
          <el-table-column prop="latest_indicator_date" label="最新指标" />
          <el-table-column prop="latest_score_date" label="最新评分" />
          <el-table-column prop="latest_report_date" label="最新报告" />
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
          <el-button type="primary" :disabled="!selected" :loading="reconciling" @click="reconcile">
            执行对账
          </el-button>
        </div>
        <EmptyState v-if="!watchlist.length" description="自选池为空，先添加基金后再对账" />
        <ErrorState
          v-else-if="reconcileError"
          title="对账失败"
          :message="reconcileError"
          :loading="reconciling"
          @retry="reconcile"
        />
        <ReconcileResultView v-else-if="reconcileResult" :result="reconcileResult" />
        <p v-else class="muted">选择基金后执行对账，逐日比较 AKShare 与 Eastmoney 的净值与涨跌幅差异。</p>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";

import { errorMessage } from "../api/client";
import { dateText } from "../api/format";
import { api } from "../api/fundpilot";
import type { DataHealth, ReconcileResult, WatchlistItem } from "../api/types";
import EmptyState from "../components/EmptyState.vue";
import ErrorState from "../components/ErrorState.vue";
import FundSelector from "../components/FundSelector.vue";
import MetricCard from "../components/MetricCard.vue";
import ReconcileResultView from "../components/ReconcileResult.vue";

const loading = ref(false);
const loadError = ref<string | null>(null);
const health = ref<DataHealth | null>(null);
const watchlist = ref<WatchlistItem[]>([]);
const selected = ref<string>();
const reconciling = ref(false);
const reconcileError = ref<string | null>(null);
const reconcileResult = ref<ReconcileResult | null>(null);

async function load() {
  loading.value = true;
  loadError.value = null;
  try {
    [health.value, watchlist.value] = await Promise.all([
      api.dataHealth({ skipErrorToast: true }),
      api.watchlist({ skipErrorToast: true }),
    ]);
  } catch (error) {
    loadError.value = errorMessage(error);
  } finally {
    loading.value = false;
  }
}

async function reconcile() {
  if (!selected.value) return;
  reconciling.value = true;
  reconcileError.value = null;
  try {
    reconcileResult.value = await api.reconcile(selected.value, { skipErrorToast: true });
  } catch (error) {
    reconcileResult.value = null;
    reconcileError.value = errorMessage(error);
  } finally {
    reconciling.value = false;
  }
}

onMounted(load);
</script>
