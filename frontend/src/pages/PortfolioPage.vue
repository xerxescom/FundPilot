<template>
  <div v-loading="loading" element-loading-text="正在更新持仓和组合诊断...">
    <div class="panel">
      <h2 class="section-title">记录交易</h2>
      <el-form :model="transaction" inline>
        <el-form-item label="资产类型">
          <el-select v-model="transaction.asset_type" class="type-select">
            <el-option label="基金" value="fund" />
            <el-option label="股票" value="stock" />
            <el-option label="ETF" value="etf" />
          </el-select>
        </el-form-item>
        <el-form-item label="代码"><el-input v-model="transaction.asset_code" /></el-form-item>
        <el-form-item label="交易类型">
          <el-select v-model="transaction.trade_type" class="type-select">
            <el-option label="买入" value="buy" />
            <el-option label="卖出" value="sell" />
            <el-option v-if="transaction.asset_type === 'fund'" label="申购" value="subscription" />
            <el-option v-if="transaction.asset_type === 'fund'" label="赎回" value="redemption" />
          </el-select>
        </el-form-item>
        <el-form-item label="交易日期"><el-date-picker v-model="transaction.trade_date" value-format="YYYY-MM-DD" /></el-form-item>
        <el-form-item label="成交金额"><el-input-number v-model="transaction.amount" :min="0" /></el-form-item>
        <el-form-item :label="priceLabel"><el-input-number v-model="transaction.nav" :min="0" :precision="4" /></el-form-item>
        <el-form-item label="手续费"><el-input-number v-model="transaction.fee" :min="0" /></el-form-item>
        <el-form-item><el-button type="primary" :disabled="!transaction.asset_code" @click="addTransaction">保存并自动汇总</el-button></el-form-item>
        <el-form-item v-if="transaction.asset_type !== 'fund'"><el-button @click="syncAsset">同步股票/ETF 行情</el-button></el-form-item>
      </el-form>
      <p class="muted">基金使用净值，股票和 ETF 使用成交价；卖出记录会按当前平均成本重算剩余持仓。</p>
    </div>

    <div class="section metric-grid">
      <MetricCard label="当前市值" :value="money(overview?.total_value)" />
      <MetricCard label="投入成本" :value="money(overview?.total_cost)" />
      <MetricCard label="收益金额" :value="money(overview?.profit_amount)" />
      <MetricCard label="收益率" :value="pct(overview?.profit_rate)" />
    </div>

    <div class="section panel">
      <h2 class="section-title">基金拟买入模拟</h2>
      <el-form :model="simulationForm" inline>
        <el-form-item label="基金代码"><el-input v-model="simulationForm.fund_code" /></el-form-item>
        <el-form-item label="拟买金额"><el-input-number v-model="simulationForm.amount" :min="0" /></el-form-item>
        <el-form-item><el-button type="primary" :disabled="!simulationForm.fund_code || simulationForm.amount <= 0" @click="simulateBuy">计算组合影响</el-button></el-form-item>
      </el-form>
      <template v-if="simulation">
        <div class="metric-grid simulation-grid">
          <MetricCard label="买入后总市值" :value="money(simulation.total_value_after)" :hint="`买入前 ${money(simulation.total_value_before)}`" />
          <MetricCard label="目标基金占比" :value="pct(simulation.target_weight_after)" :hint="`买入前 ${pct(simulation.target_weight_before)}`" />
          <MetricCard label="最大持仓占比" :value="pct(simulation.max_weight_after)" :hint="`买入前 ${pct(simulation.max_weight_before)}`" />
          <MetricCard label="最高相关性" :value="correlationText(simulation.max_correlation)" :hint="`平均 ${correlationText(simulation.avg_correlation)}`" />
        </div>
        <el-alert v-for="risk in simulation.risk_items" :key="risk.title" class="alert-item" :type="risk.level === 'medium' ? 'warning' : 'info'" :closable="false" :title="risk.title" :description="risk.description" />
      </template>
    </div>

    <div class="section panel">
      <h2 class="section-title">组合诊断</h2>
      <div class="metric-grid">
        <MetricCard label="持仓数量" :value="diagnosis?.summary.position_count ?? 0" />
        <MetricCard label="最大持仓占比" :value="pct(diagnosis?.summary.max_weight)" />
        <MetricCard label="近 1 月回撤" :value="pct(diagnosis?.summary.drawdown_1m)" />
        <MetricCard label="组合收益率" :value="pct(diagnosis?.summary.profit_rate)" />
      </div>
      <el-alert v-for="risk in diagnosis?.risk_items || []" :key="risk.title" class="alert-item" :type="risk.level === 'medium' ? 'warning' : 'info'" :closable="false" :title="risk.title" :description="risk.description" />
      <p class="muted">{{ diagnosis?.observation }}</p>
    </div>

    <div class="section two-col">
      <div class="panel">
        <h2 class="section-title">统一持仓列表</h2>
        <el-table :data="positionRows" border stripe>
          <el-table-column prop="asset_type_label" label="类型" width="85" />
          <el-table-column prop="asset_code" label="代码" width="110" />
          <el-table-column prop="asset_name" label="名称" min-width="140" />
          <el-table-column prop="holding_share" label="持有数量" />
          <el-table-column prop="latest_price" label="最新价格/净值" />
          <el-table-column prop="current_value" label="当前市值" />
          <el-table-column label="收益率"><template #default="{ row }">{{ pct(row.profit_rate) }}</template></el-table-column>
          <el-table-column label="操作" width="90"><template #default="{ row }"><el-button link type="danger" @click="deletePosition(row.id)">删除</el-button></template></el-table-column>
        </el-table>
      </div>
      <div class="panel"><h2 class="section-title">持仓占比</h2><ChartBox :option="pieOption" /></div>
    </div>

    <div class="section panel">
      <h2 class="section-title">交易记录</h2>
      <el-table :data="transactionRows" border stripe>
        <el-table-column prop="asset_type_label" label="类型" width="85" />
        <el-table-column prop="asset_code" label="代码" width="110" />
        <el-table-column prop="asset_name" label="名称" min-width="140" />
        <el-table-column prop="trade_type_label" label="交易" width="80" />
        <el-table-column prop="trade_date" label="交易日期" />
        <el-table-column prop="amount" label="成交金额" />
        <el-table-column prop="nav" label="成交价格/净值" />
        <el-table-column prop="share" label="数量" />
        <el-table-column label="操作" width="150"><template #default="{ row }"><el-button link type="danger" @click="deleteTransaction(row.id)">删除并重新汇总</el-button></template></el-table-column>
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
import type { Asset, PortfolioBuySimulation, PortfolioDiagnosis, PortfolioOverview, WatchlistItem } from "../api/types";
import ChartBox from "../components/ChartBox.vue";
import MetricCard from "../components/MetricCard.vue";

