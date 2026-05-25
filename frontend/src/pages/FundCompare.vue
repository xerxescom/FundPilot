<template>
  <div>
    <div class="toolbar panel">
      <el-select v-model="selected" multiple filterable placeholder="选择 2-5 只基金" style="min-width: 420px">
        <el-option v-for="item in watchlist" :key="item.fund_code" :label="`${item.fund_code} ${item.fund_name || ''}`" :value="item.fund_code" />
      </el-select>
      <el-button type="primary" :disabled="selected.length < 2" @click="compare">对比</el-button>
    </div>
    <div class="section panel">
      <el-table :data="fundRows" border stripe>
        <el-table-column prop="fund_code" label="基金代码" />
        <el-table-column prop="fund_name" label="基金名称" />
        <el-table-column prop="industry" label="行业/主题" />
        <el-table-column label="近1月"><template #default="{ row }">{{ pct(row.return_1m) }}</template></el-table-column>
        <el-table-column label="近1年"><template #default="{ row }">{{ pct(row.return_1y) }}</template></el-table-column>
        <el-table-column label="最大回撤"><template #default="{ row }">{{ pct(row.max_drawdown_1y) }}</template></el-table-column>
        <el-table-column prop="score" label="总分" />
        <el-table-column prop="rating" label="评级" />
      </el-table>
    </div>
    <div class="section panel">
      <h2 class="section-title">风险收益散点</h2>
      <ChartBox :option="scatterOption" />
    </div>
    <div class="section panel">
      <h2 class="section-title">行业/主题汇总</h2>
      <AutoTable :rows="industryRows" />
    </div>
  </div>
</template>

<script setup lang="ts">
import type { EChartsOption } from "echarts";
import { computed, onMounted, ref } from "vue";

import { api } from "../api/fundpilot";
import { pct } from "../api/format";
import type { WatchlistItem } from "../api/types";
import AutoTable from "../components/AutoTable.vue";
import ChartBox from "../components/ChartBox.vue";

const watchlist = ref<WatchlistItem[]>([]);
const selected = ref<string[]>([]);
const comparison = ref<Record<string, unknown> | null>(null);
const industryRows = ref<Array<Record<string, unknown>>>([]);
const fundRows = computed(() => (comparison.value?.funds as Array<Record<string, unknown>>) || []);
const scatterOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: "item" },
  xAxis: { name: "最大回撤", type: "value" },
  yAxis: { name: "近1年收益", type: "value" },
  series: [
    {
      type: "scatter",
      data: fundRows.value.map((row) => [
        Number(row.max_drawdown_1y || 0),
        Number(row.return_1y || 0),
        String(row.fund_code || ""),
      ]),
    },
  ],
}));

async function compare() {
  comparison.value = (await api.compareFunds(selected.value)) as Record<string, unknown>;
}

onMounted(async () => {
  const [watchlistData, industryData] = await Promise.all([api.watchlist(), api.industryOverview()]);
  watchlist.value = watchlistData;
  industryRows.value = industryData as Array<Record<string, unknown>>;
  selected.value = watchlist.value.slice(0, 2).map((item) => item.fund_code);
  if (selected.value.length >= 2) await compare();
});
</script>
