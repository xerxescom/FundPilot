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
import { computed, onMounted, ref, watch } from "vue";

import { api } from "../api/fundpilot";
import type { WatchlistItem } from "../api/types";
import AutoTable from "../components/AutoTable.vue";
import ChartBox from "../components/ChartBox.vue";
import FundSelector from "../components/FundSelector.vue";

const watchlist = ref<WatchlistItem[]>([]);
const selected = ref<string>();
const rows = ref<Array<Record<string, unknown>>>([]);
const lineOption = computed(() => ({
  tooltip: { trigger: "axis" },
  xAxis: { type: "category", data: rows.value.map((row) => row.score_date) },
  yAxis: { type: "value", min: 0, max: 100 },
  series: [{ name: "总分", type: "line", data: rows.value.map((row) => row.total_score) }],
}));

async function loadTrend() {
  rows.value = selected.value ? ((await api.scoreTrend(selected.value)) as Array<Record<string, unknown>>) : [];
}

onMounted(async () => {
  watchlist.value = await api.watchlist();
  selected.value = watchlist.value[0]?.fund_code;
  await loadTrend();
});
watch(selected, loadTrend);
</script>
