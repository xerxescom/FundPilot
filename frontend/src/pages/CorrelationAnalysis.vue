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
        <el-table-column label="基金 A" min-width="180">
          <template #default="{ row }">
            <span>{{ row.fund_a_name || row.fund_a }}</span>
            <span class="code-tag">{{ row.fund_a }}</span>
          </template>
        </el-table-column>
        <el-table-column label="基金 B" min-width="180">
          <template #default="{ row }">
            <span>{{ row.fund_b_name || row.fund_b }}</span>
            <span class="code-tag">{{ row.fund_b }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="correlation" label="相关系数" width="120" />
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
import type { EChartsOption } from "echarts";
import { computed, onMounted, ref } from "vue";

import { api } from "../api/fundpilot";
import type { WatchlistItem } from "../api/types";
import AutoTable from "../components/AutoTable.vue";
import ChartBox from "../components/ChartBox.vue";
import FundSelector from "../components/FundSelector.vue";

const watchlist = ref<WatchlistItem[]>([]);
const pairs = ref<unknown[]>([]);
const matrix = ref<Record<string, Record<string, number>>>({});
const nameMap = ref<Record<string, string>>({});
const returns = ref<Array<Record<string, unknown>>>([]);
const fundA = ref<string>();
const fundB = ref<string>();

const fundNameMap = computed(() =>
  Object.fromEntries(watchlist.value.map((item) => [item.fund_code, item.fund_name || item.fund_code])),
);
const fundALabel = computed(() => (fundA.value ? fundNameMap.value[fundA.value] || fundA.value : ""));
const fundBLabel = computed(() => (fundB.value ? fundNameMap.value[fundB.value] || fundB.value : ""));

/** Remap matrix keys from raw fund codes to "Name (code)" labels */
const matrixRows = computed(() => {
  const labelFor = (code: string) => {
    const name = nameMap.value[code];
    return name ? `${name} (${code})` : code;
  };
  return Object.entries(matrix.value).map(([fundCode, values]) => ({
    基金: labelFor(fundCode),
    ...Object.fromEntries(Object.entries(values).map(([k, v]) => [labelFor(k), v])),
  }));
});

const lineOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: "axis" },
  legend: { top: 0 },
  grid: { left: 58, right: 28, bottom: 34, containLabel: true },
  xAxis: { type: "category", data: returns.value.map((row) => String(row.nav_date || "")) },
  yAxis: { type: "value" },
  series: [
    { name: fundALabel.value, type: "line", data: returns.value.map((row) => Number(row.return_a || 0)) },
    { name: fundBLabel.value, type: "line", data: returns.value.map((row) => Number(row.return_b || 0)) },
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
  const [watchlistData, pairsData, matrixResp] = await Promise.all([
    api.watchlist(),
    api.correlationPairs(),
    api.correlationMatrix(),
  ]);
  watchlist.value = watchlistData;
  pairs.value = pairsData as unknown[];
  // Handle both old (plain dict) and new ({matrix, name_map}) response shapes
  const resp = matrixResp as Record<string, unknown>;
  if (resp.matrix && typeof resp.matrix === "object") {
    matrix.value = resp.matrix as Record<string, Record<string, number>>;
    nameMap.value = (resp.name_map as Record<string, string>) || {};
  } else {
    matrix.value = matrixResp as unknown as Record<string, Record<string, number>>;
  }
  fundA.value = watchlist.value[0]?.fund_code;
  fundB.value = watchlist.value[1]?.fund_code;
  await loadPair();
});
</script>

<style scoped>
.code-tag {
  margin-left: 6px;
  font-size: 12px;
  color: #94a3b8;
}
</style>

