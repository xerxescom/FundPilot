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
        :hint="`近1月 ${pct(item.return_1m)} · ${dateText(item.trade_date)}`"
      />
    </div>
    <div class="section panel">
      <el-table :data="rows" border stripe>
        <el-table-column prop="index_code" label="指数代码" />
        <el-table-column prop="index_name" label="指数名称" />
        <el-table-column prop="trade_date" label="日期" />
        <el-table-column prop="close" label="收盘" />
        <el-table-column label="日涨跌"><template #default="{ row }">{{ pct(row.daily_return) }}</template></el-table-column>
        <el-table-column label="近1月"><template #default="{ row }">{{ pct(row.return_1m) }}</template></el-table-column>
        <el-table-column prop="source" label="来源" />
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from "element-plus";
import { onMounted, ref } from "vue";

import { api } from "../api/fundpilot";
import { dateText, pct } from "../api/format";
import type { MarketContext } from "../api/types";
import MetricCard from "../components/MetricCard.vue";

const loading = ref(false);
const rows = ref<MarketContext[]>([]);

async function load() {
  rows.value = await api.market();
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
