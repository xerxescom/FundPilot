<template>
  <div v-loading="loading">
    <div class="toolbar">
      <el-button type="primary" @click="sync">同步市场数据</el-button>
    </div>
    <div class="metric-grid">
      <MetricCard
        v-for="item in rows.slice(0, 4)"
        :key="item.index_code"
        :label="item.index_name"
        :value="pct(item.daily_return)"
        :hint="`近1月 ${pct(item.return_1m)} · ${peText(item.pe_percentile)} · ${dateText(item.trade_date)}`"
      />
    </div>
    <div class="section panel">
      <ErrorState v-if="loadError" title="市场数据加载失败" :message="loadError" :loading="loading" @retry="load" />
      <EmptyState
        v-else-if="!loading && !hasData"
        description="暂无市场数据，点击下方按钮同步指数行情"
        action-text="同步市场数据"
        :loading="loading"
        @retry="sync"
      />
      <el-table v-else :data="rows" border stripe>
        <el-table-column prop="index_code" label="指数代码" />
        <el-table-column prop="index_name" label="指数名称" />
        <el-table-column prop="trade_date" label="日期" />
        <el-table-column prop="close" label="收盘" />
        <el-table-column label="日涨跌"><template #default="{ row }">{{ pct(row.daily_return) }}</template></el-table-column>
        <el-table-column label="近1月"><template #default="{ row }">{{ pct(row.return_1m) }}</template></el-table-column>
        <el-table-column label="PE TTM"><template #default="{ row }">{{ numberText(row.pe_ttm) }}</template></el-table-column>
        <el-table-column label="PE 百分位"><template #default="{ row }">{{ peText(row.pe_percentile) }}</template></el-table-column>
        <el-table-column prop="valuation_date" label="估值日期" />
        <el-table-column prop="source" label="来源" />
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from "element-plus";
import { computed, onMounted, ref } from "vue";

import { errorMessage } from "../api/client";
import { api } from "../api/fundpilot";
import { dateText, pct } from "../api/format";
import type { MarketContext } from "../api/types";
import EmptyState from "../components/EmptyState.vue";
import ErrorState from "../components/ErrorState.vue";
import MetricCard from "../components/MetricCard.vue";

const loading = ref(false);
const loadError = ref<string | null>(null);
const rows = ref<MarketContext[]>([]);
// 接口会为未同步的指数返回占位行（trade_date 为空），据是否有日期判断是否真的同步过
const hasData = computed(() => rows.value.some((row) => Boolean(row.trade_date)));

function peText(value?: number | null) {
  return value === null || value === undefined ? "暂无" : `${Math.round(value * 100)}%`;
}

function numberText(value?: number | null) {
  return value === null || value === undefined ? "暂无" : Number(value).toFixed(2);
}

async function load() {
  loading.value = true;
  loadError.value = null;
  try {
    rows.value = await api.market({ skipErrorToast: true });
  } catch (error) {
    rows.value = [];
    loadError.value = errorMessage(error);
  } finally {
    loading.value = false;
  }
}

async function sync() {
  loading.value = true;
  try {
    await api.syncMarket();
    ElMessage.success("市场数据已同步");
    await load();
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>