const ASSET_LABEL: Record<string, string> = { fund: "基金", stock: "股票", etf: "ETF" };
const TRADE_LABEL: Record<string, string> = { buy: "买入", sell: "卖出", subscription: "申购", redemption: "赎回" };
const loading = ref(false);
const overview = ref<PortfolioOverview | null>(null);
const diagnosis = ref<PortfolioDiagnosis | null>(null);
const simulation = ref<PortfolioBuySimulation | null>(null);
const transactions = ref<Array<Record<string, unknown>>>([]);
const watchlist = ref<WatchlistItem[]>([]);
const assets = ref<Asset[]>([]);
const transaction = reactive({ asset_type: "fund" as "fund" | "stock" | "etf", asset_code: "", trade_type: "buy", trade_date: "", amount: 0, nav: 0, fee: 0 });
const simulationForm = reactive({ fund_code: "", amount: 0 });
const priceLabel = computed(() => (transaction.asset_type === "fund" ? "成交净值" : "成交价格"));
const nameMap = computed(() => Object.fromEntries([
  ...watchlist.value.map((item) => [item.fund_code, item.fund_name || ""]),
  ...assets.value.map((item) => [item.asset_code, item.asset_name]),
]));
const positionRows = computed(() => (overview.value?.positions || []).map((item) => ({
  id: item.position.id,
  asset_type: item.asset_type || item.position.asset_type,
  asset_type_label: ASSET_LABEL[item.asset_type || item.position.asset_type] || item.asset_type,
  asset_code: item.asset_code || item.position.asset_code || item.position.fund_code,
  asset_name: item.asset_name || item.fund_name || "",
  holding_share: item.position.holding_share,
  latest_price: item.latest_price ?? item.latest_nav,
  current_value: item.current_value,
  profit_rate: item.profit_rate,
})));
const transactionRows = computed(() => transactions.value.map((item) => {
  const assetType = String(item.asset_type || "fund");
  const assetCode = String(item.asset_code || item.fund_code || "");
  return { ...item, asset_code: assetCode, asset_type_label: ASSET_LABEL[assetType] || assetType, asset_name: nameMap.value[assetCode] || "", trade_type_label: TRADE_LABEL[String(item.trade_type)] || item.trade_type };
}));
const pieOption = computed<EChartsOption>(() => ({ tooltip: { trigger: "item" }, series: [{ type: "pie", radius: ["45%", "70%"], data: positionRows.value.map((row) => ({ name: row.asset_name ? `${row.asset_name} (${row.asset_code})` : row.asset_code, value: row.current_value || 0 })) }] }));

async function load() {
  loading.value = true;
  try {
    [overview.value, transactions.value, diagnosis.value, watchlist.value, assets.value] = await Promise.all([
      api.portfolioOverview(), api.portfolioTransactions() as Promise<Array<Record<string, unknown>>>, api.portfolioDiagnosis() as Promise<PortfolioDiagnosis>, api.watchlist(), api.assets(),
    ]);
  } finally { loading.value = false; }
}
async function addTransaction() {
  loading.value = true;
  try { await api.addTransaction({ ...transaction }); ElMessage.success("交易记录已保存"); await load(); } finally { loading.value = false; }
}
async function syncAsset() {
  loading.value = true;
  try { const result = await api.syncAsset(transaction.asset_code, transaction.asset_type as "stock" | "etf"); ElMessage.success(`已同步 ${result.synced_rows} 条行情`); await load(); } finally { loading.value = false; }
}
async function simulateBuy() { loading.value = true; try { simulation.value = await api.simulatePortfolioBuy({ ...simulationForm }); } finally { loading.value = false; } }
function correlationText(value?: number | null) { return value === null || value === undefined ? "暂无" : Number(value).toFixed(2); }
async function deleteTransaction(id: number) { await api.deleteTransaction(id); await load(); }
async function deletePosition(id: number) { await api.deletePosition(id); await load(); }
onMounted(load);
</script>

<style scoped>
.alert-item { margin-top: 10px; }
.simulation-grid { margin-top: 10px; }
.type-select { width: 110px; }
</style>
