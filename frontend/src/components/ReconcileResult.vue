<template>
  <div>
    <el-alert :type="statusType(result.status)" :closable="false" show-icon :title="result.summary" />
    <el-alert
      v-for="(message, source) in sourceErrors"
      :key="String(source)"
      class="alert-item"
      type="warning"
      :closable="false"
      :title="`${sourceLabel(String(source))}：${message}`"
    />
    <div v-if="result.counts" class="metric-grid counts">
      <MetricCard label="AKShare 缺失" :value="result.counts.akshare_missing" />
      <MetricCard label="Eastmoney 缺失" :value="result.counts.eastmoney_missing" />
      <MetricCard label="单位净值差异" :value="result.counts.unit_nav_diff" />
      <MetricCard label="日涨跌幅差异" :value="result.counts.daily_return_diff" />
    </div>
    <el-table v-if="result.rows.length" :data="result.rows" border stripe max-height="560">
      <el-table-column label="日期" width="120">
        <template #default="{ row }">{{ dateText(row.nav_date) }}</template>
      </el-table-column>
      <el-table-column label="AKShare 净值">
        <template #default="{ row }">{{ valueText(row.akshare_unit_nav) }}</template>
      </el-table-column>
      <el-table-column label="Eastmoney 净值">
        <template #default="{ row }">{{ valueText(row.eastmoney_unit_nav) }}</template>
      </el-table-column>
      <el-table-column label="净值差">
        <template #default="{ row }">{{ valueText(row.unit_nav_diff, 4) }}</template>
      </el-table-column>
      <el-table-column label="AKShare 日涨跌">
        <template #default="{ row }">{{ pct(row.akshare_daily_return) }}</template>
      </el-table-column>
      <el-table-column label="Eastmoney 日涨跌">
        <template #default="{ row }">{{ pct(row.eastmoney_daily_return) }}</template>
      </el-table-column>
      <el-table-column label="涨跌差">
        <template #default="{ row }">{{ valueText(row.daily_return_diff, 4) }}</template>
      </el-table-column>
      <el-table-column label="结论" width="130">
        <template #default="{ row }">
          <el-tag :type="verdictType(row.status)" size="small">{{ row.status || "未知" }}</el-tag>
        </template>
      </el-table-column>
    </el-table>
    <p v-else class="muted">该结果没有逐行明细（数据源不可用或仅单源可用）。</p>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";

import { dateText, pct } from "../api/format";
import type { ReconcileResult } from "../api/types";
import MetricCard from "./MetricCard.vue";

const props = defineProps<{ result: ReconcileResult }>();

const sourceErrors = computed(() =>
  Object.fromEntries(
    Object.entries(props.result.source_errors || {}).filter(([, message]) => Boolean(message)),
  ),
);

const STATUS_TYPES: Record<string, "success" | "warning" | "error" | "info"> = {
  ok: "success",
  warning: "warning",
  degraded: "warning",
  failed: "error",
};

function statusType(status: string) {
  return STATUS_TYPES[status] || "info";
}

const VERDICT_TYPES: Record<string, "success" | "warning" | "info"> = {
  一致: "success",
  "AKShare 缺失": "info",
  "Eastmoney 缺失": "info",
  单位净值差异: "warning",
  日涨跌幅差异: "warning",
};

function verdictType(status?: string | null) {
  return VERDICT_TYPES[status || ""] || "info";
}

function sourceLabel(source: string) {
  return { akshare: "AKShare", eastmoney: "Eastmoney" }[source] || source;
}

function valueText(value?: number | null, digits = 4) {
  return value === null || value === undefined ? "—" : Number(value).toFixed(digits);
}
</script>

<style scoped>
.alert-item {
  margin-top: 10px;
}

.counts {
  margin-top: 12px;
}
</style>
