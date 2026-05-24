<template>
  <div v-loading="loading">
    <div class="panel">
      <h2 class="section-title">新增买入记录</h2>
      <el-form :model="transaction" inline>
        <el-form-item label="基金代码"><el-input v-model="transaction.fund_code" /></el-form-item>
        <el-form-item label="买入日期"><el-date-picker v-model="transaction.trade_date" value-format="YYYY-MM-DD" /></el-form-item>
        <el-form-item label="买入金额"><el-input-number v-model="transaction.amount" :min="0" /></el-form-item>
        <el-form-item label="成交净值"><el-input-number v-model="transaction.nav" :min="0" :precision="4" /></el-form-item>
        <el-form-item label="手续费"><el-input-number v-model="transaction.fee" :min="0" /></el-form-item>
        <el-form-item><el-button type="primary" @click="addTransaction">添加买入记录并自动汇总</el-button></el-form-item>
      </el-form>
    </div>

    <div class="section metric-grid">
      <MetricCard label="当前市值" :value="money(overview?.total_value)" />
      <MetricCard label="投入成本" :value="money(overview?.total_cost)" />
      <MetricCard label="收益金额" :value="money(overview?.profit_amount)" />
      <MetricCard label="收益率" :value="pct(overview?.profit_rate)" />
    </div>

    <div class="section two-col">
      <div class="panel">
        <h2 class="section-title">持仓列表</h2>
        <el-table :data="positionRows" border stripe>
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="fund_code" label="基金代码" />
          <el-table-column prop="holding_share" label="持有份额" />
          <el-table-column prop="latest_nav" label="最新净值" />
          <el-table-column prop="current_value" label="当前市值" />
          <el-table-column label="收益率"><template #default="{ row }">{{ pct(row.profit_rate) }}</template></el-table-column>
          <el-table-column label="操作" width="130">
            <template #default="{ row }">
              <el-button link type="danger" @click="deletePosition(row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <div class="panel">
        <h2 class="section-title">持仓占比</h2>
        <ChartBox :option="pieOption" />
      </div>
    </div>

    <div class="section panel">
      <h2 class="section-title">买入记录</h2>
      <el-table :data="transactions" border stripe>
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="fund_code" label="基金代码" />
        <el-table-column prop="trade_date" label="买入日期" />
        <el-table-column prop="amount" label="买入金额" />
        <el-table-column prop="nav" label="成交净值" />
        <el-table-column prop="share" label="份额" />
        <el-table-column label="操作" width="130">
          <template #default="{ row }">
            <el-button link type="danger" @click="deleteTransaction(row.id)">删除并重新汇总</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from "element-plus";
import { computed, onMounted, reactive, ref } from "vue";

import { api } from "../api/fundpilot";
import { money, pct } from "../api/format";
import type { PortfolioOverview } from "../api/types";
import ChartBox from "../components/ChartBox.vue";
import MetricCard from "../components/MetricCard.vue";

const loading = ref(false);
const overview = ref<PortfolioOverview | null>(null);
const transactions = ref<unknown[]>([]);
const transaction = reactive({ fund_code: "", trade_date: "", amount: 0, nav: 0, fee: 0 });

const positionRows = computed(() =>
  (overview.value?.positions || []).map((item) => ({
    id: item.position.id,
    fund_code: item.position.fund_code,
    holding_share: item.position.holding_share,
    latest_nav: item.latest_nav,
    current_value: item.current_value,
    profit_rate: item.profit_rate,
  })),
);

const pieOption = computed(() => ({
  tooltip: { trigger: "item" },
  series: [
    {
      type: "pie",
      radius: ["45%", "70%"],
      data: positionRows.value.map((row) => ({ name: row.fund_code, value: row.current_value || 0 })),
    },
  ],
}));

async function load() {
  [overview.value, transactions.value] = await Promise.all([api.portfolioOverview(), api.portfolioTransactions()]);
}

async function addTransaction() {
  loading.value = true;
  try {
    await api.addTransaction({ ...transaction });
    ElMessage.success("买入记录已添加");
    await load();
  } finally {
    loading.value = false;
  }
}

async function deleteTransaction(id: number) {
  await api.deleteTransaction(id);
  await load();
}

async function deletePosition(id: number) {
  await api.deletePosition(id);
  await load();
}

onMounted(load);
</script>
