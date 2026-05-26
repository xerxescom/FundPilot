<template>
  <div>
    <div class="toolbar panel">
      <FundSelector v-model="selected" :items="watchlist" />
    </div>
    <div class="section panel">
      <AutoTable :rows="rows" />
    </div>
    <div class="section panel">
      <ChartBox :option="lineOption" />
    </div>
  </div>
</template>

<script setup lang="ts">
import type { EChartsOption } from "echarts";
import { computed, onMounted, ref, watch } from "vue";

import { api } from "../api/fundpilot";
import type { ScoreTrendRow, WatchlistItem } from "../api/types";
import AutoTable from "../components/AutoTable.vue";
import ChartBox from "../components/ChartBox.vue";
import FundSelector from "../components/FundSelector.vue";

const watchlist = ref<WatchlistItem[]>([]);
const selected = ref<string>();
const rows = ref<ScoreTrendRow[]>([]);
const lineOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: "axis" },
  legend: { top: 0 },
  grid: { top: 44, left: 56, right: 42, bottom: 36, containLabel: true },
  xAxis: { type: "category", data: rows.value.map((row) => String(row.score_date || "")) },
  yAxis: [
    { type: "value", min: 0, max: 100 },
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
  rows.value = selected.value ? await api.scoreTrend(selected.value) : [];
}

onMounted(async () => {
  watchlist.value = await api.watchlist();
  selected.value = watchlist.value[0]?.fund_code;
  await loadTrend();
});
watch(selected, loadTrend);
</script>
