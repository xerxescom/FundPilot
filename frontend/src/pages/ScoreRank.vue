<template>
  <div v-loading="loading">
    <div class="toolbar panel">
      <el-segmented
        v-model="selectedStrategy"
        :options="strategyOptions"
        :disabled="loading"
        @change="loadScores"
      />
      <el-select v-model="ratings" multiple placeholder="评级筛选" style="min-width: 260px">
        <el-option v-for="rating in ratingOptions" :key="rating" :label="rating" :value="rating" />
      </el-select>
      <el-select v-model="signals" multiple placeholder="窗口信号" style="min-width: 220px">
        <el-option
          v-for="signal in signalOptions"
          :key="signal"
          :label="signalText(signal)"
          :value="signal"
        />
      </el-select>
      <el-select v-model="confidenceLevels" multiple placeholder="可信度" style="min-width: 180px">
        <el-option
          v-for="level in confidenceOptions"
          :key="level"
          :label="confidenceText(level)"
          :value="level"
        />
      </el-select>
      <el-slider v-model="minScore" :min="0" :max="100" style="width: 260px" />
    </div>
    <el-alert
      v-if="currentStrategy?.scenario"
      class="section"
      type="info"
      :closable="false"
      :title="currentStrategy.name"
      :description="currentStrategy.scenario"
    />
    <div class="section panel">
      <el-table :data="filtered" border stripe>
        <el-table-column prop="fund_code" label="基金代码" />
        <el-table-column prop="fund_name" label="基金名称" min-width="180" />
        <el-table-column label="总分"><template #default="{ row }">{{ scoreText(row.total_score) }}</template></el-table-column>
        <el-table-column label="可信度" min-width="120">
          <template #default="{ row }">
            <el-tag :type="confidenceTag(row.confidence_level)">
              {{ confidenceText(row.confidence_level) }} {{ scoreText(row.confidence_score) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="窗口信号" min-width="140">
          <template #default="{ row }">
            <el-tag :type="signalTag(row.buy_window_signal)">
              {{ signalText(row.buy_window_signal) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="市场环境" min-width="130">
          <template #default="{ row }">
            <el-tag :type="marketTag(row.market_signal)">
              {{ marketText(row.market_signal) }} {{ percentileText(row.market_pe_percentile) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="同类排名" min-width="140">
          <template #default="{ row }">
            {{ peerText(row) }}
          </template>
        </el-table-column>
        <el-table-column label="组合适配" min-width="130">
          <template #default="{ row }">
            <el-tag :type="fitTag(row.portfolio_fit_level)">
              {{ fitText(row.portfolio_fit_level) }} {{ scoreText(row.portfolio_fit_score) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="rating" label="评级" />
        <el-table-column prop="strategy_name" label="评分策略" min-width="120" />
        <el-table-column label="风险标签" min-width="180">
          <template #default="{ row }">{{ riskLabels(row) }}</template>
        </el-table-column>
        <el-table-column prop="reason" label="推荐理由" min-width="280" />
      </el-table>
    </div>
    <div class="section panel">
      <ChartBox :option="barOption" />
    </div>
  </div>
</template>

<script setup lang="ts">
import type { EChartsOption } from "echarts";
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";

import { api } from "../api/fundpilot";
import { scoreText } from "../api/format";
import type { Score, ScoreStrategy } from "../api/types";
import ChartBox from "../components/ChartBox.vue";

const loading = ref(false);
const route = useRoute();
const rows = ref<Score[]>([]);
const strategies = ref<ScoreStrategy[]>([]);
const selectedStrategy = ref("default");
const ratings = ref<string[]>([]);
const signals = ref<NonNullable<Score["buy_window_signal"]>[]>([]);
const confidenceLevels = ref<NonNullable<Score["confidence_level"]>[]>([]);
const initializedQueryFilters = ref(false);
const minScore = ref(0);
const strategyOptions = computed(() => strategies.value.map((item) => ({ label: item.name, value: item.key })));
const currentStrategy = computed(() => strategies.value.find((item) => item.key === selectedStrategy.value));
const ratingOptions = computed(() => Array.from(new Set(rows.value.map((row) => row.rating).filter(Boolean))) as string[]);
const signalOptions = computed(
  () => Array.from(new Set(rows.value.map((row) => row.buy_window_signal).filter(Boolean))) as NonNullable<Score["buy_window_signal"]>[],
);
const confidenceOptions = computed(
  () => Array.from(new Set(rows.value.map((row) => row.confidence_level).filter(Boolean))) as NonNullable<Score["confidence_level"]>[],
);
const filtered = computed(() =>
  rows.value.filter(
    (row) =>
      (!ratings.value.length || ratings.value.includes(row.rating || "")) &&
      (!signals.value.length || signals.value.includes(row.buy_window_signal as NonNullable<Score["buy_window_signal"]>)) &&
      (!confidenceLevels.value.length ||
        confidenceLevels.value.includes(row.confidence_level as NonNullable<Score["confidence_level"]>)) &&
      Number(row.total_score || 0) >= minScore.value,
  ),
);
const barOption = computed<EChartsOption>(() => ({
  grid: { left: 110, right: 30, top: 20, bottom: 20 },
  xAxis: { type: "value", max: 100 },
  yAxis: { type: "category", data: filtered.value.slice(0, 20).map((row) => row.fund_name || row.fund_code) },
  series: [{ type: "bar", data: filtered.value.slice(0, 20).map((row) => row.total_score || 0) }],
}));

async function loadScores() {
  loading.value = true;
  try {
    rows.value = await api.strategyTopScores(selectedStrategy.value);
    ratings.value = ratingOptions.value;
    applyQueryFilters();
  } finally {
    loading.value = false;
  }
}

function parseQueryList(value: unknown) {
  const raw = Array.isArray(value) ? value.join(",") : String(value || "");
  return raw
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function applyQueryFilters() {
  if (initializedQueryFilters.value) return;
  const querySignals = parseQueryList(route.query.signals) as NonNullable<Score["buy_window_signal"]>[];
  const queryConfidence = parseQueryList(route.query.confidence) as NonNullable<Score["confidence_level"]>[];
  if (querySignals.length) signals.value = querySignals;
  if (queryConfidence.length) confidenceLevels.value = queryConfidence;
  initializedQueryFilters.value = true;
}

function confidenceText(level?: Score["confidence_level"]) {
  const labels = { high: "高", medium: "中", low: "低" };
  return level ? labels[level] : "未知";
}

function confidenceTag(level?: Score["confidence_level"]) {
  if (level === "high") return "success";
  if (level === "medium") return "warning";
  return "danger";
}

function signalText(signal?: Score["buy_window_signal"]) {
  const labels = {
    favorable: "窗口较好",
    watch: "可以观察",
    wait_pullback: "等待确认",
    cautious: "谨慎观察",
    blocked: "不可操作",
  };
  return signal ? labels[signal] : "暂无";
}

function signalTag(signal?: Score["buy_window_signal"]) {
  if (signal === "favorable") return "success";
  if (signal === "watch") return "primary";
  if (signal === "wait_pullback") return "warning";
  return "danger";
}

function marketText(signal?: Score["market_signal"]) {
  const labels = { supportive: "偏强", neutral: "中性", weak: "偏弱" };
  return signal ? labels[signal] : "暂无";
}

function marketTag(signal?: Score["market_signal"]) {
  if (signal === "supportive") return "success";
  if (signal === "weak") return "warning";
  return "info";
}

function percentileText(value?: number | null) {
  return value === null || value === undefined ? "" : `PE ${Math.round(value * 100)}%`;
}

function peerText(row: Score) {
  if (row.peer_percentile === null || row.peer_percentile === undefined) {
    return row.peer_group ? `${row.peer_group} 样本不足` : "暂无";
  }
  return `${Math.round(row.peer_percentile * 100)}% / ${row.peer_group_size || 0}`;
}

function fitText(level?: Score["portfolio_fit_level"]) {
  const labels = { high: "高", medium: "中", low: "低" };
  return level ? labels[level] : "暂无";
}

function fitTag(level?: Score["portfolio_fit_level"]) {
  if (level === "high") return "success";
  if (level === "medium") return "warning";
  return "danger";
}

function riskLabels(row: Score) {
  const labels = row.risk_flag_labels?.length ? row.risk_flag_labels : row.risk_flags;
  return labels?.length ? labels.join("；") : "无";
}

onMounted(async () => {
  loading.value = true;
  try {
    strategies.value = await api.scoreStrategies();
    if (!strategies.value.some((item) => item.key === selectedStrategy.value)) {
      selectedStrategy.value = strategies.value[0]?.key || "default";
    }
  } finally {
    loading.value = false;
  }
  await loadScores();
});
</script>
