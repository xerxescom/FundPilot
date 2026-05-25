<template>
  <div v-loading="loading" element-loading-text="正在更新持仓和组合诊断...">
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

    <div class="section panel">
      <h2 class="section-title">组合诊断</h2>
      <div class="metric-grid">
        <MetricCard label="持仓数量" :value="diagnosis?.summary.position_count ?? 0" />
        <MetricCard label="最大持仓占比" :value="pct(diagnosis?.summary.max_weight)" />
        <MetricCard label="近 1 月回撤" :value="pct(diagnosis?.summary.drawdown_1m)" />
        <MetricCard label="组合收益率" :value="pct(diagnosis?.summary.profit_rate)" />
      </div>
      <el-alert
        v-for="risk in diagnosis?.risk_items || []"
        :key="risk.title"
        class="alert-item"
        :type="risk.level === 'medium' ? 'warning' : 'info'"
        :closable="false"
        :title="risk.title"
        :description="risk.description"
      />
      <p class="muted">{{ diagnosis?.observation }}</p>
    </div>

    <div class="section two-col">
      <div class="panel">
        <h2 class="section-title">持仓列表</h2>
        <el-table :data="positionRows" border stripe>
          <el-table-column prop="id" label="编号 (ID)" width="90" />
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
        <el-table-column prop="id" label="编号 (ID)" width="90" />
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
import type { EChartsOption } from "echarts";
import { computed, onMounted, reactive, ref } from "vue";

import { api } from "../api/fundpilot";
import { money, pct } from "../api/format";
import type { PortfolioDiagnosis, PortfolioOverview } from "../api/types";
import ChartBox from "../components/ChartBox.vue";
import MetricCard from "../components/MetricCard.vue";

const loading = ref(false);
const overview = ref<PortfolioOverview | null>(null);
const diagnosis = ref<PortfolioDiagnosis | null>(null);
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

const pieOption = computed<EChartsOption>(() => ({
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
  loading.value = true;
  try {
    [overview.value, transactions.value, diagnosis.value] = await Promise.all([
      api.portfolioOverview(),
      api.portfolioTransactions(),
      api.portfolioDiagnosis() as Promise<PortfolioDiagnosis>,
    ]);
  } finally {
    loading.value = false;
  }
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

<style scoped>
.alert-item {
  margin-top: 10px;
}
</style>
