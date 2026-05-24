<template>
  <div>
    <div class="panel">
      <div class="toolbar">
        <FundSelector v-model="fundA" :items="watchlist" />
        <FundSelector v-model="fundB" :items="watchlist" />
        <el-button type="primary" @click="loadPair">查看相关走势</el-button>
        <el-button @click="generateAlerts">生成高相关预警</el-button>
      </div>
      <el-table :data="pairs" border stripe>
        <el-table-column prop="fund_a" label="基金A (fund_a)" />
        <el-table-column prop="fund_b" label="基金B (fund_b)" />
        <el-table-column prop="correlation" label="相关系数 (correlation)" />
      </el-table>
    </div>
    <div class="section panel">
      <h2 class="section-title">日涨跌走势对比</h2>
      <ChartBox :option="lineOption" />
    </div>
    <div class="section panel">
      <h2 class="section-title">相关矩阵</h2>
      <AutoTable :rows="matrixRows" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from "element-plus";
import { computed, onMounted, ref } from "vue";

import { api } from "../api/fundpilot";
import type { WatchlistItem } from "../api/types";
import AutoTable from "../components/AutoTable.vue";
import ChartBox from "../components/ChartBox.vue";
import FundSelector from "../components/FundSelector.vue";

const watchlist = ref<WatchlistItem[]>([]);
const pairs = ref<unknown[]>([]);
const matrix = ref<Record<string, Record<string, number>>>({});
const returns = ref<Array<Record<string, unknown>>>([]);
const fundA = ref<string>();
const fundB = ref<string>();
const matrixRows = computed(() =>
  Object.entries(matrix.value).map(([fundCode, values]) => ({
    fund_code: fundCode,
    ...values,
  })),
);
const lineOption = computed(() => ({
  tooltip: { trigger: "axis" },
  xAxis: { type: "category", data: returns.value.map((row) => row.nav_date) },
  yAxis: { type: "value" },
  series: [
    { name: fundA.value, type: "line", data: returns.value.map((row) => row.return_a) },
    { name: fundB.value, type: "line", data: returns.value.map((row) => row.return_b) },
  ],
}));

async function loadPair() {
  if (!fundA.value || !fundB.value) return;
  returns.value = (await api.correlationReturns(fundA.value, fundB.value)) as Array<Record<string, unknown>>;
}

async function generateAlerts() {
  const alerts = await api.generateCorrelationAlerts();
  ElMessage.success(`已生成或更新 ${alerts.length} 条相关性预警`);
}

onMounted(async () => {
  [watchlist.value, pairs.value, matrix.value] = await Promise.all([
    api.watchlist(),
    api.correlationPairs(),
    api.correlationMatrix(),
  ]);
  fundA.value = watchlist.value[0]?.fund_code;
  fundB.value = watchlist.value[1]?.fund_code;
  await loadPair();
});
</script>
