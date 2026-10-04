<template>
  <div v-loading="loading">
    <div class="toolbar panel">
      <FundSelector v-model="selected" :items="watchlist" />
    </div>
    <div class="section panel">
      <ErrorState v-if="loadError" title="评分历史加载失败" :message="loadError" :loading="loading" @retry="loadTrend" />
      <EmptyState
        v-else-if="!loading && !rows.length"
        :description="watchlist.length ? '该基金暂无评分历史：先在基金详情页计算评分' : '自选池为空，先添加基金'"
        action-text="重新加载"
        :loading="loading"
        @retry="loadTrend"
      />
      <AutoTable v-else :rows="rows" />
    </div>
    <div v-if="rows.length" class="section panel">
      <ChartBox :option="lineOption" />
    </div>
  </div>
</template>

<script setup lang="ts">
import type { EChartsOption } from "echarts";
import { computed, onMounted, ref, watch } from "vue";

import { errorMessage } from "../api/client";
import { api } from "../api/fundpilot";
import type { ScoreTrendRow, WatchlistItem } from "../api/types";
import AutoTable from "../components/AutoTable.vue";
import ChartBox from "../components/ChartBox.vue";
import EmptyState from "../components/EmptyState.vue";
import ErrorState from "../components/ErrorState.vue";
import FundSelector from "../components/FundSelector.vue";

const loading = ref(false);
const loadError = ref<string | null>(null);
const watchlist = ref<WatchlistItem[]>([]);
const selected = ref<string>();
const rows = ref<ScoreTrendRow[]>([]);
const lineOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: "axis" },
  legend: { top: 0 },
  grid: { top: 44, left: 56, right: 42, bottom: 36, containLabel: true },
  xAxis: { type: "category", data: rows.value.map((row) => String(row.score_date || "")) },
  yAxis: [
    { type: "value", name: "总分", min: 0, max: 100 },
    { type: "value", name: "变化", min: -20, max: 20 },
  ],
  series: [
    { name: "总分", type: "line", smooth: true, data: rows.value.map((row) => Number(row.total_score || 0)) },
    {
      name: "分数变化",
      type: "bar",
      yAxisIndex: 1,
      data: rows.value.map((row) => Number(row.score_change || 0)),
    },
  ],
}));

async function loadTrend() {
  if (!selected.value) {
    rows.value = [];
    return;
  }
  loading.value = true;
  loadError.value = null;
  try {
    rows.value = await api.scoreTrend(selected.value, { skipErrorToast: true });
  } catch (error) {
    rows.value = [];
    loadError.value = errorMessage(error);
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  try {
    watchlist.value = await api.watchlist({ skipErrorToast: true });
  } catch (error) {
    loadError.value = errorMessage(error);
    return;
  }
  selected.value = watchlist.value[0]?.fund_code;
  await loadTrend();
});
watch(selected, loadTrend);
</script>
